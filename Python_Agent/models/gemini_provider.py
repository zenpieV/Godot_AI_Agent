import logging
import os
import time
from copy import deepcopy

from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors

from config.settings import GEMINI_MODEL
from agent.telemetry import (
    ProviderResult,
    normalize_usage,
    provider_result_text,
)


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

GEMINI_NESTED_BATCH_EXCLUDED_ACTIONS = {
    "CountNodesAction",
    "ListAutoloadsAction",
    "GetEditorStateAction",
    "ListScenesInProjectAction",
    "GetUndoHistorySummaryAction",
    "AddToGroupAction",
    "RemoveFromGroupAction",
    "ConnectSignalAction",
    "DisconnectSignalAction",
}

GEMINI_TOP_LEVEL_EXCLUDED_ACTIONS = set()


def _is_transient_gemini_error(
    error: BaseException,
) -> bool:

    return isinstance(
        error,
        genai_errors.ServerError,
    )


def _inline_count_nodes_refs(
    value,
    count_schema,
):

    if isinstance(value, dict):

        if (
            "items" in value
            and isinstance(value["items"], dict)
            and "anyOf" in value["items"]
        ):
            value = deepcopy(value)
            value["items"]["anyOf"] = [
                item
                for item in value["items"]["anyOf"]
                if not (
                    isinstance(item, dict)
                    and (
                        item.get("title")
                        in GEMINI_NESTED_BATCH_EXCLUDED_ACTIONS
                        or item.get("$ref")
                        in {
                            "#/$defs/" + action_name
                            for action_name in
                            GEMINI_NESTED_BATCH_EXCLUDED_ACTIONS
                        }
                    )
                )
            ]

        if value.get("$ref") == "#/$defs/CountNodesAction":

            return deepcopy(count_schema)

        return {
            key: _inline_count_nodes_refs(item, count_schema)
            for key, item in value.items()
        }

    if isinstance(value, list):

        return [
            _inline_count_nodes_refs(item, count_schema)
            for item in value
        ]

    return value


def make_gemini_schema_compatible(
    value
):
    """
    Convert a Pydantic-generated JSON schema into a
    form accepted by Gemini's response_schema support.

    The provider-bound schema is normalized by recursively
    removing JSON-schema constraint keywords that the Gemini
    provider rejects in this environment (discriminator,
    minimum, maximum, minItems, maxItems), while host-side
    Pydantic validation remains intact.

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

            # Recursively remove provider-rejected constraint
            # keywords observed in this environment.
            if key in ("discriminator", "minimum", "maximum", "minItems", "maxItems"):

                continue


            # Gemini accepts anyOf-style unions; oneOf is converted.
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

        # Gemini rejects overlapping find/count union branches after
        # Pydantic's discriminator metadata is removed.
        if converted.get("title") == "CountNodesAction":
            properties = converted.setdefault("properties", {})

            for property_name in (
                "node_name",
                "node_type",
                "parent_path",
                "name_match",
            ):
                properties.get(property_name, {}).pop(
                    "default",
                    None,
                )

            properties["result_mode"] = {
                "enum": ["count"],
                "type": "string",
            }
            required = converted.setdefault("required", [])
            for property_name in (
                "node_name",
                "node_type",
                "parent_path",
                "name_match",
                "result_mode",
            ):
                if property_name not in required:
                    required.append(property_name)

        if converted.get("title") == "MoveChildAction":
            properties = converted.setdefault("properties", {})
            properties["result_mode"] = {
                "enum": ["move_child"],
                "type": "string",
            }
            required = converted.setdefault("required", [])
            if "result_mode" not in required:
                required.append("result_mode")

        if "$defs" in converted:

            count_schema = converted["$defs"].get(
                "CountNodesAction"
            )

            if count_schema is not None:

                converted = _inline_count_nodes_refs(
                    converted,
                    count_schema,
                )

                converted["$defs"].pop(
                    "CountNodesAction",
                    None,
                )

                for action_name in GEMINI_TOP_LEVEL_EXCLUDED_ACTIONS:
                    converted["$defs"].pop(action_name, None)

                if "anyOf" in converted:
                    converted["anyOf"] = [
                        item
                        for item in converted["anyOf"]
                        if not (
                            isinstance(item, dict)
                            and (
                                item.get("title") in
                                GEMINI_TOP_LEVEL_EXCLUDED_ACTIONS
                                or item.get("$ref") in {
                                    "#/$defs/" + name
                                    for name in
                                    GEMINI_TOP_LEVEL_EXCLUDED_ACTIONS
                                }
                            )
                        )
                    ]

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


    response_text = provider_result_text(response)

    if not response_text:

        raise RuntimeError(
            "Gemini returned an empty response."
        )


    return ProviderResult(
        text=response_text,
        usage=normalize_usage(
            getattr(response, "usage_metadata", None)
        ),
    )