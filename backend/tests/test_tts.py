import asyncio
from app.audio.tts_elevenlabs import ElevenLabsTTS
from app.audio.tts_azure import AzureTTS

async def test_tts_fallback():
    fallback = AzureTTS()
    tts = ElevenLabsTTS(fallback_tts=fallback)
    
    print("Attempting to synthesize text...")
    try:
        audio = await tts.synthesize("Hello! This is a test of the Azure TTS fallback system.")
        print(f"Success! Generated {len(audio)} bytes of audio.")
        with open("fallback_test.pcm", "wb") as f:
            f.write(audio)
            print("Saved output to fallback_test.pcm")
    except Exception as e:
        print(f"Failed completely: {e}")

if __name__ == "__main__":
    asyncio.run(test_tts_fallback())
