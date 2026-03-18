# Project Echo-Iris: LinkedIn Post Series (Deep Dive Edition)

## Post 1: The Origin & Architecture (Kickoff)
**Date:** Early March

**Dev Log: Project Echo-Iris - The Foundation 🏗️**

While watching clips of the AI VTuber "Neuro-sama," I was marveling at the systems engineering required to run an LLM, real-time TTS, computer vision, and a 3D rig simultaneously. I decided to build my own version: Project Echo-Iris.

I’m building this in public. Here is the technical foundation:
* **The Brain (Async Python):** I architected a Python/FastAPI backend utilizing high-performance, asynchronous WebSockets to handle concurrent streaming for Audio, Vision, and Tools without blocking the main event loop.
  
  ![Screenshot: Visual architecture diagram mapping FastAPI WebSockets to the various internal subsystems](placeholder_fastapi_architecture.png)
  
* **Local Intelligence:** Instead of relying purely on cloud APIs where network latency ruins real-time immersion, I integrated local LLMs (Qwen 2.5:0.5b via Ollama) specifically tuned for millisecond-response generation and heavily customized system prompt execution.
  
  ![Screenshot: Windows Terminal demonstrating Ollama successfully loading the Qwen local weights](placeholder_ollama_terminal.png)

* **Dual-Track Recall:** An AI needs context. I engineered a hybrid memory system. An STM (Short-Term Memory) handles the sliding array of conversational context limits, while an LTM (Long-Term Memory) leverages ChromaDB mapping with Nomic Text Embeddings for persistent, semantic vector search Retrieval-Augmented Generation (RAG).
  
  ![Screenshot: Code snippet highlighting the ChromaDB collection retrieval logic](placeholder_chromadb_code.png)

The backend is breathing and holding semantic state. Next up: building the body in Unity. 

#GenerativeAI #SoftwareEngineering #Python #FastAPI #Ollama #ChromaDB #BuildInPublic

---

## Post 2: The Frontend & The "T-Pose of Doom"
**Date:** March 2nd - 4th

**Dev Log: Project Echo-Iris - Rigging & Procedural Lip-Sync 👄**

Connecting a Python AI backend to a Unity C# frontend is where things get messy. My goal this week was simple: get the VRM avatar breathing and speaking naturally.

* **The T-Pose of Doom:** Hit a major roadblock with the avatar failing to animate. Traced it back to the Animator Controller relying on generic Mixamo mappings. I had to write custom retargeting logic specifically mapping the skeletal bone transforms to the strict Unity Humanoid rig definition.
  
  ![Screenshot: The Unity Editor viewing the Avatar configuration panel, showing the mapping to a Humanoid Rig](placeholder_unity_humanoid_rig.png)

* **Lip-Sync Desync:** Initially, the avatar's mouth wouldn't sync with the incoming audio. It constantly spat an RMS value of `0.000` because the server-side calculations were being mismatched against Unity's raw audio buffer format structure. 
* **The Solution (Method B & GetOutputData):** I pivoted the architecture. Instead of relying purely on network RMS triggers, I programmed Unity to perform local audio analysis directly from the active `AudioSource` buffer utilizing `GetOutputData()`. I implemented a custom Cooley-Tukey FFT (Fast Fourier Transform) that sweeps the float array samples `[-1, 1]` locally at 44.1kHz, translating real-time wave frequencies to drive the VRM blendshapes in perfect phonetic sync with Japanese vowel constraints (あ, い, う, え, お).
  
  ![Screenshot: Code snippet of the custom Cooley-Tukey FFT from the AvatarTester script](placeholder_fft_math.png)
  ![Screenshot: The VRM Avatar in Unity mid-sentence, correctly rendering the 'O' vowel blendshape](placeholder_vrm_lipsync.png)

#Unity3D #GameDev #SoftwareArchitecture #VTuber #EchoIris #AudioProcessing

---

## Post 3: Audio Engineering & Byte-Alignment
**Date:** March 3rd - 6th

**Dev Log: Project Echo-Iris - Audio Pipelines & Data Corruption 🎧**

An autonomous AI needs to hear and speak flawlessly without lag. This phase was all about strictly synchronized asynchronous I/O data streams. 

* **The Stack:** Implemented OpenAI Whisper (`faster-whisper`) over PyTorch for local speech-to-text, paired dynamically with ElevenLabs/Azure TTS for voice synthesis.
  
  ![Screenshot: Faster-Whisper command line output tracing the detected English transcription](placeholder_whisper_logs.png)

* **The Bug:** I ran into a severe audio corruption issue where the synthesized soundwaves were literally tearing into static noise on the Unity side.
* **The Fix:** I wrote extensive WebSocket fragmentation tests (`test_ws_fragmentation.py`) on the Python backend and identified a horrifying "byte-alignment slice error". Unity expected strict 16-bit PCM data (2 bytes per sample), but the Python TTS generator was aggressively slicing networking chunks at 4096 bytes asynchronously. Because of TCP packet fragmentation, the network sometimes sliced exactly in the middle of a 2-byte structural sample, shifting every subsequent byte by 1 and destroying the waveform. I engineered a strict even-byte chunk accumulator in the FastAPI router (`len(data) % 2 == 0`), entirely resolving the corrupted frames and ensuring every payload landed perfectly aligned.
  
  ![Screenshot: pytest output showing the test_ws_fragmentation.py successfully ensuring even-byte boundaries](placeholder_pytest_accumulator.png)

