import asyncio
import io
from app.audio.tts_azure import AzureTTS
from app.config import settings
from app.api.routes_audio_ws import _pack_audio_frame

async def mock_ws_send_logic():
    tts = AzureTTS()
    
    # Simulate Brain feeding ElevenLabs stream
    async def _mock_stream():
        yield "Hello, "
        yield "this is a test "
        yield "of chunk fragmentation."
        
    print(f"Config Chunk Size: {settings.tts_chunk_size}")

    chunk_id = 0
    # Simulate routes_audio_ws.py line 128:
    async for audio_chunk in tts.synthesize_stream(_mock_stream()):
        print(f"\n[Generator yielded chunk size: {len(audio_chunk)}]")
        
        chunk_size = settings.tts_chunk_size
        offset = 0
        while offset < len(audio_chunk):
            frame_data = audio_chunk[offset : offset + chunk_size]
            
            # _pack_audio_frame calculates RMS on `frame_data`
            frame = _pack_audio_frame(chunk_id, frame_data)
            import struct
            rms = struct.unpack("<f", frame[8:12])[0]
            
            print(f"  -> WebSocket Frame [{chunk_id}] length: {len(frame_data)} | RMS: {rms:.4f}")
            
            chunk_id += 1
            offset += chunk_size

if __name__ == "__main__":
    asyncio.run(mock_ws_send_logic())
