import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config.settings import GEMINI_MODEL
from models import gemini_provider, groq_provider
from agent.telemetry import ProviderResult


CONVERSATION = [
    {"role": "system", "content": "System instruction."},
    {"role": "user", "content": "Find Player."},
    {"role": "assistant", "content": '{"action":"find_nodes"}'},
    {
        "role": "tool",
        "content": '{"success":true,"nodes":[{"path":"Player"}]}' ,
        "tool_call_id": "internal-only",
        "tool_calls": [{"id": "internal-only"}],
    },
]


def test_gemini_maps_messages_schema_and_json_response(monkeypatch):
    response = SimpleNamespace(text='{"action":"final_answer"}')
    generate_content = Mock(return_value=response)
    client = SimpleNamespace(
        models=SimpleNamespace(generate_content=generate_content)
    )
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(gemini_provider, "client", client)
    monkeypatch.setattr(gemini_provider, "_client_initialized", True)

    schema = {
        "type": "object",
        "oneOf": [{"type": "object", "discriminator": {"propertyName": "action"}}],
        "properties": {"action": {"type": "string"}},
    }

    result = gemini_provider.ask_gemini(CONVERSATION, schema)

    assert isinstance(result, ProviderResult)
    assert result.text == response.text
    assert result.usage.available is False
    generate_content.assert_called_once()
    request = generate_content.call_args.kwargs
    assert request["model"] == GEMINI_MODEL
    assert request["contents"] == (
        "USER:\nFind Player.\n\n"
        "ASSISTANT:\n{\"action\":\"find_nodes\"}\n\n"
        "TOOL RESULT:\n{\"success\":true,\"nodes\":[{\"path\":\"Player\"}]}\n\n"
    )
    assert request["config"]["system_instruction"] == "System instruction.\n"
    assert request["config"]["response_mime_type"] == "application/json"
    assert "oneOf" not in json.dumps(request["config"]["response_schema"])
    assert "discriminator" not in json.dumps(request["config"]["response_schema"])
    assert "anyOf" in request["config"]["response_schema"]


def test_gemini_retries_transient_errors_without_live_sdk(monkeypatch):
    transient = RuntimeError("transient")
    generate_content = Mock(
        side_effect=[transient, transient, SimpleNamespace(text="ok")]
    )
    client = SimpleNamespace(
        models=SimpleNamespace(generate_content=generate_content)
    )
    monkeypatch.setattr(gemini_provider, "client", client)
    monkeypatch.setattr(gemini_provider, "_client_initialized", True)
    monkeypatch.setattr(
        gemini_provider,
        "_is_transient_gemini_error",
        lambda error: error is transient,
    )
    monkeypatch.setattr(gemini_provider.time, "sleep", Mock())

    result = gemini_provider.ask_gemini([], {})

    assert isinstance(result, ProviderResult)
    assert result.text == "ok"
    assert result.usage.available is False
    assert generate_content.call_count == 3
    assert gemini_provider.time.sleep.call_count == 2


def test_gemini_does_not_retry_non_transient_error(monkeypatch):
    generate_content = Mock(side_effect=RuntimeError("bad request"))
    client = SimpleNamespace(
        models=SimpleNamespace(generate_content=generate_content)
    )
    monkeypatch.setattr(gemini_provider, "client", client)
    monkeypatch.setattr(gemini_provider, "_client_initialized", True)
    monkeypatch.setattr(
        gemini_provider,
        "_is_transient_gemini_error",
        lambda error: False,
    )

    with pytest.raises(RuntimeError, match="bad request"):
        gemini_provider.ask_gemini([], {})

    assert generate_content.call_count == 1


def test_groq_maps_messages_and_request_options(monkeypatch):
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"action":"final_answer"}'))]
    )
    raw_response = SimpleNamespace(
        headers={},
        parse=Mock(return_value=response),
    )
    create = Mock(return_value=raw_response)
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                with_raw_response=SimpleNamespace(create=create)
            )
        )
    )
    groq_constructor = Mock(return_value=client)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(groq_provider, "Groq", groq_constructor)
    monkeypatch.setattr(groq_provider, "_maybe_wait_for_headroom", Mock())

    result = groq_provider.ask_groq(CONVERSATION, {"ignored": True})

    assert isinstance(result, ProviderResult)
    assert result.text == response.choices[0].message.content
    assert result.usage.available is False
    groq_constructor.assert_called_once_with(
        api_key="test-key",
        max_retries=groq_provider.GROQ_MAX_RETRIES,
    )
    create.assert_called_once()
    request = create.call_args.kwargs
    assert request["model"] == groq_provider.GROQ_MODEL
    assert request["reasoning_effort"] == "medium"
    assert request["response_format"] == {"type": "json_object"}
    assert request["messages"][:3] == CONVERSATION[:3]
    tool_message = request["messages"][3]
    assert tool_message["role"] == "user"
    assert "AGENT EXECUTION RESULT:" in tool_message["content"]
    assert "tool_call_id" not in tool_message
    assert "tool_calls" not in tool_message


def test_groq_request_errors_are_propagated_after_configured_retries(monkeypatch):
    create = Mock(side_effect=RuntimeError("rate limited"))
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                with_raw_response=SimpleNamespace(create=create)
            )
        )
    )
    groq_constructor = Mock(return_value=client)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(groq_provider, "Groq", groq_constructor)
    monkeypatch.setattr(groq_provider, "_maybe_wait_for_headroom", Mock())

    with pytest.raises(RuntimeError, match="rate limited"):
        groq_provider.ask_groq([], {})

    groq_constructor.assert_called_once_with(
        api_key="test-key",
        max_retries=groq_provider.GROQ_MAX_RETRIES,
    )
    create.assert_called_once()


def test_groq_rate_limit_headers_update_and_pace_deterministically(monkeypatch):
    groq_provider._last_rate_limit_state.update(
        {
            "remaining_requests": None,
            "remaining_tokens": None,
            "reset_requests_seconds": None,
            "reset_tokens_seconds": None,
        }
    )
    groq_provider._update_rate_limit_state_from_headers(
        {
            "x-ratelimit-remaining-requests": "1",
            "x-ratelimit-remaining-tokens": "100",
            "x-ratelimit-reset-requests": "2s",
            "x-ratelimit-reset-tokens": "1500ms",
        }
    )
    sleep = Mock()
    monkeypatch.setattr(groq_provider.time, "sleep", sleep)

    groq_provider._maybe_wait_for_headroom()

    assert groq_provider._last_rate_limit_state == {
        "remaining_requests": 1,
        "remaining_tokens": 100,
        "reset_requests_seconds": 2.0,
        "reset_tokens_seconds": 1.5,
    }
    sleep.assert_called_once_with(2.0)
