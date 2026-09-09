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


def _assert_no_key_anywhere(value, banned_keys):
    if isinstance(value, dict):
        for key, item in value.items():
            assert key not in banned_keys, f"unsupported key {key!r} survived compatibility transform"
            _assert_no_key_anywhere(item, banned_keys)
    elif isinstance(value, list):
        for item in value:
            _assert_no_key_anywhere(item, banned_keys)


def test_compatibility_strips_minimum_maximum_in_nested_property():
    schema = {
        "type": "object",
        "properties": {
            "new_index": {"type": "integer", "minimum": 0, "maximum": 10},
        },
    }

    result = gemini_provider.make_gemini_schema_compatible(schema)

    assert result["properties"]["new_index"] == {"type": "integer"}
    assert "minimum" not in result["properties"]["new_index"]
    assert "maximum" not in result["properties"]["new_index"]


def test_compatibility_strips_minimum_maximum_in_anyof_branch():
    schema = {
        "anyOf": [
            {"type": "integer", "minimum": 1, "maximum": 5},
            {"type": "string"},
        ],
    }

    result = gemini_provider.make_gemini_schema_compatible(schema)

    assert result["anyOf"][0] == {"type": "integer"}
    assert result["anyOf"][1] == {"type": "string"}


def test_compatibility_strips_min_items_max_items_on_array():
    schema = {
        "type": "array",
        "items": {"type": "string"},
        "minItems": 1,
        "maxItems": 5,
    }

    result = gemini_provider.make_gemini_schema_compatible(schema)

    assert result == {"type": "array", "items": {"type": "string"}}
    assert "minItems" not in result
    assert "maxItems" not in result


def test_compatibility_still_removes_discriminator():
    schema = {
        "oneOf": [{"type": "object"}, {"type": "string"}],
        "discriminator": {"propertyName": "action"},
    }

    result = gemini_provider.make_gemini_schema_compatible(schema)

    assert "discriminator" not in result
    assert result["anyOf"] == [{"type": "object"}, {"type": "string"}]


def test_compatibility_preserves_supported_fields():
    schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["batch"]},
        },
        "anyOf": [{"$ref": "#/$defs/SomeAction"}],
    }

    result = gemini_provider.make_gemini_schema_compatible(schema)

    assert result["type"] == "object"
    assert result["properties"]["action"] == {"type": "string", "enum": ["batch"]}
    assert result["anyOf"] == [{"$ref": "#/$defs/SomeAction"}]


def test_compatibility_agent_decision_has_no_unsupported_keywords():
    from pydantic import TypeAdapter

    from agent.schemas import AgentDecision

    raw = TypeAdapter(AgentDecision).json_schema()
    result = gemini_provider.make_gemini_schema_compatible(raw)

    _assert_no_key_anywhere(
        result,
        {"minimum", "maximum", "minItems", "maxItems", "discriminator"},
    )


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