import os
import re
import time
import logging

from groq import Groq

from config.settings import GROQ_MODEL
from agent.telemetry import ProviderResult, normalize_usage

# Import specific error types defensively - the exact class names have
# been stable across recent groq-python versions, but we never want a
# missing/renamed class to break the provider. If the import fails we
# just fall back to generic exception handling below.

try:
    from groq import RateLimitError as GroqRateLimitError
except ImportError:
    GroqRateLimitError = None

try:
    from groq import APIStatusError as GroqAPIStatusError
except ImportError:
    GroqAPIStatusError = None


logger = logging.getLogger(__name__)


# The Groq SDK already retries automatically and honors the server's
# Retry-After header on 429s, which is correct behavior - we don't
# replace that. We only make the retry count an explicit, bounded
# project setting instead of relying on whichever default the
# installed SDK version happens to ship with.
GROQ_MAX_RETRIES = 4

# Groq returns x-ratelimit-* headers on every response (see
# https://console.groq.com/docs/rate-limits). If the last known
# response told us we're effectively out of request or token budget
# for the current window, we wait out the reported reset time before
# firing the next call, instead of firing anyway and guaranteeing a
# 429 followed by the same wait via the SDK's reactive retry. This is
# intentionally conservative: it only engages when headroom is
# genuinely low, never on every call, and never for longer than
# PROACTIVE_PACING_MAX_WAIT_SECONDS.
PROACTIVE_PACING_REQUEST_FLOOR = 1
PROACTIVE_PACING_TOKEN_FLOOR = 200
PROACTIVE_PACING_MAX_WAIT_SECONDS = 30


_last_rate_limit_state = {
    "remaining_requests": None,
    "remaining_tokens": None,
    "reset_requests_seconds": None,
    "reset_tokens_seconds": None,
}


def _prepare_groq_messages(conversation):
    """Translate internally executed results for Groq's chat protocol."""

    messages = []

    for message in conversation:

        prepared_message = dict(message)

        if prepared_message.get("role") == "tool":
            prepared_message["role"] = "user"
            prepared_message["content"] = (
                "AGENT EXECUTION RESULT:\n"
                + str(
                    prepared_message.get(
                        "content",
                        "",
                    )
                )
                + "\n\n"
                + "This result came from an internally "
                + "executed agent action, not native tool calling."
            )

            prepared_message.pop(
                "tool_call_id",
                None,
            )
            prepared_message.pop(
                "tool_calls",
                None,
            )

        messages.append(
            prepared_message
        )

    return messages


def _parse_groq_duration(value):
    """
    Parse Groq's rate-limit reset strings (e.g. "1.2s", "120ms",
    "6m0s") into a float number of seconds.

    Returns None if the value is missing or doesn't match the
    expected shape, so callers fail open (skip pacing) rather than
    guess at a wait time.
    """

    if not value:
        return None

    value = value.strip()

    match = re.fullmatch(
        r"(?:(\d+(?:\.\d+)?)m)?(\d+(?:\.\d+)?)(ms|s)?",
        value,
    )

    if not match:
        return None

    minutes_part, number_part, unit = match.groups()

    try:
        seconds = float(number_part)
    except (TypeError, ValueError):
        return None

    if unit == "ms":
        seconds = seconds / 1000.0

    if minutes_part:
        try:
            seconds += float(minutes_part) * 60.0
        except ValueError:
            pass

    return seconds


def _update_rate_limit_state_from_headers(headers):
    """
    Read Groq's x-ratelimit-* headers and cache the latest known
    values for use by _maybe_wait_for_headroom(). Never raises - a
    missing or unparseable header just leaves that value unknown.

    Logs a single compact status line. Never logs full response
    payloads.
    """

    if not headers:
        return

    def _get_int(name):
        raw = headers.get(name)
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    remaining_requests = _get_int(
        "x-ratelimit-remaining-requests"
    )
    remaining_tokens = _get_int(
        "x-ratelimit-remaining-tokens"
    )
    reset_requests_seconds = _parse_groq_duration(
        headers.get("x-ratelimit-reset-requests")
    )
    reset_tokens_seconds = _parse_groq_duration(
        headers.get("x-ratelimit-reset-tokens")
    )

    _last_rate_limit_state["remaining_requests"] = remaining_requests
    _last_rate_limit_state["remaining_tokens"] = remaining_tokens
    _last_rate_limit_state["reset_requests_seconds"] = reset_requests_seconds
    _last_rate_limit_state["reset_tokens_seconds"] = reset_tokens_seconds

    logger.info(
        "Groq rate limit status: remaining_requests=%s "
        "remaining_tokens=%s reset_requests=%ss reset_tokens=%ss",
        remaining_requests,
        remaining_tokens,
        reset_requests_seconds,
        reset_tokens_seconds,
    )


