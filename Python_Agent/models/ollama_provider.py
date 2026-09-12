from ollama import chat

from config.settings import OLLAMA_MODEL
from agent.telemetry import ProviderResult, normalize_usage


def ask_ollama(
    conversation,
    schema,
    model=None,
):
    """
    Send the full conversation to Ollama.

    `model` overrides the settings default so the
    panel's per-turn model selection reaches the API
    call; None falls back to OLLAMA_MODEL.

    Returns:
        A raw JSON string matching the provided schema.
    """

    response = chat(
        model=model or OLLAMA_MODEL,
        messages=conversation,
        format=schema,
    )

    return ProviderResult(
        text=response.message.content,
        usage=normalize_usage(response),
    )
