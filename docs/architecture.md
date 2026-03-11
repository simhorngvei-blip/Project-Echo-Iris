# Echo-Iris: System Architecture

This document maps out the core data flow and communication pipelines between the Python Backend (The Brain) and the Unity Frontend (The Body) to ensure stable WebSocket integration as the project scales.

---

## 🎧 1. The Audio Pipeline (Real-Time Conversational Flow)

This is the primary loop for interacting with the AI. It relies on concurrent WebSocket connections for low-latency voice streaming.

**Data Flow:**
1. **Microphone Capture (Unity):** The user holds a hotkey or clicks a button in the Unity client.
2. **Audio Streaming (Unity ➔ Python):** Unity records PCM audio chunks and streams the raw bytes over WebSockets to the Python server.
3. **Transcription (Python):** `faster-whisper` receives the full PCM payload, runs Speech-to-Text (STT), and extracts the user's prompt.
4. **LLM Inference (Python):** The transcript is passed to the local LLM (Ollama). The prompt is constrained by the System Prompt to output a strict JSON payload ("Method B").
5. **JSON Interception (Python):** The backend intercepts the LLM's response, extracting the `thought`, `spoken_text`, and `emotion` keys.
6. **TTS Generation (Python):** The `spoken_text` string is immediately routed to the Text-to-Speech engine (ElevenLabs, Kokoro, or Azure) to generate voice audio bytes.
7. **Audio Delivery (Python ➔ Unity):** The server packages the TTS audio bytes along with a custom 12-byte header containing the `emotion` string index (or plain string) and streams it back to Unity over the WebSocket.
8. **Lip-Sync & Playback (Unity):** `AudioPlaybackBuffer.cs` receives the audio, runs real-time FFT frequency analysis to calculate exact vowel blendshapes (あ, い, う, え, お), triggers the `emotion` animation, and plays the audio through the avatar.

---

## 👁️ 2. The Vision Subsystem (Active / Planned)

This system allows the AI to contextualize its environment by constantly interpreting desktop webcam data.

**Data Flow:**
1. **Frame Capture (Unity):** Unity's `VisionWebSocketManager.cs` captures a frame from the selected webcam at a steady interval (e.g., 5-10 FPS).
2. **Image Encoding (Unity ➔ Python):** The frame is heavily downscaled, compressed into a base64 JPEG, and sent to the server.
3. **Fast Object Detection (Python):** A lightweight detection model (YOLOv8 Nano) constantly scans incoming frames to identify objects in the room instantly.
4. **Deep Scene Description (Python):** On a slower interval (e.g., every 5 seconds), the frame is passed to a multimodal local LLM (LLaVA) which generates a rich natural-language description (e.g., "The user is holding a phone and smiling").
5. **Context Injection (Python):** Both the YOLO tags and LLaVA descriptions are silently injected into the AI's Short-Term Memory. When the user speaks, the LLM uses this recent visual context to formulate a response.

---

## 🔧 3. Action Tools & LangChain (Planned)

This framework gives the LLM agency to influence the physical world and the desktop environment autonomously.

**Data Flow:**
1. **Tool Invocation (Python):** The LLM decides it needs to perform an action based on context. Instead of a normal conversational response, it outputs a specialized JSON command (e.g., `{"tool": "set_timer", "args": {"minutes": 10}}`).
2. **Command Routing (Python):** The backend intercepts this non-conversational JSON and routes it to the corresponding Python module:
   *   **Desktop/OS:** Executes OS-level commands (open Notepad, check clock, search web).
   *   **Physical Hardware:** Sends serial commands to a connected microcontroller over Bluetooth/USB (e.g., Arduino robot arm).
   *   **Client Callbacks:** Sends a specialized WebSocket event back to Unity to trigger a visual change (e.g., spawning a digital alarm clock in the Unity scene).
3. **Feedback Loop (Python):** The server executes the tool and silently injects the result (e.g., "Timer set successfully") back into the LLM's Short-Term Memory so Emily knows the action occurred.
