from ollama import chat

from config.settings import OLLAMA_MODEL
from agent.telemetry import ProviderResult, normalize_usage


def ask_ollama(
    conversation,
    schema
):
    """
    Send the full conversation to Ollama.

    Returns:
        A raw JSON string matching the provided schema.
    """

    response = chat(
        model=OLLAMA_MODEL,
        messages=conversation,
        format=schema,
    )

    return ProviderResult(
        text=response.message.content,
        usage=normalize_usage(response),
    )
