# ==========================================
# Model provider configuration
# ==========================================

MODEL_PROVIDER = "gemini"

# MODEL_PROVIDER = "groq"

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

GEMINI_MODEL = "gemini-3.1-flash-lite"

# ==========================================
# OpenRouter configuration
# ==========================================

OPENROUTER_MODEL = (
    "cohere/north-mini-code:free"
)
