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


def test_gemini_disambiguates_count_nodes_schema():
    from agent.schemas import AgentDecision
    from pydantic import TypeAdapter

    schema = gemini_provider.make_gemini_schema_compatible(
        TypeAdapter(AgentDecision).json_schema()
    )
    schema_text = json.dumps(schema)

    assert "CountNodesAction" in schema_text
    assert "result_mode" in schema_text
    assert "#/$defs/CountNodesAction" not in schema_text

    batch_actions = schema["$defs"]["BatchAction"]["properties"][
        "actions"
    ]["items"]["anyOf"]
    assert not any(
        item.get("title")
        in gemini_provider.GEMINI_NESTED_BATCH_EXCLUDED_ACTIONS
        or item.get("$ref")
        in {
            "#/$defs/" + action_name
            for action_name in
            gemini_provider.GEMINI_NESTED_BATCH_EXCLUDED_ACTIONS
        }
        for item in batch_actions
    )



def test_gemini_excludes_overlapping_group_actions_from_nested_batch():
    """Regression test for the Gemini 400 INVALID_ARGUMENT bug that
    appears after adding structurally identical actions (add_to_group /
    remove_from_group) to the AgentDecision union.

    After the Gemini adapter removes the discriminator and converts
    oneOf to anyOf, AddToGroupAction and RemoveFromGroupAction present
    overlapping branches in the nested batch.actions union (same
    properties + required fields). Gemini rejects the entire request
    with 400 INVALID_ARGUMENT.

    The fix excludes both branches from the provider-only nested batch
    union while retaining them as valid standalone actions and in the
    public Pydantic schema.
    """
    from agent.schemas import AgentDecision
    from pydantic import TypeAdapter

    raw_schema = TypeAdapter(AgentDecision).json_schema()
    schema = gemini_provider.make_gemini_schema_compatible(raw_schema)
    schema_text = json.dumps(schema)

    # The normalized schema must not contain oneOf or discriminator.
    assert "oneOf" not in schema_text
    assert "discriminator" not in schema_text

    # Both actions must remain valid standalone actions (top-level union).
    assert "#/$defs/AddToGroupAction" in schema_text
    assert "#/$defs/RemoveFromGroupAction" in schema_text
    assert "AddToGroupAction" in schema["$defs"]
    assert "RemoveFromGroupAction" in schema["$defs"]

    # Both actions must be excluded from the nested batch.actions union.
    batch_actions = schema["$defs"]["BatchAction"]["properties"][
        "actions"
    ]["items"]["anyOf"]
    batch_titles = {
        item.get("title") for item in batch_actions if item.get("title")
    }
    batch_refs = {
        item.get("$ref") for item in batch_actions if item.get("$ref")
    }
    excluded = gemini_provider.GEMINI_NESTED_BATCH_EXCLUDED_ACTIONS
    for action_name in ("AddToGroupAction", "RemoveFromGroupAction"):
        assert action_name not in batch_titles
        assert f"#/$defs/{action_name}" not in batch_refs
        # And they must be in the exclusion set.
        assert action_name in excluded

    # MoveChildAction is available in the nested batch via $ref
    # (batch items use $ref, not title, so batch_titles is empty).
    # Check batch_refs for the $defs reference.
    assert "#/$defs/MoveChildAction" in batch_refs
    assert "MoveChildAction" not in excluded
    assert "MoveChildAction" not in gemini_provider.GEMINI_TOP_LEVEL_EXCLUDED_ACTIONS


def test_gemini_excludes_overlapping_signal_actions_from_nested_batch():
    """Regression guard for the same Gemini 400 INVALID_ARGUMENT
    overlap class as the group actions: connect_signal and
    disconnect_signal present structurally identical branches
    (same required fields; connect adds optional deferred), so both
    are excluded from the provider-only nested batch union while
    remaining valid standalone actions in the top-level union.
    """
    from agent.schemas import AgentDecision
    from pydantic import TypeAdapter

    raw_schema = TypeAdapter(AgentDecision).json_schema()
    schema = gemini_provider.make_gemini_schema_compatible(raw_schema)
    schema_text = json.dumps(schema)

    assert "oneOf" not in schema_text
    assert "discriminator" not in schema_text

    # Both actions remain valid standalone actions (top-level union).
    assert "#/$defs/ConnectSignalAction" in schema_text
    assert "#/$defs/DisconnectSignalAction" in schema_text
    assert "ConnectSignalAction" in schema["$defs"]
    assert "DisconnectSignalAction" in schema["$defs"]

    # Both actions are excluded from the nested batch.actions union.
    batch_actions = schema["$defs"]["BatchAction"]["properties"][
        "actions"
    ]["items"]["anyOf"]
    batch_refs = {
        item.get("$ref") for item in batch_actions if item.get("$ref")
    }
    excluded = gemini_provider.GEMINI_NESTED_BATCH_EXCLUDED_ACTIONS
    for action_name in ("ConnectSignalAction", "DisconnectSignalAction"):
        assert f"#/$defs/{action_name}" not in batch_refs
        assert action_name in excluded

    # The read-only connection inspector has no overlapping pair
    # beyond the existing {node_path}-only actions, so it stays in
    # the nested batch union like list_node_signals.
    assert "#/$defs/ListConnectionsAction" in batch_refs
    assert "ListConnectionsAction" not in excluded


def test_gemini_schema_accepts_script_actions_without_exclusions():
    """Rule 12 analysis record for the script tools batch.

    Structural analysis of the five new branches:
    - CreateScriptAction {script_path, content}: unique required set
      (a superset of find_nodes_by_script, a tolerated subset
      relation like delete_node under other mutations).
    - AttachScriptAction {node_path, script_path}: unique required
      set.
    - DetachScriptAction {node_path}: identical required set to the
      existing delete_node branch (tolerated precedent, live
      validated since Tool Expansion V2).
    - GetScriptContentAction {script_path}: identical required set to
      find_nodes_by_script (read-only identical pair, tolerated
      precedent like the {node_path}-only family).
    - ListScriptDiagnosticsAction {script_path}: same as above.

    Therefore NO nested-batch exclusions are added; the live Gemini
    smoke test is the authoritative gate (Rule 12), with the
    two-tier exclusion pattern as the documented fallback.
    """
    from agent.schemas import AgentDecision
    from pydantic import TypeAdapter

    raw_schema = TypeAdapter(AgentDecision).json_schema()
    schema = gemini_provider.make_gemini_schema_compatible(raw_schema)
    schema_text = json.dumps(schema)

    assert "oneOf" not in schema_text
    assert "discriminator" not in schema_text

    script_actions = [
        "CreateScriptAction",
        "AttachScriptAction",
        "DetachScriptAction",
        "GetScriptContentAction",
        "ListScriptDiagnosticsAction",
    ]

    # All five remain valid standalone actions (top-level union).
    for action_name in script_actions:
        assert f"#/$defs/{action_name}" in schema_text
        assert action_name in schema["$defs"]

    # All five remain in the nested batch.actions union (no
    # exclusions were added for this batch).
    batch_actions = schema["$defs"]["BatchAction"]["properties"][
        "actions"
    ]["items"]["anyOf"]
    batch_refs = {
        item.get("$ref") for item in batch_actions if item.get("$ref")
    }
    for action_name in script_actions:
        assert f"#/$defs/{action_name}" in batch_refs
        assert action_name not in gemini_provider.GEMINI_NESTED_BATCH_EXCLUDED_ACTIONS


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
