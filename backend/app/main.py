"""
Echo-Iris — FastAPI Application Entry-Point

Bootstraps the Brain (STM + LTM + LLM) and Audio subsystems at
startup and exposes the REST / WebSocket routers.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.core.brain import Brain

if TYPE_CHECKING:
    from app.audio.stt import SpeechToText
    from app.audio.tts_base import TTSBase
    from app.vision.pipeline import VisionPipeline

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application-scoped singleton instances
# ---------------------------------------------------------------------------
_brain: Brain | None = None
_stt: SpeechToText | None = None
_tts: TTSBase | None = None
_vision: VisionPipeline | None = None


def get_brain() -> Brain:
    """Return the singleton Brain instance (created during lifespan)."""
    if _brain is None:
        raise RuntimeError("Brain has not been initialised — is the app running?")
    return _brain


def get_audio_components():
    """Return (stt, tts, brain) for the audio WebSocket handler."""
    if _stt is None or _tts is None or _brain is None:
        raise RuntimeError("Audio subsystems not initialised — is the app running?")
    return _stt, _tts, _brain


def get_vision_pipeline():
    """Return the singleton VisionPipeline for the vision WebSocket."""
    if _vision is None:
        raise RuntimeError("Vision pipeline not initialised — is the app running?")
    return _vision


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _brain, _stt, _tts, _vision
    logger.info("🧠 Echo-Iris starting up …")

    # Phase 1: Core Brain
    _brain = Brain()
    logger.info("✅ Brain ready  (model=%s)", settings.ollama_model)

    # Phase 2: Audio subsystems
    from app.audio.stt import SpeechToText
    _stt = SpeechToText()
    logger.info("🎤 STT ready  (model=%s)", settings.stt_model_size)

    # Initialise the configured TTS provider
    if settings.tts_provider == "elevenlabs":
        from app.audio.tts_elevenlabs import ElevenLabsTTS
        from app.audio.tts_azure import AzureTTS
        
        fallback = AzureTTS()
        _tts = ElevenLabsTTS(fallback_tts=fallback)
        logger.info("🔊 TTS ready  (provider=elevenlabs, fallback=azure)")
    else:
        logger.warning("⚠️ No TTS provider configured (tts_provider=%s)", settings.tts_provider)

    # Phase 3: Vision subsystem
    if settings.vision_enabled:
        from app.vision.detector import ObjectDetector
        from app.vision.scene import SceneDescriber
        from app.vision.pipeline import VisionPipeline
        detector = ObjectDetector()
        describer = SceneDescriber()
        _vision = VisionPipeline(detector, describer, _brain.stm)
        logger.info("👁️ Vision pipeline ready  (yolo=%s, deep=%s)",
                    settings.vision_yolo_model, settings.vision_ollama_model)
    else:
        logger.info("👁️ Vision disabled")

    yield  # --- app is running ---

    logger.info("🛑 Echo-Iris shutting down …")
    _brain = None
    _stt = None
    _tts = None
    _vision = None


# ---------------------------------------------------------------------------
# FastAPI app factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Echo-Iris — Core Backend",
    description="Multimodal AI VTuber brain: LLM + STM + LTM + STT + TTS.",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS — allow everything during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Register routers
# ---------------------------------------------------------------------------
from app.api.routes_rest import router as rest_router  # noqa: E402
from app.api.routes_ws import router as ws_router  # noqa: E402
from app.api.routes_audio_ws import router as audio_ws_router  # noqa: E402
from app.api.routes_vision_ws import router as vision_ws_router  # noqa: E402
from app.api.routes_tools import router as tools_router  # noqa: E402

app.include_router(rest_router)
app.include_router(ws_router)
app.include_router(audio_ws_router)
app.include_router(vision_ws_router)
app.include_router(tools_router)

# ---------------------------------------------------------------------------
# Serve Unity WebGL if available
# ---------------------------------------------------------------------------
# Path corresponds to: backend/app/main.py -> backend/app -> backend -> ../frontend/unity_web_build
web_build_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend", "unity_web_build")
if os.path.exists(web_build_dir):
    logger.info(f"Serving WebGL frontend from {web_build_dir}")
    app.mount("/", StaticFiles(directory=web_build_dir, html=True), name="static")
else:
    logger.warning(f"No WebGL build found at {web_build_dir} — website will not be served.")
