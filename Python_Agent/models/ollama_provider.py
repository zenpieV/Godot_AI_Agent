from ollama import chat

from config.settings import OLLAMA_MODEL


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

    return response.message.content
