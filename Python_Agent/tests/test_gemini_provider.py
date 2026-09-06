from types import SimpleNamespace
from unittest.mock import Mock

from models import gemini_provider


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

    assert result == response.text