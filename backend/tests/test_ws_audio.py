import asyncio
import websockets
import json

async def test_audio_ws():
    uri = "ws://localhost:8000/ws/audio"
    try:
        async with websockets.connect(uri) as ws:
            print("Connected to Audio WS")
            
            # Send small dummy audio bytes (e.g. 1000 bytes of zeros for PCM audio)
            dummy_pcm = bytes(1000)
            await ws.send(dummy_pcm)
            print("Sent dummy PCM data")
            
            # Send end_audio marker
            await ws.send(json.dumps({"type": "end_audio"}))
            print("Sent end_audio marker")
            
            # Wait for response
            while True:
                response = await ws.recv()
                if isinstance(response, str):
                    print(f"Received JSON: {response}")
                else:
                    print(f"Received binary frame of {len(response)} bytes")
                    
    except Exception as e:
        print(f"Connection closed with error: {e}")

if __name__ == "__main__":
    asyncio.run(test_audio_ws())
