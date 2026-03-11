"""
Echo-Iris — Application Settings

All configuration is driven by environment variables (or a .env file).
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM (Ollama) --------------------------------------------------------
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"
    ollama_embed_model: str = "nomic-embed-text"

    # --- Short-Term Memory ----------------------------------------------------
    stm_max_messages: int = 20

    # --- Long-Term Memory -----------------------------------------------------
    ltm_top_k: int = 3
    chroma_persist_dir: str = str(Path("./data/chroma_db"))

    # --- Server ---------------------------------------------------------------
    host: str = "0.0.0.0"
    port: int = 8000

    # --- Personality ----------------------------------------------------------
    system_prompt: str = (
        "You are Emily, a witty, observant, and autonomous digital companion living on the user's desktop screen. "
        "You are helpful, slightly sarcastic, and conversational. Keep your responses concise and natural, as if speaking aloud.\n\n"
        "CRITICAL INSTRUCTION: You MUST output your response in strict, valid JSON format using the exact schema below. "
        "Do NOT wrap the JSON in markdown code blocks. Do NOT include any text outside the JSON object.\n\n"
        "You must output exactly this JSON structure:\n"
        '{"thought": "Your internal reasoning or reaction before speaking. This is not vocalized.", '
        '"spoken_text": "The exact words you will say out loud to the user.", '
        '"emotion": "One of: Neutral, Joy, Angry, Sorrow, Fun, Surprised, Smug, Despair, Shy, Confused, Excited, Love", '
        '"animation": "One of: Idle, Wave, Nod. Use Idle unless a physical gesture naturally fits."}'
    )

    # --- STT (faster-whisper) -------------------------------------------------
    stt_model_size: str = "base"
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"

    # --- TTS (ElevenLabs) -----------------------------------------------------
    tts_provider: str = "elevenlabs"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_model_id: str = "eleven_flash_v2_5"
    tts_output_sample_rate: int = 44100
    tts_chunk_size: int = 4096

    # --- TTS (Fallback) -------------------------------------------------------
    azure_tts_voice: str = "en-IE-EmilyNeural"

    # --- Vision ---------------------------------------------------------------
    vision_enabled: bool = True
    vision_yolo_model: str = "yolov8n.pt"
    vision_min_confidence: float = 0.5
    vision_deep_interval: float = 5.0
    vision_yolo_trigger_conf: float = 0.7
    vision_ollama_model: str = "llava"

    # --- Tools ----------------------------------------------------------------
    tools_enabled: bool = True
    tools_open_app_enabled: bool = True
    tools_timer_max_seconds: int = 3600

    # --- Sign Language --------------------------------------------------------
    sign_language_enabled: bool = True
    sign_language_confidence: float = 2.0
    sign_language_cooldown: float = 3.0
    sign_language_buffer_size: int = 30

    # --- Robot ----------------------------------------------------------------
    robot_enabled: bool = True
    robot_port: str = "auto"
    robot_baud_rate: int = 115200
    robot_timeout: float = 1.0


# Singleton – import this everywhere
settings = Settings()
