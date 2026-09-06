from types import SimpleNamespace
from unittest.mock import Mock

from models import gemini_provider
from agent.telemetry import ProviderResult


def test_ask_gemini_returns_raw_response_text(monkeypatch):
    response = SimpleNamespace(text='{"message":"hello"}')
    generate_content = Mock(return_value=response)
    client = SimpleNamespace(
        models=SimpleNamespace(generate_content=generate_content)
    )

    monkeypatch.setattr(gemini_provider, "client", client)
    monkeypatch.setattr(gemini_provider, "_client_initialized", True)

    result = gemini_provider.ask_gemini(
        conversation=[
            {"role": "system", "content": "Return JSON."},
            {"role": "user", "content": "Say hello."},
        ],
        schema={"type": "object"},
    )

    assert isinstance(result, ProviderResult)
    assert result.text == response.text
    assert result.usage.available is False


def test_ask_gemini_normalizes_usage_metadata(monkeypatch):
    response = SimpleNamespace(
        text='{"message":"hello"}',
        usage_metadata=SimpleNamespace(
            prompt_token_count=12,
            candidates_token_count=8,
            total_token_count=20,
        ),
    )
    client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=Mock(return_value=response)
        )
    )
    monkeypatch.setattr(gemini_provider, "client", client)
    monkeypatch.setattr(gemini_provider, "_client_initialized", True)

    result = gemini_provider.ask_gemini([], {"type": "object"})

    assert result.usage.input_tokens == 12
    assert result.usage.output_tokens == 8
    assert result.usage.total_tokens == 20
    assert result.usage.available is True