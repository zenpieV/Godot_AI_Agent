import os

import httpx

from config.settings import OPENROUTER_MODEL
from agent.telemetry import ProviderResult, normalize_usage


OPENROUTER_API_URL = (
    "https://openrouter.ai/api/v1/chat/completions"
)


def _prepare_openrouter_messages(
    conversation,
):
    """
    Convert the agent's provider-neutral conversation
    into messages that are valid for OpenRouter's
    OpenAI-compatible chat endpoint.

    Our agent executes Godot tools itself rather than
    using native OpenAI tool calling, so internal
    role='tool' messages must be represented as normal
    conversational context.
    """

    prepared_messages = []

    for message in conversation:

        role = message.get(
            "role"
        )

        content = message.get(
            "content",
            ""
        )

        if role == "tool":

            prepared_messages.append(
                {
                    "role": "user",
                    "content": (
                        "AGENT EXECUTION RESULT:\n"
                        + content
                    ),
                }
            )

            continue

        prepared_messages.append(
            {
                "role": role,
                "content": content,
            }
        )

    return prepared_messages


def ask_openrouter(
    conversation,
    schema,
):
    """
    Send the current agent conversation to OpenRouter.

    The initial OpenRouter model does not guarantee
    JSON-schema enforcement, so we request JSON-object
    output and continue relying on the agent's existing
    normalization + strict local Pydantic validation.

    `schema` is intentionally accepted to preserve the
    common provider interface, even though this model
    does not enforce it remotely.
    """

    del schema

    api_key = os.getenv(
        "OPENROUTER_API_KEY"
    )

    if not api_key:

        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. "
            "Add it to your .env file before "
            "using the OpenRouter provider."
        )

    messages = (
        _prepare_openrouter_messages(
            conversation
        )
    )

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "response_format": {
            "type": "json_object",
        },
        "temperature": 0.1,
    }

    headers = {
        "Authorization": (
            "Bearer "
            + api_key
        ),
        "Content-Type": (
            "application/json"
        ),
    }

    with httpx.Client(
        timeout=120.0
    ) as client:

        response = client.post(
            OPENROUTER_API_URL,
            headers=headers,
            json=payload,
        )

    if response.is_error:
        raise RuntimeError(
            "OpenRouter API request failed: "
            + str(response.status_code)
            + " "
            + response.text
        )

    response_data = (
        response.json()
    )

    choices = response_data.get(
        "choices"
    )

    if not choices:

        raise RuntimeError(
            "OpenRouter returned no completion choices."
        )

    message = (
        choices[0].get(
            "message",
            {}
        )
    )

    content = message.get(
        "content"
    )

    if not content:

        raise RuntimeError(
            "OpenRouter returned an empty model response."
        )

    return ProviderResult(
        text=content,
        usage=normalize_usage(
            response_data.get("usage")
        ),
    )