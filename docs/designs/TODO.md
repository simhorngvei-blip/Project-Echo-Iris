# Echo-Iris: Development Tasks

## ✅ Completed
- [x] Fixed Azure TTS byte-alignment slice error
- [x] Built the `EchoIrisDebugUI` Unity dashboard
- [x] Implemented `DirectLipSync.cs` for local RMS calculation in Unity
- [x] Implemented 'Method B' JSON parsing in the Python backend
- [x] Created Unity `ExpressionController.cs` to trigger VRM blendshapes from the JSON payload
- [x] Hooked up YOLOv8 object detection endpoint
- [x] Passed 'Latest LLaVA Scene' text into the LLM context automatically
- [x] Created REST tool endpoints (`/api/tools/timer`, `/api/tools/open_app`, `/api/tools/robot`)
- [x] Wired Unity DebugUI mock buttons to actual FastAPI tool endpoints

## 🚧 Current Task (Priority)
- [ ] Test full Method B pipeline end-to-end (speak → JSON → emotion + audio)
- [ ] Test ExpressionController blendshape auto-detection on VRM model

## 👁️ Upcoming
- [ ] Add Sign Language gesture → speech injection UI indicators
- [ ] Add emotion history display to DebugUI
