import os
import time
import logging

from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors

from config.settings import GEMINI_MODEL


load_dotenv()


logger = logging.getLogger(__name__)


# Deferred initialization:
# API key and client are created on first call.
client = None
_client_initialized = False


# ==========================================
# Transient-error retry policy
# ==========================================
#
# Gemini occasionally returns a transient 503 ("model is
# currently experiencing high demand") that resolves itself
# within a few seconds. Without this, a single transient
# blip terminates the entire agent session.
#
# google.genai.errors.APIError.raise_error() classifies
# every non-2xx response by status code and raises:
#   - ClientError for 4xx (deterministic request problems)
#   - ServerError for 5xx (genuinely transient server-side
#     conditions, which 503 UNAVAILABLE falls under)
# This was confirmed by inspecting the installed SDK source
# directly rather than assumed. Only ServerError is treated
# as retryable here - ClientError, local errors (missing API
# key, empty-response RuntimeError, etc.) are never retried
# and propagate immediately, unchanged from current behavior.

GEMINI_MAX_ATTEMPTS = 3  # initial request + 2 retries

GEMINI_RETRY_BACKOFF_SECONDS = (1.0, 2.0)


def _is_transient_gemini_error(
    error: BaseException,
) -> bool:

    return isinstance(
        error,
        genai_errors.ServerError,
    )


def make_gemini_schema_compatible(
    value
):
    """
    Convert a Pydantic-generated JSON schema into a
    form accepted by Gemini's response_schema support.

    Gemini's SDK does not accept the JSON Schema
    keywords 'oneOf' or 'discriminator'.

    Pydantic discriminated unions commonly generate:

    - oneOf
    - discriminator

    Gemini accepts anyOf-style unions, so oneOf is
    converted recursively to anyOf and discriminator
    metadata is removed.
    """

    if isinstance(
        value,
        dict
    ):

        converted = {}

        for key, item in value.items():

            # Gemini SDK rejects discriminator.
            if key == "discriminator":

                continue


            # Gemini SDK rejects oneOf.
            # Convert it to anyOf.
            if key == "oneOf":

                converted["anyOf"] = (
                    make_gemini_schema_compatible(
                        item
                    )
                )

                continue


            converted[key] = (
                make_gemini_schema_compatible(
                    item
                )
            )


        return converted


    if isinstance(
        value,
        list
    ):

        return [

            make_gemini_schema_compatible(
                item
            )

            for item in value
        ]


    return value


def ask_gemini(
    conversation,
    schema
):
    """
    Send the complete agent conversation
    to Gemini and request structured JSON.

    The supplied schema is converted from the
    Pydantic JSON Schema representation into the
    subset supported by Gemini's response_schema
    implementation.
    """

    global client
    global _client_initialized


    # --------------------------------------
    # Lazy initialization
    # --------------------------------------

    if not _client_initialized:

        api_key = os.getenv(
            "GEMINI_API_KEY"
        )


        if not api_key:

            raise ValueError(
                "GEMINI_API_KEY was not found. "
                "Make sure it exists in your "
                ".env file."
            )


        client = genai.Client(
            api_key=api_key
        )


        _client_initialized = True


    # --------------------------------------
    # Convert schema for Gemini
    # --------------------------------------

    gemini_schema = (
        make_gemini_schema_compatible(
            schema
        )
    )


    # --------------------------------------
    # Build prompts
    # --------------------------------------

    system_prompt = ""


    conversation_prompt = ""


    for message in conversation:

        role = message[
            "role"
        ]


        content = message[
            "content"
        ]


        if role == "system":

            system_prompt += (
                content
                + "\n"
            )


        elif role == "user":

            conversation_prompt += (
                "USER:\n"
                + content
                + "\n\n"
            )


        elif role == "assistant":

            conversation_prompt += (
                "ASSISTANT:\n"
                + content
                + "\n\n"
            )


        elif role == "tool":

            conversation_prompt += (
                "TOOL RESULT:\n"
                + content
                + "\n\n"
            )


    # --------------------------------------
    # Ask Gemini (with bounded transient retry)
    # --------------------------------------

    generate_content_config = {
        "system_instruction": (
            system_prompt
        ),

        "response_mime_type": (
            "application/json"
        ),

        "response_schema": (
            gemini_schema
        ),
    }

    response = None

    for attempt in range(
        1,
        GEMINI_MAX_ATTEMPTS + 1,
    ):

        try:

            response = (
                client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=conversation_prompt,
                    config=generate_content_config,
                )
            )

            break

        except Exception as error:

            if not _is_transient_gemini_error(
                error
            ):

                # Deterministic/local errors (bad
                # request, missing key, schema
                # problems, etc.) are never retried.

                raise

            status_code = getattr(
                error,
                "code",
                "unknown",
            )

            if attempt == GEMINI_MAX_ATTEMPTS:

                logger.error(
                    "Gemini transient provider error "
                    f"({status_code}) persisted after "
                    f"{GEMINI_MAX_ATTEMPTS} attempts. "
                    "Giving up."
                )

                raise

            backoff_seconds = (
                GEMINI_RETRY_BACKOFF_SECONDS[
                    attempt - 1
                ]
            )

            logger.warning(
                "Gemini transient provider error "
                f"({status_code}). Retry "
                f"{attempt}/{GEMINI_MAX_ATTEMPTS - 1} "
                f"in {backoff_seconds}s."
            )

            time.sleep(
                backoff_seconds
            )


    if not response.text:

        raise RuntimeError(
            "Gemini returned an empty response."
        )


    return response.text