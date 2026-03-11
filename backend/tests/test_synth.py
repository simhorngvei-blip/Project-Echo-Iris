import asyncio
import numpy as np
from app.audio.tts_azure import AzureTTS
from app.api.routes_audio_ws import _compute_rms

async def a():
    tts = AzureTTS()
    out = await tts.synthesize('This works')
    print(len(out))
    rms = _compute_rms(out)
    print("RMS:", rms)
    
    # Print the first 20 bytes
    print("First 20 bytes:", list(out[:20]))

    samples = np.frombuffer(out, dtype=np.int16).astype(np.float32)
    print("First 10 samples (float):", list(samples[:10]))
    print("Max sample:", np.max(np.abs(samples)))

if __name__ == "__main__":
    asyncio.run(a())
