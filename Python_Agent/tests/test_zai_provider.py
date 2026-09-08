from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from models import zai_provider
from agent.telemetry import ProviderResult


CONVERSATION = [
    {"role": "system", "content": "System instruction."},
    {"role": "user", "content": "Find Player."},
    {"role": "assistant", "content": '{"action":"find_nodes"}'},
    {
        "role": "tool",
        "content": '{"success":true,"nodes":[{"path":"Player"}]}',
        "tool_call_id": "internal-only",
        "tool_calls": [{"id": "internal-only"}],
    },
]


def _fake_response(status_code=200, json_data=None, text=""):
    """Build a minimal httpx-like response object."""
    response = SimpleNamespace(
        status_code=status_code,
        text=text,
        is_error=status_code >= 400,
    )
    if json_data is not None:
        response.json = Mock(return_value=json_data)
    return response


class _FakeClient:
    """Minimal httpx.Client stand-in supporting the context manager protocol."""

    def __init__(self, response):
        self.response = response
        self.post = Mock(return_value=response)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _patch_http(monkeypatch, response):
    """Replace httpx.Client with one that returns ``response`` from .post()."""
    instance = _FakeClient(response)
    client_cls = Mock(return_value=instance)
    monkeypatch.setattr(zai_provider.httpx, "Client", client_cls)
    return client_cls, instance


# 1. request construction / message conversion
def test_ask_zai_builds_request_and_converts_messages(monkeypatch):
    response_data = {
        "choices": [
            {"message": {"content": '{"action":"final_answer"}'}}
        ],
    }
    client_cls, client_instance = _patch_http(
        monkeypatch,
        _fake_response(json_data=response_data),
    )
    monkeypatch.setenv("ZAI_API_KEY", "test-key")

    result = zai_provider.ask_zai(CONVERSATION, {"ignored": True})

    assert isinstance(result, ProviderResult)
    assert result.text == '{"action":"final_answer"}'

    # Client construction
    client_cls.assert_called_once_with(timeout=120.0)

    # Request construction
    client_instance.post.assert_called_once()
    request = client_instance.post.call_args.kwargs
    assert request["headers"]["Authorization"] == "Bearer test-key"
    payload = request["json"]
    assert payload["model"] == zai_provider.ZAI_MODEL
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["temperature"] == 0.1

    # Message conversion: tool -> user with execution prefix
    messages = payload["messages"]
    assert messages[0] == {"role": "system", "content": "System instruction."}
    assert messages[1] == {"role": "user", "content": "Find Player."}
    assert messages[2] == {
        "role": "assistant",
        "content": '{"action":"find_nodes"}',
    }
    tool_message = messages[3]
    assert tool_message["role"] == "user"
    assert "AGENT EXECUTION RESULT:" in tool_message["content"]
    assert "tool_call_id" not in tool_message
    assert "tool_calls" not in tool_message


# 2. model / API key handling
def test_ask_zai_uses_configured_model(monkeypatch):
    response_data = {
        "choices": [{"message": {"content": '{"action":"final_answer"}'}}],
    }
    client_cls, _ = _patch_http(
        monkeypatch,
        _fake_response(json_data=response_data),
    )
    monkeypatch.setenv("ZAI_API_KEY", "test-key")

    zai_provider.ask_zai([], {})

    payload = client_cls.return_value.post.call_args.kwargs["json"]
    assert payload["model"] == "glm-4.7-flash"


def test_ask_zai_raises_when_api_key_missing(monkeypatch):
    client_cls, _ = _patch_http(
        monkeypatch,
        _fake_response(json_data={"choices": []}),
    )
    monkeypatch.delenv("ZAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="ZAI_API_KEY is not set"):
        zai_provider.ask_zai([], {})

    client_cls.assert_not_called()


# 3. successful response parsing
def test_ask_zai_parses_successful_response(monkeypatch):
    response_data = {
        "choices": [
            {
                "message": {
                    "content": '{"action":"find_nodes","node_name":"Hero"}'
                }
            }
        ],
    }
    _patch_http(
        monkeypatch,
        _fake_response(json_data=response_data),
    )
    monkeypatch.setenv("ZAI_API_KEY", "test-key")

    result = zai_provider.ask_zai(
        [{"role": "user", "content": "hi"}], {}
    )

    assert isinstance(result, ProviderResult)
    assert (
        result.text
        == '{"action":"find_nodes","node_name":"Hero"}'
    )
    assert result.usage.available is False


# 4. usage normalization
def test_ask_zai_normalizes_usage_metadata(monkeypatch):
    response_data = {
        "choices": [
            {"message": {"content": '{"action":"final_answer"}'}}
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 4,
            "total_tokens": 14,
        },
    }
    _patch_http(
        monkeypatch,
        _fake_response(json_data=response_data),
    )
    monkeypatch.setenv("ZAI_API_KEY", "test-key")

    result = zai_provider.ask_zai([], {})

    assert result.usage.available is True
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 4
    assert result.usage.total_tokens == 14


# 5. HTTP / API failure propagation
def test_ask_zai_raises_on_http_error(monkeypatch):
    _patch_http(
        monkeypatch,
        _fake_response(status_code=401, text="Unauthorized"),
    )
    monkeypatch.setenv("ZAI_API_KEY", "bad-key")

    with pytest.raises(
        RuntimeError, match="Z.ai API request failed: 401"
    ):
        zai_provider.ask_zai([], {})


def test_ask_zai_raises_on_empty_choices(monkeypatch):
    response_data = {"choices": []}
    _patch_http(
        monkeypatch,
        _fake_response(json_data=response_data),
    )
    monkeypatch.setenv("ZAI_API_KEY", "test-key")

    with pytest.raises(
        RuntimeError, match="no completion choices"
    ):
        zai_provider.ask_zai([], {})


def test_ask_zai_raises_on_empty_content(monkeypatch):
    response_data = {
        "choices": [{"message": {"content": ""}}],
    }
    _patch_http(
        monkeypatch,
        _fake_response(json_data=response_data),
    )
    monkeypatch.setenv("ZAI_API_KEY", "test-key")

    with pytest.raises(
        RuntimeError, match="empty model response"
    ):
        zai_provider.ask_zai([], {})
