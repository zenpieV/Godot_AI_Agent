# ==========================================
# Model provider configuration
# ==========================================

MODEL_PROVIDER = "gemini"

# MODEL_PROVIDER = "groq"

# MODEL_PROVIDER = "zai"

# MODEL_PROVIDER = "openrouter"

# ==========================================
# Batch execution configuration
# ==========================================

# Maximum number of actions a model may propose in a single
# bounded "batch" decision (see agent/schemas.py). This is a
# hard ceiling enforced by AgentDecision validation, not a
# suggestion - a batch larger than this is rejected outright,
# never silently truncated or executed.

MAX_BATCH_SIZE = 5

# ==========================================
# Ollama configuration
# ==========================================

OLLAMA_MODEL = "qwen3-vl:4b"


# ==========================================
# Gemini configuration
# ==========================================

GEMINI_MODEL = "gemini-3.5-flash-lite"

# ==========================================
# OpenRouter configuration
# ==========================================

OPENROUTER_MODEL = (
    "cohere/north-mini-code:free"
)

# ==========================================
# Z.ai configuration
# ==========================================

ZAI_MODEL = "glm-4.7-flash"

# ==========================================
# Offline scene execution configuration
# ==========================================
# run_scene_offline launches the scene as a headless
# subprocess of the Python agent (not via the editor),
# which makes the scene's stdout/stderr readable for
# autonomous error checking. Override via environment
# variables if the engine binary or project root lives
# elsewhere.

import os as _os

GODOT_BINARY_PATH = _os.getenv(
    "GODOT_BINARY_PATH",
    "../../../Godot_v4.7.2-stable_win64_console.exe",
)

PROJECT_PATH = _os.getenv(
    "PROJECT_PATH",
    "..",
)