#AudioEngineering #Python #DataStreams #OpenAIWhisper #Debugging 

---

## Post 4: Vision & The Desktop Mascot
**Date:** March 7th - 9th

**Dev Log: Project Echo-Iris - Senses & Overlay Mode 👁️**

Giving the AI the ability to "see" my screen and exist outside of a standard application window box. 

* **Dual-Track Vision:** To avoid pipeline bottlenecks, I decoupled the vision system. A lightweight `yolov8n.pt` computer vision model acts as a blazing-fast Object Detector for rapid scene checks (bounding boxes), while an instance of LLaVA handles deep, interrogate-level semantic rendering of base64 video payloads streamed iteratively over the WebSockets. 
  
  ![Screenshot: A visual representation of the YOLOv8 bounding boxes intercepting an object feed](placeholder_yolo_vision.png)

* **Mascot Mode (Windows API Hacks):** I wanted a desktop companion, not just a game executable. I bypassed Unity's default rendering by tapping into the OS level, utilizing P/Invoke to call `user32.dll` directly from C#. By manipulating the extended window styles (specifically toggling `WS_EX_LAYERED` and `WS_EX_TRANSPARENT`), I forced the main thread into a borderless, click-through, always-on-top rendering overlay—allowing Echo-Iris to walk freely across my taskbar without interrupting my workflow.

  ![Screenshot: Project Echo-Iris rendering seamlessly as a transparent overlay on the Windows desktop taskbar](placeholder_desktop_mascot.png)
  ![Screenshot: The TransparentWindowManager.cs script showcasing the P/Invoke user32.dll imports](placeholder_user32_code.png)

#ComputerVision #YOLO #LLaVA #Unity3D #WindowsAPI #MachineLearning

---

## Post 5: Professionalization & Deployment
**Date:** March 10th - 11th

**Dev Log: Project Echo-Iris - Refactoring & WebGL 🚀**

Transitioning this from a hacky local prototype into a professional, deployable open-source architecture. 

* **WebGL Porting:** Deployed the app directly to the browser. Web browsers completely sandbox and isolate native TCP/UDP sockets and direct microphone hardware. To override this, I had to author custom JavaScript interoperability layers (`.jslib`), seamlessly hooking Unity's internal web requests into native browser-level HTML5 WebSocket and `MediaRecorder` APIs.
  
  ![Screenshot: The WebGL build of Echo-Iris successfully rendering inside Google Chrome](placeholder_webgl_browser.png)

* **The Great Refactor:** Executed a massive, phased structural refactor to pivot the workspace to Project Echo-Iris. Since Unity relies deeply on specific `.meta` cache GUIDs, blindly renaming scripts destroys the project. I meticulously tracked and preserved the namespace and class modifications, maintaining a 100% asset linkage success rate across the Prefabs and Scenes.
* **Open Source Readiness:** Implemented strict Semantic Versioning (`v1.0.0`), authored comprehensive Markdown documentation involving Mermaid.js architecture flowcharts, and established rigorous GitHub Issue Templates for community bug tracking and feature pull requests. 

  ![Screenshot: The Echo-Iris GitHub repository landing page displaying the new Readme and Markdown formatting](placeholder_github_repo.png)

#OpenSource #WebGL #GitHub #DevOps #SoftwareEngineering #EchoIris

---

## Post 6: Demolishing Technical Debt
**Date:** March 13th - 17th

**Dev Log: Project Echo-Iris - Consolidating The Architecture 🧹**

After achieving stable V1 WebGL deployment, I audited the underlying Unity frontend and realized the codebase was a victim of its own rapid iterative prototyping. Severe technical debt had accumulated around how the VRM avatar was being puppeteered.

* **The Problem (Race Conditions):** I was running three disparate scripts (`ExpressionController`, `LipSyncController`, and `AvatarAnimationController`) that were actively fighting for dominance over the avatar's Animator and `SkinnedMeshRenderer` blendshapes. Because they operated autonomously on Unity's asynchronous `Update()` ticks without a centralized state machine, they constantly overwrote each other's vector weights—causing facial twitching, animation snapping, and a terrifying jitter.
* **The Solution (The Unified Controller):** I ripped out the fragmented scripts and engineered a single, monolithic `EchoIrisAvatarController`. It acts as a strict, prioritized finite state machine orchestrating: 1) Base locomotion/idling, 2) Triggered emote animations, 3) Emotional VRM blendshapes via the LLM Method B JSON protocol, and 4) Real-time procedural lip-syncing driven by the localized audio FFT.
  
  ![Screenshot: The Unity Inspector window showing the unified EchoIrisAvatarController attached to the root character](placeholder_unified_controller_inspector.png)

* **High-Level Orchestration:** To cap it off, I elevated the high-level routing logic into a master `EchoIrisManager` script. Now, the telemetry flows perfectly: `VisionManager` and `AudioManager` parse incoming server WebSocket byte arrays and hand them synchronously to the `EchoIrisManager`, which gracefully commands the `AvatarController` to execute the appropriate physical response without any state collision or race conditions.
  
  ![Screenshot: Code snippet of the EchoIrisManager dispatching websocket bytes to the AvatarController](placeholder_manager_routing_code.png)

The framework is finally clean, deeply modular, and prepared for advanced multi-modal tool integration.

#GameDev #SoftwareArchitecture #Refactoring #Unity3D #TechnicalDebt #EchoIris