def _maybe_wait_for_headroom():
    """
    If the last known response indicates we're effectively out of
    request or token budget for this window, sleep for the reported
    reset time (capped) before the next call. No-op whenever headroom
    looks healthy, so this never adds delay to normal operation.
    """

    remaining_requests = _last_rate_limit_state["remaining_requests"]
    remaining_tokens = _last_rate_limit_state["remaining_tokens"]

    low_on_requests = (
        remaining_requests is not None
        and remaining_requests <= PROACTIVE_PACING_REQUEST_FLOOR
    )

    low_on_tokens = (
        remaining_tokens is not None
        and remaining_tokens <= PROACTIVE_PACING_TOKEN_FLOOR
    )

    if not (low_on_requests or low_on_tokens):
        return

    wait_candidates = [
        seconds
        for seconds in (
            _last_rate_limit_state["reset_requests_seconds"]
            if low_on_requests
            else None,
            _last_rate_limit_state["reset_tokens_seconds"]
            if low_on_tokens
            else None,
        )
        if seconds is not None
    ]

    if not wait_candidates:
        return

    wait_seconds = min(
        max(wait_candidates),
        PROACTIVE_PACING_MAX_WAIT_SECONDS,
    )

    if wait_seconds <= 0:
        return

    logger.info(
        "Groq proactive pacing: remaining budget is low "
        "(requests=%s, tokens=%s). Waiting %.1fs before the "
        "next request instead of triggering a 429.",
        remaining_requests,
        remaining_tokens,
        wait_seconds,
    )

    time.sleep(wait_seconds)


def ask_groq(
    conversation,
    schema,
):
    api_key = os.getenv(
        "GROQ_API_KEY"
    )

    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. "
            "Set the GROQ_API_KEY environment "
            "variable before using the Groq provider."
        )

    client = Groq(
        api_key=api_key,
        max_retries=GROQ_MAX_RETRIES,
    )

    groq_messages = _prepare_groq_messages(
        conversation
    )

    _maybe_wait_for_headroom()

    try:

        # with_raw_response gives us the HTTP headers alongside the
        # parsed completion, so we can read Groq's rate-limit info.
        # This is a standard, documented accessor on Stainless-
        # generated clients (the same pattern openai-python uses) -
        # not an SDK internal.
        raw_response = (
            client.chat.completions.with_raw_response.create(
                model=GROQ_MODEL,
                messages=groq_messages,
                reasoning_effort="medium",
                response_format={
                    "type": "json_object",
                },
            )
        )

        _update_rate_limit_state_from_headers(
            raw_response.headers
        )

        response = raw_response.parse()

    except AttributeError:

        # Older groq-python versions may not expose
        # with_raw_response. Fall back to a plain call so the agent
        # keeps working; we just lose header-based pacing and
        # observability in that case.

        logger.warning(
            "Groq client does not support with_raw_response "
            "in this SDK version; falling back to a standard "
            "call without rate-limit header visibility."
        )

        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=groq_messages,
            reasoning_effort="medium",
            response_format={
                "type": "json_object",
            },
        )

    except Exception as error:

        if (
            GroqRateLimitError is not None
            and isinstance(error, GroqRateLimitError)
        ):
            logger.error(
                "Groq rate limit exceeded after the SDK's "
                "built-in retries were exhausted: %s",
                error,
            )

        elif (
            GroqAPIStatusError is not None
            and isinstance(error, GroqAPIStatusError)
        ):
            logger.error(
                "Groq API returned an error status: %s",
                error,
            )

        else:
            logger.error(
                "Groq request failed: %s",
                error,
            )

        raise

    message = (
        response.choices[0].message
    )

    if not message.content:
        raise RuntimeError(
            "Groq returned an empty model response."
        )

    return ProviderResult(
        text=message.content,
        usage=normalize_usage(
            getattr(response, "usage", None)
        ),
    )
