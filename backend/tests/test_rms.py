import asyncio
import numpy as np
from app.audio.tts_azure import AzureTTS
from app.api.routes_audio_ws import _compute_rms
from app.config import settings

async def diagnostics():
    tts = AzureTTS()
    print("Generating audio with Azure TTS...")
    audio_bytes = await tts.synthesize("Hello! This is a test of the RMS.")
    
    print(f"Total bytes: {len(audio_bytes)}")
    
    # Test RMS for each chunk, matching how the websocket server sends it
    chunk_size = settings.tts_chunk_size
    
    valid_chunks = 0
    zero_chunks = 0
    
    for i in range(0, len(audio_bytes), chunk_size):
        chunk = audio_bytes[i : i + chunk_size]
        rms = _compute_rms(chunk)
        if rms > 0:
            valid_chunks += 1
        else:
            zero_chunks += 1
            
    print(f"Valid chunks (RMS > 0): {valid_chunks}")
    print(f"Zero chunks (RMS = 0): {zero_chunks}")
    
    # Print the RMS of the first valid chunk
    for i in range(0, len(audio_bytes), chunk_size):
        chunk = audio_bytes[i : i + chunk_size]
        rms = _compute_rms(chunk)
        if rms > 0:
            print(f"First valid chunk RMS: {rms}")
            break

if __name__ == "__main__":
    asyncio.run(diagnostics())
