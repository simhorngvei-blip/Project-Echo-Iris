import asyncio
import numpy as np
import struct
from app.audio.tts_azure import AzureTTS
from app.api.routes_audio_ws import _pack_audio_frame, _compute_rms
from app.config import settings

async def diagnostics():
    tts = AzureTTS()
    print(f"Generating audio with Azure TTS ({settings.tts_output_sample_rate}Hz)...")
    
    # 1. Generate Azure audio chunks natively
    chunks_out = []
    async for chunk in tts._synthesize_text("Hello, this is a test. The RMS should move my mouth."):
        chunks_out.append(chunk)
    
    # Simulate routes_audio_ws.py behavior
    chunk_id = 0
    zero_packed = 0
    valid_packed = 0
    
    print("\n--- Simulating WebSocket Pack ---")
    for frame_data in chunks_out:
        rms = _compute_rms(frame_data)
        
        # This is exactly what _pack_audio_frame does
        packed = _pack_audio_frame(chunk_id, frame_data)
        
        # Read the RMS right back out of the packed struct
        magic, cid, dlen, packed_rms = struct.unpack("<2sHIf", packed[:12])
        
        if chunk_id < 5:
            print(f"[{chunk_id}] Original RMS: {rms:.4f}  |  Packed RMS: {packed_rms:.4f}  |  Len: {dlen}")
            
        if packed_rms > 0:
            valid_packed += 1
        else:
            zero_packed += 1
            
        chunk_id += 1
        
    print(f"\nTotal zero RMS packed headers: {zero_packed}")
    print(f"Total valid RMS packed headers: {valid_packed}")


if __name__ == "__main__":
    asyncio.run(diagnostics())
