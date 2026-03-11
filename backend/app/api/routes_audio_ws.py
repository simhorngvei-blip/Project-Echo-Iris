"""
Echo-Iris — Bidirectional Audio WebSocket

Endpoint: ``/ws/audio``

Protocol
--------
**Inbound (Unity → Server):**
- Binary frames: raw PCM 16-bit signed LE, 16 kHz, mono audio chunks.
- JSON text frame ``{"type": "end_audio"}`` signals end-of-utterance.

**Outbound (Server → Unity):**
- JSON text frame ``{"type": "transcript", "text": "..."}`` with the STT result.
- Binary frames: 12-byte header + PCM audio data (see ``_pack_audio_frame``).
- JSON text frame ``{"type": "audio_end"}`` when all audio chunks have been sent.
"""

from __future__ import annotations

import logging
import struct
from typing import AsyncIterator

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Wire-format magic bytes for Echo-Iris audio frames
_MAGIC = b"\xCA\x01"


def _compute_rms(pcm_bytes: bytes) -> float:
    """Compute RMS energy of a 16-bit PCM chunk (for lip-sync)."""
    if len(pcm_bytes) < 2:
        return 0.0
    samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(samples ** 2)))


def _transcode_to_pcm(audio_bytes: bytes) -> bytes:
    """
    Checks if the audio bytes are WebM/Ogg (from WebGL MediaRecorder).
    If so, uses ffmpeg to transcode them to 16kHz 16-bit Mono PCM.
    Returns the raw PCM bytes.
    """
    import subprocess
    import tempfile
    import os

    # Check for WebM EBML header (\x1a\x45\xdf\xa3) or Ogg magic (OggS)
    is_webm = audio_bytes.startswith(b"\x1a\x45\xdf\xa3")
    is_ogg = audio_bytes.startswith(b"OggS")
    is_riff = audio_bytes.startswith(b"RIFF")

    if not (is_webm or is_ogg or is_riff):
        # Already raw PCM (from Unity Editor/Standalone)
        return audio_bytes

    logger.info("Detected compressed audio blob (WebGL). Transcoding via ffmpeg...")
    
    with tempfile.NamedTemporaryFile(delete=False) as temp_in:
        temp_in.write(audio_bytes)
        in_path = temp_in.name
    
    out_path = in_path + ".raw"

    try:
        # ffmpeg -y -i <in> -f s16le -acodec pcm_s16le -ar 16000 -ac 1 <out>
        subprocess.run([
            "ffmpeg", "-y", "-i", in_path,
            "-f", "s16le", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1",
            out_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        with open(out_path, "rb") as f:
            pcm = f.read()
        return pcm
    except Exception as e:
        logger.error(f"Failed to transcode audio from WebGL: {e}")
        return b""
    finally:
        if os.path.exists(in_path):
            os.remove(in_path)
        if os.path.exists(out_path):
            os.remove(out_path)


def _pack_audio_frame(chunk_id: int, pcm_data: bytes) -> bytes:
    """
    Build a binary frame with a 12-byte header for Unity.

    Layout::

        magic     (2B)  0xCA 0x01
        chunk_id  (2B)  uint16 LE
        data_len  (4B)  uint32 LE
        rms       (4B)  float32 LE
        pcm_data  (variable)
    """
    rms = _compute_rms(pcm_data)
    header = struct.pack("<2sHIf", _MAGIC, chunk_id & 0xFFFF, len(pcm_data), rms)
    return header + pcm_data


@router.websocket("/ws/audio")
async def websocket_audio(ws: WebSocket):
    """
    Full audio pipeline: receive audio → STT → Brain → TTS → send audio.
    """
    await ws.accept()
    logger.info("Audio WebSocket client connected")

    # Lazy imports to avoid circular dependencies
    from app.main import get_audio_components

    stt, tts, brain = get_audio_components()

    audio_buffer = bytearray()

    try:
        while True:
            # ---- Receive phase: collect audio chunks until end_audio ----
            message = await ws.receive()

            if message.get("type") == "websocket.disconnect":
                break

            # Binary frame → accumulate PCM audio
            if "bytes" in message and message["bytes"]:
                audio_buffer.extend(message["bytes"])
                continue

            # Text frame → check for control messages
            if "text" in message and message["text"]:
                import json
                try:
                    payload = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue

                msg_type = payload.get("type")

                # ----- Route 1: End of audio recording → STT then Brain -----
                if msg_type == "end_audio":
                    if not audio_buffer:
                        await ws.send_json({"type": "error", "error": "No audio received"})
                        continue

                    raw_bytes = bytes(audio_buffer)
                    audio_buffer.clear()

                    # Transcode if it's WebM/Ogg from the WebGL plugin
                    pcm_bytes = _transcode_to_pcm(raw_bytes)
                    if not pcm_bytes:
                        await ws.send_json({"type": "error", "error": "Failed to transcode audio"})
                        continue

                    # 1. Transcribe (STT)
                    transcript = stt.transcribe(pcm_bytes)
                    if not transcript:
                        await ws.send_json({"type": "transcript", "text": ""})
                        await ws.send_json({"type": "audio_end"})
                        continue

                    # Send transcript to Unity (for subtitles)
                    await ws.send_json({"type": "transcript", "text": transcript})

                # ----- Route 2: Text chat → skip STT, go straight to Brain -----
                elif msg_type == "text_chat":
                    transcript = payload.get("text", "").strip()
                    if not transcript:
                        await ws.send_json({"type": "error", "error": "Empty text message"})
                        continue

                    # Echo the text as a transcript for the UI
                    await ws.send_json({"type": "transcript", "text": transcript})

                else:
                    continue

                # ============================================================
                # Shared pipeline: Brain → Method B parse → TTS → send audio
                # ============================================================

                # 2. Get full Brain response (accumulate all tokens)
                full_response_parts = []
                async for token in brain.stream_process(transcript):
                    full_response_parts.append(token)
                full_response = "".join(full_response_parts)

                # 3. Parse Method B JSON: {"thought":..., "spoken_text":..., "emotion":..., "animation":...}
                spoken_text = full_response
                emotion = "Neutral"
                animation = "Idle"
                thought = ""

                try:
                    import json as json_mod
                    # Strip markdown code fences if the LLM wrapped them
                    cleaned = full_response.strip()
                    if cleaned.startswith("```"):
                        cleaned = cleaned.split("\n", 1)[-1]
                    if cleaned.endswith("```"):
                        cleaned = cleaned.rsplit("```", 1)[0]
                    cleaned = cleaned.strip()

                    parsed = json_mod.loads(cleaned)
                    if isinstance(parsed, dict):
                        spoken_text = parsed.get("spoken_text", full_response)
                        emotion = parsed.get("emotion", "Neutral")
                        animation = parsed.get("animation", "Idle")
                        thought = parsed.get("thought", "")
                        logger.info("Method B parsed — emotion=%s, animation=%s, thought=%s",
                                    emotion, animation, thought[:60])
                except (json_mod.JSONDecodeError, ValueError):
                    # Fallback: treat entire response as spoken_text
                    logger.warning("Method B parse failed — using raw text as spoken_text")

                # 4. Send emotion + animation to Unity BEFORE audio starts
                await ws.send_json({"type": "emotion", "emotion": emotion, "animation": animation})

                # Send the AI reply text for display in the Debug UI
                await ws.send_json({"type": "ai_reply", "text": spoken_text})

                # 5. Stream spoken_text through TTS → audio chunks
                chunk_id = 0

                async def _tts_text_stream(_text: str = spoken_text):
                    """Yield the spoken_text as a single chunk for TTS."""
                    yield _text

                async for audio_chunk in tts.synthesize_stream(_tts_text_stream()):
                    audio_buffer.extend(audio_chunk)
                    
                    chunk_size = settings.tts_chunk_size
                    if chunk_size % 2 != 0:
                        chunk_size -= 1
                        
                    while len(audio_buffer) >= chunk_size:
                        frame_data = bytes(audio_buffer[:chunk_size])
                        audio_buffer = audio_buffer[chunk_size:]
                        
                        frame = _pack_audio_frame(chunk_id, frame_data)
                        await ws.send_bytes(frame)
                        chunk_id += 1
                
                # Send any remaining audio in the buffer
                if len(audio_buffer) > 0:
                    if len(audio_buffer) % 2 != 0:
                         audio_buffer.pop()
                    if len(audio_buffer) > 0:
                         frame = _pack_audio_frame(chunk_id, bytes(audio_buffer))
                         await ws.send_bytes(frame)
                         chunk_id += 1
                    audio_buffer.clear()

                # Signal end of audio stream
                await ws.send_json({"type": "audio_end"})
                logger.info(
                    "Audio response complete — %d chunks, emotion=%s, animation=%s, for: %s",
                    chunk_id, emotion, animation,
                    transcript[:60],
                )

    except WebSocketDisconnect:
        logger.info("Audio WebSocket client disconnected")
    except Exception:
        logger.exception("Audio WebSocket error")
        if ws.client_state == WebSocketState.CONNECTED:
            await ws.send_json({"type": "error", "error": "Internal server error"})
