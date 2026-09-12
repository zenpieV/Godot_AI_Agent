import builtins
import json
import logging
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from pydantic import ValidationError

from agent.boundary import (
    check_decision_blocked,
    compute_action_fingerprint,
    extract_mutation_target,
)
from agent import registry as registry_module
from agent.schemas import (
    BatchAction,
    BatchableAction,
    ExitSessionAction,
    FinalAnswerAction,
    RenameNodeAction,
)
from agent.telemetry import (
    ProviderResult,
    SessionObservability,
    TokenUsage,
)


@pytest.fixture(scope="module")
def agent_module():
    """Import the real agent functions without starting a live provider call."""
    import models.gemini_provider as gemini_provider
    import models.groq_provider as groq_provider

    original_gemini = gemini_provider.ask_gemini
    original_groq = groq_provider.ask_groq
    original_input = builtins.input

    input_responses = iter(
        [
            "bootstrap import",
        ]
    )

    def bootstrap_input(prompt):
        try:
            return next(input_responses)
        except StopIteration as error:
            raise EOFError from error

    gemini_provider.ask_gemini = lambda **kwargs: json.dumps(
        {
            "action": "final_answer",
            "reason": "import bootstrap",
            "final_answer": "import complete",
        }
    )
    groq_provider.ask_groq = lambda **kwargs: json.dumps(
        {
            "action": "final_answer",
            "reason": "import bootstrap",
            "final_answer": "import complete",
        }
    )
    builtins.input = bootstrap_input

    try:
        import agent.godot_agent as godot_agent
        yield godot_agent
    finally:
        gemini_provider.ask_gemini = original_gemini
        groq_provider.ask_groq = original_groq
        builtins.input = original_input


def test_valid_structured_action_and_final_answer(agent_module):
    action = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "rename_node",
                "reason": "Use the known path.",
                "node_path": "Player",
                "new_name": "Hero",
            }
        )
    )
    final = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "final_answer",
                "reason": "The operation is complete.",
                "final_answer": "Done.",
            }
        )
    )

    assert isinstance(action, RenameNodeAction)
    assert isinstance(final, FinalAnswerAction)


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        '{"action": "rename_node", "reason": "missing path", "new_name": "Hero"}',
        '{"action": "does_not_exist", "reason": "invalid action"}',
    ],
)
def test_malformed_missing_and_invalid_actions_are_rejected(
    agent_module,
    payload,
):
    with pytest.raises(ValidationError):
        agent_module.AGENT_DECISION_ADAPTER.validate_json(payload)


def test_flattened_batch_actions_are_rejected_without_execution(
    agent_module,
    monkeypatch,
):
    """Regression: a flattened (non-object) batch "actions" array must
    be rejected by validation, never repaired, and never executed.

    Mirrors malformed Gemini output observed during live stress testing:
    each action object was flattened into a list of alternating field
    names and values. The live failure produced 25 string elements.
    """
    flattened_group = [
        "rename_node",
        "node_path",
        "Negatrix/Heatblast/HP",
        "new_name",
        "Health-60",
    ]
    malformed_payload = {
        "reason": "Stress-test flattened batch.",
        "action": "batch",
        "actions": flattened_group * 5,  # 25 elements, like the live failure
    }

    # Guard the execution boundary: if the malformed payload were ever
    # accepted or "repaired", neither the batch executor nor a mutation
    # tool handler may run.
    monkeypatch.setattr(
        agent_module,
        "execute_batch_actions",
        Mock(side_effect=AssertionError("malformed batch must not execute")),
    )
    monkeypatch.setattr(
        registry_module.scene_tools,
        "rename_node",
        Mock(side_effect=AssertionError("malformed batch must not execute")),
    )

    with pytest.raises(ValidationError, match="at most 5"):
        agent_module.AGENT_DECISION_ADAPTER.validate_json(
            json.dumps(malformed_payload)
        )

    # The malformed structure was not silently repaired or dispatched.
    agent_module.execute_batch_actions.assert_not_called()
    registry_module.scene_tools.rename_node.assert_not_called()


def test_valid_multi_action_batch_executes_in_order(
    agent_module,
    monkeypatch,
):
    """A properly structured batch of two complete action objects
    validates and executes both actions through the normal path."""
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "batch",
                "reason": "Rename two nodes.",
                "actions": [
                    {
                        "action": "rename_node",
                        "reason": "Rename Heatblast HP.",
                        "node_path": "Negatrix/Heatblast/HP",
                        "new_name": "Health-60",
                    },
                    {
                        "action": "rename_node",
                        "reason": "Rename Heatblast Attack.",
                        "node_path": "Negatrix/Heatblast/Attack",
                        "new_name": "Attack-100",
                    },
                ],
            }
        )
    )

    assert isinstance(decision, BatchAction)
    assert len(decision.actions) == 2

    mock_rename = Mock(return_value={"success": True})
    monkeypatch.setattr(
        registry_module.scene_tools,
        "rename_node",
        mock_rename,
    )

    result = agent_module.execute_batch_actions(
        decision,
        "Rename the two nodes.",
        logging.getLogger("valid-batch-test"),
    )

    assert result["success"] is True
    assert result["succeeded_count"] == 2
    assert mock_rename.call_count == 2
    assert mock_rename.call_args_list[0].kwargs == {
        "node_path": "Negatrix/Heatblast/HP",
        "new_name": "Health-60",
    }
    assert mock_rename.call_args_list[1].kwargs == {
        "node_path": "Negatrix/Heatblast/Attack",
        "new_name": "Attack-100",
    }


def test_invalid_action_arguments_are_rejected(agent_module):
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "set_properties",
                "reason": "Invalid property payload.",
                "node_path": "Player",
                "properties_json": "not json",
            }
        )
    )

    valid, error = agent_module.validate_agent_action(decision)

    assert valid is False
    assert "valid serialized JSON" in error


def test_validate_node_type_action_validates(agent_module):
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "validate_node_type",
                "reason": "Check before creating.",
                "node_type": "Node2D",
            }
        )
    )

    assert decision.action == "validate_node_type"

    valid, error = agent_module.validate_agent_action(decision)

    assert valid is True
    assert error == ""


def test_validate_node_type_blank_node_type_is_rejected(agent_module):
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "validate_node_type",
                "reason": "Blank type.",
                "node_type": "   ",
            }
        )
    )

    valid, error = agent_module.validate_agent_action(decision)

    assert valid is False
    assert "requires non-empty field(s): node_type" in error


def test_validate_node_type_is_batchable():
    """validate_node_type may appear as a batch item (read-only)."""
    from pydantic import TypeAdapter

    decision = TypeAdapter(BatchableAction).validate_json(
        json.dumps(
            {
                "action": "validate_node_type",
                "reason": "Pre-flight check inside a batch.",
                "node_type": "CharacterBody2D",
            }
        )
    )

    assert decision.action == "validate_node_type"


def test_list_available_node_types_action_validates(agent_module):
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "list_available_node_types",
                "reason": "Discover Node2D candidates.",
                "inherits_from": "Node2D",
                "name_contains": "Body",
                "limit": 10,
            }
        )
    )

    assert decision.action == "list_available_node_types"
    assert decision.inherits_from == "Node2D"
    assert decision.name_contains == "Body"
    assert decision.limit == 10

    valid, error = agent_module.validate_agent_action(decision)

    assert valid is True
    assert error == ""


def test_list_available_node_types_without_filters_validates(agent_module):
    """The bridge supplies the bounded default when filters are omitted."""
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "list_available_node_types",
                "reason": "Show a bounded set of node type candidates.",
            }
        )
    )

    assert decision.inherits_from is None
    assert decision.name_contains is None
    assert decision.limit is None
    assert agent_module.validate_agent_action(decision) == (True, "")


def test_list_available_node_types_limit_is_bounded_by_schema(agent_module):
    with pytest.raises(ValidationError, match="less than or equal to 100"):
        agent_module.AGENT_DECISION_ADAPTER.validate_json(
            json.dumps(
                {
                    "action": "list_available_node_types",
                    "reason": "Request too many names.",
                    "limit": 101,
                }
            )
        )


def test_list_available_node_types_is_batchable():
    from pydantic import TypeAdapter

    decision = TypeAdapter(BatchableAction).validate_json(
        json.dumps(
            {
                "action": "list_available_node_types",
                "reason": "Discover candidates before creating.",
                "name_contains": "Character",
            }
        )
    )

    assert decision.action == "list_available_node_types"


def test_list_available_node_types_bridge_result_passthrough(
    agent_module,
    monkeypatch,
):
    """The registry preserves ClassDB filtering semantics verbatim."""
    result_from_bridge = {
        "success": True,
        "action": "list_available_node_types",
        "inherits_from": "Node2D",
        "name_contains": "body",
        "limit": 10,
        "total_matches": 2,
        "truncated": False,
        "node_types": ["CharacterBody2D", "StaticBody2D"],
    }
    mock_list = Mock(return_value=result_from_bridge)
    monkeypatch.setattr(
        registry_module.scene_tools,
        "list_available_node_types",
        mock_list,
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "list_available_node_types",
                "reason": "Find body candidates under Node2D.",
                "inherits_from": "Node2D",
                "name_contains": "body",
                "limit": 10,
            }
        )
    )

    assert agent_module._execute_single_action(decision) == result_from_bridge
    mock_list.assert_called_once_with(
        inherits_from="Node2D",
        name_contains="body",
        limit=10,
    )


def test_list_available_node_types_bridge_failures_passthrough(
    agent_module,
    monkeypatch,
):
    """No matches and invalid filters remain distinguishable results."""
    no_matches = {
        "success": True,
        "action": "list_available_node_types",
        "inherits_from": "",
        "name_contains": "DefinitelyNotAType",
        "limit": 50,
        "total_matches": 0,
        "truncated": False,
        "node_types": [],
    }
    invalid_filter = {
        "success": False,
        "error": (
            "Invalid inherits_from filter: MissingBase is not a "
            "registered Godot class."
        ),
    }
    mock_list = Mock(side_effect=[no_matches, invalid_filter])
    monkeypatch.setattr(
        registry_module.scene_tools,
        "list_available_node_types",
        mock_list,
    )

    no_match_decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "list_available_node_types",
                "reason": "Check whether the name exists.",
                "name_contains": "DefinitelyNotAType",
            }
        )
    )
    invalid_filter_decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "list_available_node_types",
                "reason": "Filter by the requested base class.",
                "inherits_from": "MissingBase",
            }
        )
    )

    assert agent_module._execute_single_action(no_match_decision) == no_matches
    assert (
        agent_module._execute_single_action(invalid_filter_decision)
        == invalid_filter
    )


def test_get_node_property_action_validates(agent_module):
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "get_node_property",
                "reason": "Read one property.",
                "node_path": "Player",
                "property_name": "position",
            }
        )
    )

    assert decision.action == "get_node_property"
    assert decision.node_path == "Player"
    assert decision.property_name == "position"

    valid, error = agent_module.validate_agent_action(decision)

    assert valid is True
    assert error == ""


def test_get_node_property_blank_property_name_is_rejected(agent_module):
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "get_node_property",
                "reason": "Blank property.",
                "node_path": "Player",
                "property_name": "   ",
            }
        )
    )

    valid, error = agent_module.validate_agent_action(decision)

    assert valid is False
    assert "requires non-empty field(s): property_name" in error


def test_get_node_property_blank_node_path_is_rejected(agent_module):
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "get_node_property",
                "reason": "Blank path.",
                "node_path": "   ",
                "property_name": "position",
            }
        )
    )

    valid, error = agent_module.validate_agent_action(decision)

    assert valid is False
    assert "requires non-empty field(s): node_path" in error


def test_get_node_property_is_batchable():
    """get_node_property may appear as a batch item (read-only)."""
    from pydantic import TypeAdapter

    decision = TypeAdapter(BatchableAction).validate_json(
        json.dumps(
            {
                "action": "get_node_property",
                "reason": "Read two properties in one batch.",
                "node_path": "Player",
                "property_name": "visible",
            }
        )
    )

    assert decision.action == "get_node_property"


def test_get_node_property_bridge_failure_passthrough(
    agent_module,
    monkeypatch,
):
    """A bridge failure (missing node / missing property) is returned
    to the agent unchanged, with no tool execution and no exception
    wrapping."""
    from agent import registry as registry_module

    failure = {
        "success": False,
        "error": "Property not found: health on node Player.",
    }
    monkeypatch.setattr(
        registry_module.scene_tools,
        "get_node_property",
        Mock(return_value=failure),
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "get_node_property",
                "reason": "Read missing property.",
                "node_path": "Player",
                "property_name": "health",
            }
        )
    )

    result = agent_module._execute_single_action(decision)

    assert result == failure


def test_get_node_property_missing_node_failure_passthrough(
    agent_module,
    monkeypatch,
):
    """A missing-node bridge failure remains structured and unchanged."""
    failure = {
        "success": False,
        "error": "Node not found: MissingPlayer",
    }
    monkeypatch.setattr(
        registry_module.scene_tools,
        "get_node_property",
        Mock(return_value=failure),
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "get_node_property",
                "reason": "Read a missing node.",
                "node_path": "MissingPlayer",
                "property_name": "position",
            }
        )
    )

    assert agent_module._execute_single_action(decision) == failure


def test_get_node_property_bridge_success_passthrough(
    agent_module,
    monkeypatch,
):
    """A successful bridge response is returned to the agent with
    the property value from the actual node serialized by Godot."""
    from agent import registry as registry_module

    success = {
        "success": True,
        "action": "get_node_property",
        "node_path": "Player",
        "node_name": "Player",
        "node_type": "CharacterBody2D",
        "property_name": "position",
        "property_type": "Vector2",
        "property_type_id": 5,
        "editable": True,
        "value": {"type": "Vector2", "x": 100.0, "y": 200.0},
    }
    monkeypatch.setattr(
        registry_module.scene_tools,
        "get_node_property",
        Mock(return_value=success),
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "get_node_property",
                "reason": "Read one property.",
                "node_path": "Player",
                "property_name": "position",
            }
        )
    )

    result = agent_module._execute_single_action(decision)

    assert result["success"] is True
    assert result["property_name"] == "position"
    assert result["value"] == {"type": "Vector2", "x": 100.0, "y": 200.0}


def test_get_node_property_name_bridge_success_passthrough(
    agent_module,
    monkeypatch,
):
    """Node.name has a scalar StringName result and stays read-only."""
    success = {
        "success": True,
        "action": "get_node_property",
        "node_path": "Player",
        "node_name": "Player",
        "node_type": "CharacterBody2D",
        "property_name": "name",
        "property_type": "StringName",
        "property_type_id": 21,
        "editable": False,
        "value": "Player",
    }
    mock_property = Mock(return_value=success)
    monkeypatch.setattr(
        registry_module.scene_tools,
        "get_node_property",
        mock_property,
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "get_node_property",
                "reason": "Read the special Node name attribute.",
                "node_path": "Player",
                "property_name": "name",
            }
        )
    )

    result = agent_module._execute_single_action(decision)

    assert result == success
    mock_property.assert_called_once_with(
        node_path="Player",
        property_name="name",
    )


def test_get_node_class_info_action_validates(agent_module):
    """get_node_class_info accepts a class_name and validates."""
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "get_node_class_info",
                "reason": "Inspect the Node2D class.",
                "class_name": "Node2D",
            }
        )
    )
    assert decision.action == "get_node_class_info"
    assert decision.class_name == "Node2D"


def test_get_node_class_info_blank_class_name_is_rejected(agent_module):
    """Blank class_name fails Pydantic validation."""
    with pytest.raises(ValidationError):
        agent_module.AGENT_DECISION_ADAPTER.validate_json(
            json.dumps(
                {
                    "action": "get_node_class_info",
                    "reason": "Inspect a class.",
                    "class_name": "",
                }
            )
        )


def test_get_node_class_info_bridge_success_passthrough(
    agent_module,
    monkeypatch,
):
    """Bridge result for a valid class passes through unchanged."""
    success = {
        "success": True,
        "action": "get_node_class_info",
        "class_name": "Node2D",
        "base_class": "CanvasItem",
        "can_instantiate": True,
    }
    mock_info = Mock(return_value=success)
    monkeypatch.setattr(
        registry_module.scene_tools,
        "get_node_class_info",
        mock_info,
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "get_node_class_info",
                "reason": "Inspect Node2D.",
                "class_name": "Node2D",
            }
        )
    )

    result = agent_module._execute_single_action(decision)

    assert result == success
    mock_info.assert_called_once_with(
        class_name="Node2D",
    )


def test_get_node_class_info_unknown_class_failure_passthrough(
    agent_module,
    monkeypatch,
):
    """Bridge error for an unknown class passes through unchanged."""
    failure = {
        "success": False,
        "error": "'NotARealClass' is not a registered Godot class.",
    }
    mock_info = Mock(return_value=failure)
    monkeypatch.setattr(
        registry_module.scene_tools,
        "get_node_class_info",
        mock_info,
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "get_node_class_info",
                "reason": "Inspect an unknown class.",
                "class_name": "NotARealClass",
            }
        )
    )

    result = agent_module._execute_single_action(decision)

    assert result == failure
    mock_info.assert_called_once_with(
        class_name="NotARealClass",
    )


def test_get_node_class_info_is_batchable(agent_module):
    """get_node_class_info is a valid batch member."""
    batch = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "batch",
                "reason": "Inspect two classes.",
                "actions": [
                    {
                        "action": "get_node_class_info",
                        "reason": "Inspect Node2D.",
                        "class_name": "Node2D",
                    },
                    {
                        "action": "get_node_class_info",
                        "reason": "Inspect Node3D.",
                        "class_name": "Node3D",
                    },
                ],
            }
        )
    )
    assert batch.action == "batch"
    assert len(batch.actions) == 2
    assert all(
        item.action == "get_node_class_info"
        for item in batch.actions
    )


def test_list_node_signals_action_validates(agent_module):
    """list_node_signals accepts a node_path and validates."""
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "list_node_signals",
                "reason": "Inspect the signals on Player.",
                "node_path": "Player",
            }
        )
    )
    assert decision.action == "list_node_signals"
    assert decision.node_path == "Player"


def test_list_node_signals_missing_node_path_is_rejected(agent_module):
    """A missing/blank node_path fails required-field validation."""
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "list_node_signals",
                "reason": "Blank path.",
                "node_path": "   ",
            }
        )
    )

    valid, error = agent_module.validate_agent_action(decision)

    assert valid is False
    assert "requires non-empty field(s): node_path" in error


def test_list_node_signals_registry_dispatch_resolves(agent_module, monkeypatch):
    """The registry dispatches list_node_signals with its node_path."""
    mock_signals = Mock(return_value={"success": True})
    monkeypatch.setattr(
        registry_module.scene_tools,
        "list_node_signals",
        mock_signals,
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "list_node_signals",
                "reason": "Inspect signals.",
                "node_path": "Player",
            }
        )
    )

    result = agent_module._execute_single_action(decision)

    assert result == {"success": True}
    mock_signals.assert_called_once_with(node_path="Player")


def test_list_node_signals_bridge_success_passthrough(
    agent_module,
    monkeypatch,
):
    """Bridge result for a valid node passes through unchanged."""
    success = {
        "success": True,
        "action": "list_node_signals",
        "node_path": "Player",
        "node_name": "Player",
        "node_type": "Area2D",
        "total_signals": 2,
        "signals": [
            {
                "name": "area_entered",
                "args": [
                    {"name": "area", "type": "Object", "type_id": 24}
                ],
            },
            {
                "name": "tree_entered",
                "args": [],
            },
        ],
    }
    mock_signals = Mock(return_value=success)
    monkeypatch.setattr(
        registry_module.scene_tools,
        "list_node_signals",
        mock_signals,
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "list_node_signals",
                "reason": "Inspect Player signals.",
                "node_path": "Player",
            }
        )
    )

    result = agent_module._execute_single_action(decision)

    assert result == success
    mock_signals.assert_called_once_with(node_path="Player")


def test_list_node_signals_missing_node_failure_passthrough(
    agent_module,
    monkeypatch,
):
    """A missing-node bridge failure remains structured and unchanged."""
    failure = {
        "success": False,
        "error": "Node not found: MissingPlayer",
    }
    mock_signals = Mock(return_value=failure)
    monkeypatch.setattr(
        registry_module.scene_tools,
        "list_node_signals",
        mock_signals,
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "list_node_signals",
                "reason": "Inspect a missing node.",
                "node_path": "MissingPlayer",
            }
        )
    )

    result = agent_module._execute_single_action(decision)

    assert result == failure
    mock_signals.assert_called_once_with(node_path="MissingPlayer")


def test_list_node_signals_is_batchable(agent_module):
    """list_node_signals is a valid batch member."""
    batch = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "batch",
                "reason": "Inspect signals on two nodes.",
                "actions": [
                    {
                        "action": "list_node_signals",
                        "reason": "Inspect Player signals.",
                        "node_path": "Player",
                    },
                    {
                        "action": "list_node_signals",
                        "reason": "Inspect root signals.",
                        "node_path": ".",
                    },
                ],
            }
        )
    )
    assert batch.action == "batch"
    assert len(batch.actions) == 2
    assert all(
        item.action == "list_node_signals"
        for item in batch.actions
    )


def test_list_node_groups_action_validates(agent_module):
    """list_node_groups accepts a node_path and validates."""
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "list_node_groups",
                "reason": "Inspect the groups on Player.",
                "node_path": "Player",
            }
        )
    )
    assert decision.action == "list_node_groups"
    assert decision.node_path == "Player"


def test_list_node_groups_missing_node_path_is_rejected(agent_module):
    """A missing/blank node_path fails required-field validation."""
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "list_node_groups",
                "reason": "Blank path.",
                "node_path": "   ",
            }
        )
    )

    valid, error = agent_module.validate_agent_action(decision)

    assert valid is False
    assert "requires non-empty field(s): node_path" in error


def test_list_node_groups_registry_dispatch_resolves(agent_module, monkeypatch):
    """The registry dispatches list_node_groups with its node_path."""
    mock_groups = Mock(return_value={"success": True})
    monkeypatch.setattr(
        registry_module.scene_tools,
        "list_node_groups",
        mock_groups,
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "list_node_groups",
                "reason": "Inspect groups.",
                "node_path": "Player",
            }
        )
    )

    result = agent_module._execute_single_action(decision)

    assert result == {"success": True}
    mock_groups.assert_called_once_with(node_path="Player")


def test_list_node_groups_bridge_success_passthrough(
    agent_module,
    monkeypatch,
):
    """Bridge result for a valid node passes through unchanged."""
    success = {
        "success": True,
        "action": "list_node_groups",
        "node_path": "Player",
        "node_name": "Player",
        "node_type": "CharacterBody2D",
        "total_groups": 2,
        "groups": ["characters", "players"],
    }
    mock_groups = Mock(return_value=success)
    monkeypatch.setattr(
        registry_module.scene_tools,
        "list_node_groups",
        mock_groups,
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "list_node_groups",
                "reason": "Inspect Player groups.",
                "node_path": "Player",
            }
        )
    )

    result = agent_module._execute_single_action(decision)

    assert result == success
    mock_groups.assert_called_once_with(node_path="Player")


def test_list_node_groups_missing_node_failure_passthrough(
    agent_module,
    monkeypatch,
):
    """A missing-node bridge failure remains structured and unchanged."""
    failure = {
        "success": False,
        "error": "Node not found: MissingPlayer",
    }
    mock_groups = Mock(return_value=failure)
    monkeypatch.setattr(
        registry_module.scene_tools,
        "list_node_groups",
        mock_groups,
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "list_node_groups",
                "reason": "Inspect a missing node.",
                "node_path": "MissingPlayer",
            }
        )
    )

    result = agent_module._execute_single_action(decision)

    assert result == failure
    mock_groups.assert_called_once_with(node_path="MissingPlayer")


def test_list_node_groups_is_batchable(agent_module):
    """list_node_groups is a valid batch member."""
    batch = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "batch",
                "reason": "Inspect groups on two nodes.",
                "actions": [
                    {
                        "action": "list_node_groups",
                        "reason": "Inspect Player groups.",
                        "node_path": "Player",
                    },
                    {
                        "action": "list_node_groups",
                        "reason": "Inspect root groups.",
                        "node_path": ".",
                    },
                ],
            }
        )
    )
    assert batch.action == "batch"
    assert len(batch.actions) == 2
    assert all(
        item.action == "list_node_groups"
        for item in batch.actions
    )


def test_count_nodes_action_validates(agent_module):
    """count_nodes accepts a minimal request."""
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "count_nodes",
                "reason": "Count the enemies.",
                "node_name": "Enemy",
            }
        )
    )
    assert decision.action == "count_nodes"
    assert decision.node_name == "Enemy"


def test_count_nodes_accepts_all_supported_filters(agent_module):
    """count_nodes accepts the full shared filter shape."""
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "count_nodes",
                "reason": "Count triggers.",
                "node_name": "Trigger",
                "node_type": "Area2D",
                "parent_path": "Level",
                "name_match": "starts_with",
            }
        )
    )
    assert decision.node_type == "Area2D"
    assert decision.parent_path == "Level"
    assert decision.name_match == "starts_with"


def test_count_nodes_rejects_unsupported_name_match(agent_module):
    """An unsupported name_match mode fails Pydantic validation."""
    with pytest.raises(ValidationError):
        agent_module.AGENT_DECISION_ADAPTER.validate_json(
            json.dumps(
                {
                    "action": "count_nodes",
                    "reason": "Bad mode.",
                    "node_name": "Enemy",
                    "name_match": "regex",
                }
            )
        )


def test_count_nodes_registry_dispatch_resolves(agent_module, monkeypatch):
    """The registry dispatches count_nodes with the shared filters."""
    mock_count = Mock(return_value={"success": True, "count": 1})
    monkeypatch.setattr(
        registry_module.scene_tools,
        "count_nodes",
        mock_count,
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "count_nodes",
                "reason": "Count enemies.",
                "node_name": "Enemy",
                "node_type": "Area2D",
                "parent_path": "Level",
                "name_match": "contains",
            }
        )
    )

    result = agent_module._execute_single_action(decision)

    assert result == {"success": True, "count": 1}
    mock_count.assert_called_once_with(
        node_name="Enemy",
        node_type="Area2D",
        parent_path="Level",
        name_match="contains",
        include_subclasses=False,
    )


def test_count_nodes_bridge_success_passthrough(
    agent_module,
    monkeypatch,
):
    """Bridge count result passes through unchanged."""
    success = {
        "success": True,
        "action": "count_nodes",
        "count": 5,
        "node_name_filter": "Enemy",
        "node_type_filter": "Area2D",
        "parent_path_filter": "Level",
        "name_match": "exact",
    }
    mock_count = Mock(return_value=success)
    monkeypatch.setattr(
        registry_module.scene_tools,
        "count_nodes",
        mock_count,
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "count_nodes",
                "reason": "Count enemies.",
                "node_name": "Enemy",
                "node_type": "Area2D",
                "parent_path": "Level",
            }
        )
    )

    result = agent_module._execute_single_action(decision)

    assert result == success
    mock_count.assert_called_once_with(
        node_name="Enemy",
        node_type="Area2D",
        parent_path="Level",
        name_match="exact",
        include_subclasses=False,
    )


def test_count_nodes_missing_parent_failure_passthrough(
    agent_module,
    monkeypatch,
):
    """A missing-parent bridge failure remains structured and unchanged."""
    failure = {
        "success": False,
        "error": "Parent node not found: MissingLevel. "
        "Node not found: MissingLevel",
    }
    mock_count = Mock(return_value=failure)
    monkeypatch.setattr(
        registry_module.scene_tools,
        "count_nodes",
        mock_count,
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "count_nodes",
                "reason": "Count under a missing parent.",
                "parent_path": "MissingLevel",
            }
        )
    )

    result = agent_module._execute_single_action(decision)

    assert result == failure
    mock_count.assert_called_once_with(
        node_name=None,
        node_type=None,
        parent_path="MissingLevel",
        name_match="exact",
        include_subclasses=False,
    )


def test_count_nodes_is_batchable(agent_module):
    """count_nodes is a valid batch member."""
    batch = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "batch",
                "reason": "Count two kinds of nodes.",
                "actions": [
                    {
                        "action": "count_nodes",
                        "reason": "Count enemies.",
                        "node_name": "Enemy",
                    },
                    {
                        "action": "count_nodes",
                        "reason": "Count triggers.",
                        "node_type": "Area2D",
                    },
                ],
            }
        )
    )
    assert batch.action == "batch"
    assert len(batch.actions) == 2
    assert all(
        item.action == "count_nodes"
        for item in batch.actions
    )


def test_find_nodes_by_script_action_validates(agent_module):
    """find_nodes_by_script accepts a script_path and validates."""
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "find_nodes_by_script",
                "reason": "Find nodes using player.gd.",
                "script_path": "res://scripts/player.gd",
            }
        )
    )
    assert decision.action == "find_nodes_by_script"
    assert decision.script_path == "res://scripts/player.gd"


def test_find_nodes_by_script_blank_script_path_is_rejected(agent_module):
    """A blank script_path fails required-field validation."""
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "find_nodes_by_script",
                "reason": "Blank path.",
                "script_path": "   ",
            }
        )
    )

    valid, error = agent_module.validate_agent_action(decision)

    assert valid is False
    assert "requires non-empty field(s): script_path" in error


def test_find_nodes_by_script_registry_dispatch_resolves(
    agent_module,
    monkeypatch,
):
    """The registry dispatches find_nodes_by_script with its script_path."""
    mock_find = Mock(return_value={"success": True, "count": 0})
    monkeypatch.setattr(
        registry_module.scene_tools,
        "find_nodes_by_script",
        mock_find,
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "find_nodes_by_script",
                "reason": "Find scripted nodes.",
                "script_path": "res://scripts/enemy.gd",
            }
        )
    )

    result = agent_module._execute_single_action(decision)

    assert result == {"success": True, "count": 0}
    mock_find.assert_called_once_with(
        script_path="res://scripts/enemy.gd"
    )


def test_find_nodes_by_script_bridge_success_passthrough(
    agent_module,
    monkeypatch,
):
    """Bridge result for a matching script passes through unchanged."""
    success = {
        "success": True,
        "action": "find_nodes_by_script",
        "script_path": "res://scripts/player.gd",
        "count": 2,
        "nodes": [
            {
                "name": "Player",
                "node_type": "CharacterBody2D",
                "path": "Player",
                "is_root": False,
            },
            {
                "name": "Player2",
                "node_type": "CharacterBody2D",
                "path": "Player2",
                "is_root": False,
            },
        ],
    }
    mock_find = Mock(return_value=success)
    monkeypatch.setattr(
        registry_module.scene_tools,
        "find_nodes_by_script",
        mock_find,
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "find_nodes_by_script",
                "reason": "Find player script users.",
                "script_path": "res://scripts/player.gd",
            }
        )
    )

    result = agent_module._execute_single_action(decision)

    assert result == success
    mock_find.assert_called_once_with(
        script_path="res://scripts/player.gd"
    )


def test_find_nodes_by_script_zero_match_is_not_an_error(
    agent_module,
    monkeypatch,
):
    """A zero-match bridge result passes through as success."""
    zero = {
        "success": True,
        "action": "find_nodes_by_script",
        "script_path": "res://scripts/nobody.gd",
        "count": 0,
        "nodes": [],
    }
    mock_find = Mock(return_value=zero)
    monkeypatch.setattr(
        registry_module.scene_tools,
        "find_nodes_by_script",
        mock_find,
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "find_nodes_by_script",
                "reason": "Look for an unused script.",
                "script_path": "res://scripts/nobody.gd",
            }
        )
    )

    result = agent_module._execute_single_action(decision)

    assert result == zero
    assert result["count"] == 0


def test_find_nodes_by_script_is_batchable(agent_module):
    """find_nodes_by_script is a valid batch member."""
    batch = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "batch",
                "reason": "Inspect two scripts.",
                "actions": [
                    {
                        "action": "find_nodes_by_script",
                        "reason": "Find player.gd users.",
                        "script_path": "res://scripts/player.gd",
                    },
                    {
                        "action": "find_nodes_by_script",
                        "reason": "Find enemy.gd users.",
                        "script_path": "enemy.gd",
                    },
                ],
            }
        )
    )
    assert batch.action == "batch"
    assert len(batch.actions) == 2
    assert all(
        item.action == "find_nodes_by_script"
        for item in batch.actions
    )


def test_find_nodes_by_group_action_validates(agent_module):
    """find_nodes_by_group accepts a group_name and validates."""
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "find_nodes_by_group",
                "reason": "Find nodes in the enemies group.",
                "group_name": "enemies",
            }
        )
    )
    assert decision.action == "find_nodes_by_group"
    assert decision.group_name == "enemies"


def test_find_nodes_by_group_blank_group_name_is_rejected(agent_module):
    """A blank group_name fails required-field validation."""
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "find_nodes_by_group",
                "reason": "Blank group.",
                "group_name": "   ",
            }
        )
    )

    valid, error = agent_module.validate_agent_action(decision)

    assert valid is False
    assert "requires non-empty field(s): group_name" in error


def test_find_nodes_by_group_registry_dispatch_resolves(
    agent_module,
    monkeypatch,
):
    """The registry dispatches find_nodes_by_group with its group_name."""
    mock_find = Mock(return_value={"success": True, "count": 0})
    monkeypatch.setattr(
        registry_module.scene_tools,
        "find_nodes_by_group",
        mock_find,
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "find_nodes_by_group",
                "reason": "Find group members.",
                "group_name": "hostile",
            }
        )
    )

    result = agent_module._execute_single_action(decision)

    assert result == {"success": True, "count": 0}
    mock_find.assert_called_once_with(group_name="hostile")


def test_find_nodes_by_group_bridge_success_passthrough(
    agent_module,
    monkeypatch,
):
    """Bridge result for a matching group passes through unchanged."""
    success = {
        "success": True,
        "action": "find_nodes_by_group",
        "group_name": "enemies",
        "count": 2,
        "nodes": [
            {
                "name": "Enemy",
                "node_type": "Area2D",
                "path": "Enemy",
                "is_root": False,
            },
            {
                "name": "Enemy2",
                "node_type": "Area2D",
                "path": "Enemy2",
                "is_root": False,
            },
        ],
    }
    mock_find = Mock(return_value=success)
    monkeypatch.setattr(
        registry_module.scene_tools,
        "find_nodes_by_group",
        mock_find,
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "find_nodes_by_group",
                "reason": "Find enemies group members.",
                "group_name": "enemies",
            }
        )
    )

    result = agent_module._execute_single_action(decision)

    assert result == success
    mock_find.assert_called_once_with(group_name="enemies")


def test_find_nodes_by_group_zero_match_is_not_an_error(
    agent_module,
    monkeypatch,
):
    """A zero-match bridge result passes through as success."""
    zero = {
        "success": True,
        "action": "find_nodes_by_group",
        "group_name": "empty_group",
        "count": 0,
        "nodes": [],
    }
    mock_find = Mock(return_value=zero)
    monkeypatch.setattr(
        registry_module.scene_tools,
        "find_nodes_by_group",
        mock_find,
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "find_nodes_by_group",
                "reason": "Look for an unused group.",
                "group_name": "empty_group",
            }
        )
    )

    result = agent_module._execute_single_action(decision)

    assert result == zero
    assert result["count"] == 0


def test_find_nodes_by_group_is_batchable(agent_module):
    """find_nodes_by_group is a valid batch member."""
    batch = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "batch",
                "reason": "Inspect two groups.",
                "actions": [
                    {
                        "action": "find_nodes_by_group",
                        "reason": "Find enemies group members.",
                        "group_name": "enemies",
                    },
                    {
                        "action": "find_nodes_by_group",
                        "reason": "Find players group members.",
                        "group_name": "players",
                    },
                ],
            }
        )
    )
    assert batch.action == "batch"
    assert len(batch.actions) == 2
    assert all(
        item.action == "find_nodes_by_group"
        for item in batch.actions
    )


def test_get_project_settings_names_validates(agent_module):
    """get_project_settings accepts exact setting_names."""
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "get_project_settings",
                "reason": "Inspect window size.",
                "setting_names": [
                    "display/window/size/viewport_width",
                    "display/window/size/viewport_height",
                ],
            }
        )
    )
    assert decision.action == "get_project_settings"
    assert decision.setting_names == [
        "display/window/size/viewport_width",
        "display/window/size/viewport_height",
    ]
    assert decision.prefix is None


def test_get_project_settings_prefix_validates(agent_module):
    """get_project_settings accepts a prefix and optional limit."""
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "get_project_settings",
                "reason": "Inspect window settings.",
                "prefix": "display/window/size/",
                "limit": 5,
            }
        )
    )
    assert decision.prefix == "display/window/size/"
    assert decision.limit == 5


def test_get_project_settings_invalid_limit_is_rejected(agent_module):
    """A limit outside 1-100 fails Pydantic validation."""
    with pytest.raises(ValidationError):
        agent_module.AGENT_DECISION_ADAPTER.validate_json(
            json.dumps(
                {
                    "action": "get_project_settings",
                    "reason": "Bad limit.",
                    "prefix": "display/",
                    "limit": 5000,
                }
            )
        )


def test_get_project_settings_bridge_success_passthrough(
    agent_module,
    monkeypatch,
):
    """Bridge result for exact names passes through unchanged."""
    success = {
        "success": True,
        "action": "get_project_settings",
        "setting_names": [
            "display/window/size/viewport_width",
            "display/window/size/viewport_height",
        ],
        "prefix": "",
        "settings": {
            "display/window/size/viewport_width": 1280,
            "display/window/size/viewport_height": 720,
        },
        "missing": ["definitely/not/a/setting"],
        "redacted": [],
    }
    mock_get = Mock(return_value=success)
    monkeypatch.setattr(
        registry_module.scene_tools,
        "get_project_settings",
        mock_get,
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "get_project_settings",
                "reason": "Inspect window size.",
                "setting_names": [
                    "display/window/size/viewport_width",
                    "display/window/size/viewport_height",
                    "definitely/not/a/setting",
                ],
            }
        )
    )

    result = agent_module._execute_single_action(decision)

    assert result == success
    mock_get.assert_called_once_with(
        setting_names=[
            "display/window/size/viewport_width",
            "display/window/size/viewport_height",
            "definitely/not/a/setting",
        ],
        prefix=None,
        limit=None,
    )


def test_get_project_settings_prefix_metadata_passthrough(
    agent_module,
    monkeypatch,
):
    """Bridge prefix result metadata passes through unchanged."""
    success = {
        "success": True,
        "action": "get_project_settings",
        "setting_names": [],
        "prefix": "display/window/size/",
        "settings": {
            "display/window/size/viewport_width": 1280,
            "display/window/size/viewport_height": 720,
        },
        "missing": [],
        "redacted": [],
        "total_matches": 8,
        "returned_matches": 8,
        "truncated": False,
    }
    mock_get = Mock(return_value=success)
    monkeypatch.setattr(
        registry_module.scene_tools,
        "get_project_settings",
        mock_get,
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "get_project_settings",
                "reason": "Inspect window size.",
                "prefix": "display/window/size/",
            }
        )
    )

    result = agent_module._execute_single_action(decision)

    assert result == success
    assert result["truncated"] is False


def test_get_project_settings_is_batchable(agent_module):
    """get_project_settings is a valid batch member."""
    batch = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "batch",
                "reason": "Inspect two settings.",
                "actions": [
                    {
                        "action": "get_project_settings",
                        "reason": "Inspect renderer.",
                        "setting_names": ["rendering/renderer/rendering_method"],
                    },
                    {
                        "action": "get_project_settings",
                        "reason": "Inspect window size.",
                        "prefix": "display/window/size/",
                    },
                ],
            }
        )
    )
    assert batch.action == "batch"
    assert len(batch.actions) == 2
    assert all(
        item.action == "get_project_settings"
        for item in batch.actions
    )


@pytest.mark.parametrize(
    "action_name",
    [
        "list_autoloads",
        "get_editor_state",
        "list_scenes_in_project",
        "get_undo_history_summary",
    ],
)
def test_project_inspection_actions_validate_and_are_batchable(
    agent_module,
    action_name,
):
    payload = {
        "action": action_name,
        "reason": "Inspect the project.",
    }
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(payload)
    )
    assert decision.action == action_name
    assert agent_module.validate_agent_action(decision) == (True, "")

    batch = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "batch",
                "reason": "Inspect project state.",
                "actions": [payload],
            }
        )
    )
    assert batch.actions[0].action == action_name


@pytest.mark.parametrize(
    "action_name",
    [
        "list_autoloads",
        "get_editor_state",
        "list_scenes_in_project",
        "get_undo_history_summary",
    ],
)
def test_project_inspection_bridge_success_and_failure_passthrough(
    agent_module,
    monkeypatch,
    action_name,
):
    success = {"success": True, "action": action_name}
    failure = {"success": False, "action": action_name, "error": "unavailable"}
    mock_tool = Mock(side_effect=[success, failure])
    monkeypatch.setattr(registry_module.scene_tools, action_name, mock_tool)

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": action_name,
                "reason": "Inspect project state.",
            }
        )
    )

    assert agent_module._execute_single_action(decision) == success
    assert agent_module._execute_single_action(decision) == failure
    mock_tool.assert_has_calls([call(), call()])


def test_missing_reason_normalized_to_placeholder(agent_module):
    """Some providers omit the mandatory reason field on an
    otherwise valid decision (observed live with
    glm-4.7-flash). Normalization injects a deterministic
    placeholder; everything else still validates strictly."""
    normalized = agent_module.normalize_agent_response(
        json.dumps(
            {
                "action": "final_answer",
                "final_answer": "Yes, I can hear you.",
            }
        )
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        normalized
    )

    assert decision.action == "final_answer"
    assert decision.final_answer == "Yes, I can hear you."
    assert decision.reason == "(no reason provided by the model)"


def test_blank_reason_normalized_to_placeholder(agent_module):
    normalized = agent_module.normalize_agent_response(
        json.dumps(
            {
                "action": "get_scene_tree",
                "reason": "   ",
            }
        )
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        normalized
    )

    assert decision.action == "get_scene_tree"
    assert decision.reason == "(no reason provided by the model)"


def test_nested_parameters_normalize_then_validate(agent_module):
    normalized = agent_module.normalize_agent_response(
        json.dumps(
            {
                "action": "create_node",
                "reason": "Create the requested node.",
                "parameters": {
                    "parent_path": ".",
                    "node_type": "Node2D",
                    "node_name": "Probe",
                },
            }
        )
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(normalized)

    assert decision.action == "create_node"
    assert decision.parent_path == "."


def test_provider_error_propagates_through_ask_model(agent_module, monkeypatch):
    provider_error = RuntimeError("provider unavailable")
    monkeypatch.setattr(agent_module, "MODEL_PROVIDER", "gemini")
    monkeypatch.setattr(
        agent_module,
        "ask_gemini",
        Mock(side_effect=provider_error),
    )

    with pytest.raises(RuntimeError, match="provider unavailable"):
        agent_module.ask_model([])


def test_tool_result_continuation_and_multi_step_decisions(agent_module, monkeypatch):
    responses = iter(
        [
            json.dumps(
                {
                    "action": "find_nodes",
                    "reason": "Locate the target.",
                    "node_name": "Player",
                }
            ),
            json.dumps(
                {
                    "action": "final_answer",
                    "reason": "The result identifies the target.",
                    "final_answer": "Player is at Player.",
                }
            ),
        ]
    )
    provider = Mock(side_effect=lambda **kwargs: next(responses))
    monkeypatch.setattr(agent_module, "MODEL_PROVIDER", "gemini")
    monkeypatch.setattr(agent_module, "ask_gemini", provider)

    conversation = [
        {"role": "user", "content": "Find Player."},
    ]
    first = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        agent_module.ask_model(conversation)
    )
    conversation.extend(
        [
            {"role": "assistant", "content": first.model_dump_json()},
            {
                "role": "tool",
                "content": json.dumps(
                    {
                        "success": True,
                        "nodes": [{"path": "Player"}],
                    }
                ),
            },
        ]
    )
    second = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        agent_module.ask_model(conversation)
    )

    assert first.action == "find_nodes"
    assert second.action == "final_answer"
    assert provider.call_count == 2
    assert provider.call_args_list[1].kwargs["conversation"][-1]["role"] == "tool"


def test_zai_provider_selected_through_ask_model(agent_module, monkeypatch):
    captured = {}

    def fake_ask_zai(**kwargs):
        captured["conversation"] = kwargs["conversation"]
        return ProviderResult(text='{"action":"final_answer"}')

    monkeypatch.setattr(agent_module, "MODEL_PROVIDER", "zai")
    monkeypatch.setattr(agent_module, "ask_zai", fake_ask_zai)

    result = agent_module.ask_model([])

    assert result == '{"action":"final_answer"}'
    assert captured["conversation"] == []


def test_selected_model_reaches_provider_call(agent_module, monkeypatch):
    """Regression: the panel's model selection used to change only
    the telemetry label while the adapter still called the settings
    default model."""
    captured = {}

    def fake_ask_gemini(**kwargs):
        captured["model"] = kwargs.get("model")
        return ProviderResult(text='{"action":"final_answer"}')

    monkeypatch.setattr(agent_module, "MODEL_PROVIDER", "gemini")
    monkeypatch.setattr(agent_module, "ACTIVE_PROVIDER", None)
    monkeypatch.setattr(agent_module, "ACTIVE_MODEL", "gemini-9.9-panel-pick")
    monkeypatch.setattr(agent_module, "ask_gemini", fake_ask_gemini)

    agent_module.ask_model([])

    assert captured["model"] == "gemini-9.9-panel-pick"


def test_unset_model_selection_falls_back_to_settings_default(
    agent_module, monkeypatch
):
    captured = {}

    def fake_ask_gemini(**kwargs):
        captured["model"] = kwargs.get("model")
        return ProviderResult(text='{"action":"final_answer"}')

    monkeypatch.setattr(agent_module, "MODEL_PROVIDER", "gemini")
    monkeypatch.setattr(agent_module, "ACTIVE_MODEL", None)
    monkeypatch.setattr(agent_module, "ask_gemini", fake_ask_gemini)

    agent_module.ask_model([])

    assert captured["model"] == agent_module.GEMINI_MODEL


def test_agent_session_keeps_state_across_user_turns(agent_module, monkeypatch):
    conversation = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "first turn"},
    ]
    session = agent_module.AgentSession(
        conversation,
        logging.getLogger("agent-session-test"),
        "first turn",
    )
    session.execution_result_records.append(
        {"step": 1, "action": "create_node"}
    )
    session.blocked_skipped_actions.append(
        {"action": "rename_node"}
    )

    monkeypatch.setattr(
        builtins,
        "input",
        lambda prompt: "second turn",
    )

    steps = session.iter_steps(3)
    assert next(steps) == 0

    session.complete_turn()

    assert next(steps) == 0
    assert session.current_request == "second turn"
    assert len(session.execution_result_records) == 1
    assert len(session.blocked_skipped_actions) == 1
    assert conversation[-1]["role"] == "user"
    assert "second turn" in conversation[-1]["content"]
    assert "BEGIN ACTIVE USER TURN 2" in conversation[-1]["content"]
    assert "do not repeat or re-answer" in conversation[-1]["content"]

    session.closed = True


def test_completed_final_answer_is_marked_as_historical_context(
    agent_module,
):
    conversation = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "first turn"},
    ]
    session = agent_module.AgentSession(
        conversation,
        logging.getLogger("agent-session-history-test"),
        "first turn",
    )
    from agent.schemas import FinalAnswerAction

    final_decision = FinalAnswerAction(
        reason="Finished the request.",
        action="final_answer",
        final_answer="Created Player.",
    )

    session.complete_turn(final_decision)

    assert "Created Player." in conversation[-2]["content"]
    assert "historical context only" in conversation[-1]["content"]


def test_agent_session_termination_preserves_state(agent_module):
    conversation = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "current turn"},
    ]
    execution_history = [
        {"step": 1, "action": "create_node"},
    ]
    blocked_actions = [
        {"action": "rename_node"},
    ]
    session = agent_module.AgentSession(
        conversation,
        logging.getLogger("agent-session-termination-test"),
        "current turn",
    )
    session.execution_result_records.extend(execution_history)
    session.blocked_skipped_actions.extend(blocked_actions)

    session.terminate()

    assert session.closed is True
    assert session.conversation is conversation
    assert session.execution_result_records == execution_history
    assert session.blocked_skipped_actions == blocked_actions


def test_terminated_session_does_not_begin_another_turn(
    agent_module,
    monkeypatch,
):
    session = agent_module.AgentSession(
        [{"role": "user", "content": "current turn"}],
        logging.getLogger("agent-session-closed-test"),
        "current turn",
    )
    session.terminate()
    input_mock = Mock(side_effect=AssertionError("input was called"))
    monkeypatch.setattr(builtins, "input", input_mock)

    steps = session.iter_steps(3)

    with pytest.raises(StopIteration):
        next(steps)

    input_mock.assert_not_called()


def test_exit_command_terminates_without_prompting_again(
    agent_module,
    monkeypatch,
):
    session = agent_module.AgentSession(
        [{"role": "user", "content": "current turn"}],
        logging.getLogger("agent-session-exit-command-test"),
        "current turn",
    )
    inputs = iter([agent_module.AgentSession.TERMINATION_COMMAND])
    monkeypatch.setattr(builtins, "input", lambda prompt: next(inputs))

    assert session.begin_next_turn() is False
    assert session.closed is True


def test_context_compaction_uses_existing_implementation(agent_module):
    logger = logging.getLogger("provider-contract-test")
    conversation = [
        {"role": "tool", "content": "x" * 1000},
        {"role": "tool", "content": "y" * 1000},
        {"role": "tool", "content": "z" * 1000},
    ]
    records = [
        {
            "step": index,
            "action": "find_nodes",
            "conversation_index": index,
            "tool_result": {"success": True, "nodes": []},
            "compacted": False,
        }
        for index in range(3)
    ]

    agent_module.compact_conversation(conversation, records, logger)

    assert "AGENT EXECUTION RESULT SUMMARY" in conversation[0]["content"]
    assert conversation[1]["content"] == "y" * 1000
    assert conversation[2]["content"] == "z" * 1000


def test_batch_boundary_blocks_exact_and_same_target_resume():
    skipped = RenameNodeAction(
        action="rename_node",
        reason="skipped",
        node_path="Player",
        new_name="SkippedName",
    )
    blocked = [
        {
            "fingerprint": compute_action_fingerprint(skipped),
            "mutation_target": extract_mutation_target(skipped),
            "action": skipped.action,
            "batch_index": 2,
            "batch_size": 2,
        }
    ]

    exact_blocked, _, _ = check_decision_blocked(skipped, blocked)
    bypass_blocked, _, _ = check_decision_blocked(
        skipped.model_copy(update={"new_name": "DifferentName"}),
        blocked,
    )
    recovery_allowed, _, _ = check_decision_blocked(
        agent_module_find_nodes(),
        blocked,
    )

    assert exact_blocked is True
    assert bypass_blocked is True
    assert recovery_allowed is False


def agent_module_find_nodes():
    from agent.schemas import FindNodesAction

    return FindNodesAction(
        action="find_nodes",
        reason="inspect",
        node_name="Player",
    )


def test_exit_session_action_validates(agent_module):
    """ExitSessionAction validates successfully."""
    action = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "exit_session",
                "reason": "session complete",
                "exit_summary": "All tasks finished.",
            }
        )
    )
    assert isinstance(action, ExitSessionAction)
    assert action.action == "exit_session"
    assert action.exit_summary == "All tasks finished."


def test_exit_session_requires_exit_summary(agent_module):
    """exit_summary is required for exit_session."""
    with pytest.raises(ValidationError):
        agent_module.AGENT_DECISION_ADAPTER.validate_json(
            json.dumps(
                {
                    "action": "exit_session",
                    "reason": "done",
                }
            )
        )


def test_exit_session_is_valid_agent_decision(agent_module):
    """exit_session is accepted as a valid AgentDecision."""
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "exit_session",
                "reason": "work complete",
                "exit_summary": "Done.",
            }
        )
    )
    assert decision.action == "exit_session"


def test_exit_session_closes_session(agent_module):
    """exit_session closes an active AgentSession."""
    session = agent_module.AgentSession(
        [{"role": "user", "content": "current turn"}],
        logging.getLogger("exit-session-close-test"),
        "current turn",
    )
    assert session.closed is False

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "exit_session",
                "reason": "done",
                "exit_summary": "Session complete.",
            }
        )
    )

    # Simulate the dispatch: terminate and continue
    session.terminate()

    assert session.closed is True
    assert session.turn_completed is False


def test_exit_session_does_not_begin_another_turn(
    agent_module,
    monkeypatch,
):
    """exit_session does not prompt for another user turn."""
    session = agent_module.AgentSession(
        [{"role": "user", "content": "current turn"}],
        logging.getLogger("exit-session-no-turn-test"),
        "current turn",
    )
    session.terminate()
    input_mock = Mock(side_effect=AssertionError("input was called"))
    monkeypatch.setattr(builtins, "input", input_mock)

    steps = session.iter_steps(3)

    with pytest.raises(StopIteration):
        next(steps)

    input_mock.assert_not_called()


def test_final_answer_leaves_session_open(
    agent_module,
    monkeypatch,
):
    """final_answer completes the turn but leaves the session open."""
    session = agent_module.AgentSession(
        [{"role": "user", "content": "current turn"}],
        logging.getLogger("final-answer-open-test"),
        "current turn",
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "final_answer",
                "reason": "done",
                "final_answer": "Done.",
            }
        )
    )

    assert decision.action == "final_answer"

    # Simulate dispatch: complete_turn, then continue
    session.complete_turn()
    assert session.turn_completed is True
    assert session.closed is False

    # Now iter_steps would call begin_next_turn, which prompts
    inputs = iter(["next request"])
    monkeypatch.setattr(builtins, "input", lambda prompt: next(inputs))

    steps = session.iter_steps(3)
    # The generator should be able to produce a step
    # because the session is not closed
    try:
        next(steps)
    except StopIteration:
        pytest.fail(
            "iter_steps should not exhaust when session is open"
        )


def test_exit_command_still_terminates(agent_module, monkeypatch):
    """/exit still terminates the session."""
    session = agent_module.AgentSession(
        [{"role": "user", "content": "current turn"}],
        logging.getLogger("exit-command-test"),
        "current turn",
    )
    inputs = iter([agent_module.AgentSession.TERMINATION_COMMAND])
    monkeypatch.setattr(
        builtins, "input", lambda prompt: next(inputs)
    )

    assert session.begin_next_turn() is False
    assert session.closed is True


def test_exit_session_cannot_substitute_for_unexecuted_mutation(
    agent_module,
    monkeypatch,
):
    """Regression: a bare exit_session that claims a deletion (or any
    other work) must not terminate the session nor execute anything.

    Mirrors the live failure where Gemini returned ONLY exit_session
    with "Deleted 'Omnitrix' node and terminating the session as
    requested." and no delete_node action ever ran.
    """
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "exit_session",
                "reason": "deleting node and ending session",
                "exit_summary": (
                    "Deleted 'Omnitrix' node and terminating "
                    "the session as requested."
                ),
            }
        )
    )
    assert decision.action == "exit_session"

    # exit_session is a pure termination decision: it must never
    # dispatch to any tool handler.
    mock_delete = Mock(
        side_effect=AssertionError(
            "exit_session must not call delete_node"
        )
    )
    monkeypatch.setattr(
        registry_module.scene_tools,
        "delete_node",
        mock_delete,
    )

    dispatched = agent_module._execute_single_action(decision)

    assert dispatched["success"] is False
    mock_delete.assert_not_called()

    # Deterministic guard: with no executed tool action in the
    # current turn, exit_session is rejected and the session stays
    # open for the model to perform the actual work.
    assert agent_module.exit_session_is_allowed(0) is False

    guard_result = agent_module.build_premature_exit_session_result()

    assert guard_result["success"] is False
    assert guard_result["action"] == "exit_session"
    assert "cannot substitute" in guard_result["validation_error"]
    assert (
        "no tool action has been executed in this turn"
        in guard_result["validation_error"]
    )

    session = agent_module.AgentSession(
        [{"role": "user", "content": "delete omnitrix and end session"}],
        logging.getLogger("exit-session-guard-test"),
        "delete omnitrix and end session",
    )
    assert session.closed is False


def test_valid_delete_node_then_exit_session_still_works(
    agent_module,
    monkeypatch,
):
    """A real delete_node followed by exit_session still works.

    Once the requested mutation has actually executed, exit_session
    is allowed and terminates the session normally.
    """
    delete_decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "delete_node",
                "reason": "Delete the requested node.",
                "node_path": "Omnitrix",
            }
        )
    )
    mock_delete = Mock(
        return_value={
            "success": True,
            "action": "delete_node",
            "undoable": True,
        }
    )
    monkeypatch.setattr(
        registry_module.scene_tools,
        "delete_node",
        mock_delete,
    )

    result = agent_module.execute_single_action(delete_decision)

    assert result["success"] is True
    mock_delete.assert_called_once_with(node_path="Omnitrix")

    # After real work executed, the guard allows exit_session and the
    # session terminates normally via session.terminate(), unchanged.
    assert agent_module.exit_session_is_allowed(1) is True
    assert agent_module.exit_session_is_allowed(5) is True

    session = agent_module.AgentSession(
        [{"role": "user", "content": "delete omnitrix and end session"}],
        logging.getLogger("exit-session-after-work-test"),
        "delete omnitrix and end session",
    )
    session.terminate()
    assert session.closed is True


def test_prompt_requires_work_before_exit_session(agent_module):
    """The system prompt must tell the model to execute requested
    work before exit_session and to never claim unexecuted actions."""
    system_prompt = agent_module.conversation[0]["content"]

    assert (
        "exit_session performs NO tool work itself"
        in system_prompt
    )
    assert (
        "substitute for requested work"
        in system_prompt
    )
    assert (
        "Never claim in exit_summary that any tool action was"
        in system_prompt
    )


def test_exit_session_preserves_session_state(agent_module):
    """Termination preserves accumulated conversation/state."""
    conversation = [{"role": "user", "content": "turn 1"}]
    session = agent_module.AgentSession(
        conversation,
        logging.getLogger("exit-session-state-test"),
        "turn 1",
    )
    session.execution_result_records.extend(
        [{"step": 0, "action": "find_nodes"}]
    )
    session.blocked_skipped_actions.append(
        {"action": "rename_node"}
    )

    session.terminate()

    assert session.closed is True
    assert session.conversation is conversation
    assert len(session.execution_result_records) == 1
    assert len(session.blocked_skipped_actions) == 1


def test_exit_session_excluded_from_batch():
    """exit_session is excluded from BatchableAction."""
    from pydantic import TypeAdapter

    from agent.schemas import BatchableAction

    adapter = TypeAdapter(BatchableAction)
    with pytest.raises(ValidationError):
        adapter.validate_json(
            json.dumps(
                {
                    "action": "exit_session",
                    "reason": "done",
                    "exit_summary": "Should not be batchable.",
                }
            )
        )


def test_iter_steps_terminates_after_close(agent_module):
    """
    After session.terminate() is called while iter_steps() is
    suspended at a yield, the generator must immediately raise
    StopIteration on the next advance and must not yield another
    step. This prevents unnecessary model/API calls after
    exit_session.
    """
    session = agent_module.AgentSession(
        [{"role": "user", "content": "current turn"}],
        logging.getLogger("iter-steps-terminate-test"),
        "current turn",
    )
    steps = session.iter_steps(5)

    first = next(steps)
    assert first == 0
    assert session.closed is False

    # Simulate exit_session handler: terminate while suspended
    session.terminate()
    assert session.closed is True

    with pytest.raises(StopIteration):
        next(steps)


def test_list_nodes_is_not_in_batchable_action():
    """Regression: list_nodes is an obsolete prototype action.

    It must NOT be accepted as a BatchableAction. Previously, list_nodes
    was batchable and its Python implementation returned a list instead
    of a dict, causing:
        AttributeError: 'list' object has no attribute 'get'
    inside execute_batch_actions().
    """
    from pydantic import TypeAdapter

    adapter = TypeAdapter(BatchableAction)
    with pytest.raises(ValidationError):
        adapter.validate_json(
            json.dumps(
                {
                    "action": "list_nodes",
                    "reason": "should be rejected",
                }
            )
        )


def test_list_nodes_is_not_in_agent_decision():
    """list_nodes must not be a valid top-level AgentDecision either."""
    from pydantic import TypeAdapter

    from agent.schemas import AgentDecision

    adapter = TypeAdapter(AgentDecision)
    with pytest.raises(ValidationError):
        adapter.validate_json(
            json.dumps(
                {
                    "action": "list_nodes",
                    "reason": "should be rejected",
                }
            )
        )


def test_model_usage_available_is_recorded(agent_module, monkeypatch):
    telemetry = SessionObservability("usage-session")
    monkeypatch.setattr(agent_module, "MODEL_PROVIDER", "gemini")
    monkeypatch.setattr(
        agent_module,
        "ask_gemini",
        lambda **kwargs: ProviderResult(
            text='{"action":"final_answer"}',
            usage=TokenUsage(11, 7, 18, True),
        ),
    )

    result = agent_module.ask_model(
        [], telemetry, turn_number=2, step_number=3
    )

    assert result == '{"action":"final_answer"}'
    call = telemetry.model_calls[0]
    assert call.provider == "gemini"
    assert call.model == agent_module.GEMINI_MODEL
    assert call.usage.input_tokens == 11
    assert call.usage.output_tokens == 7
    assert call.usage.total_tokens == 18
    assert call.usage.available is True
    assert call.duration_ms >= 0


def test_model_usage_unavailable_is_not_fabricated(agent_module, monkeypatch):
    telemetry = SessionObservability("unknown-usage-session")
    monkeypatch.setattr(agent_module, "MODEL_PROVIDER", "gemini")
    monkeypatch.setattr(
        agent_module,
        "ask_gemini",
        lambda **kwargs: ProviderResult(
            text='{"action":"final_answer"}'
        ),
    )

    agent_module.ask_model([], telemetry, turn_number=1, step_number=1)

    usage = telemetry.model_calls[0].usage
    assert usage.available is False
    assert usage.input_tokens is None
    assert usage.output_tokens is None
    assert usage.total_tokens is None


def test_model_failure_records_duration_and_error(agent_module, monkeypatch):
    telemetry = SessionObservability("failure-session")
    monkeypatch.setattr(agent_module, "MODEL_PROVIDER", "gemini")
    monkeypatch.setattr(
        agent_module,
        "ask_gemini",
        Mock(side_effect=RuntimeError("provider unavailable")),
    )

    with pytest.raises(RuntimeError, match="provider unavailable"):
        agent_module.ask_model([], telemetry, turn_number=1, step_number=1)

    call = telemetry.model_calls[0]
    assert call.success is False
    assert call.duration_ms >= 0
    assert "provider unavailable" in call.error


def test_batch_telemetry_preserves_batch_boundary(agent_module, monkeypatch):
    telemetry = SessionObservability("batch-session")
    decision = BatchAction(
        action="batch",
        reason="run known actions",
        actions=[
            RenameNodeAction(
                action="rename_node",
                reason="first",
                node_path="A",
                new_name="B",
            ),
            RenameNodeAction(
                action="rename_node",
                reason="second",
                node_path="B",
                new_name="C",
            ),
        ],
    )
    monkeypatch.setattr(
        agent_module,
        "execute_single_action",
        lambda decision, **kwargs: {"success": True},
    )

    result = agent_module.execute_batch_actions(
        decision,
        "rename the nodes",
        logging.getLogger("batch-telemetry-test"),
        observability=telemetry,
        turn_number=1,
        step_number=2,
    )

    assert result["success"] is True
    batch = telemetry.batches[0]
    assert batch.batch_size == 2
    assert batch.succeeded_count == 2
    assert batch.failed_count == 0
    assert batch.stopped_early is False
    assert batch.duration_ms >= 0


def test_session_summary_aggregates_known_and_unknown_usage():
    telemetry = SessionObservability("summary-session")
    telemetry.record_model_call(
        "call-1", 1, 1, "gemini", "test-model", 4.0,
        TokenUsage(10, 5, 15, True), True,
    )
    telemetry.record_model_call(
        "call-2", 1, 2, "ollama", "test-model", 2.0,
        TokenUsage(), True,
    )
    telemetry.record_tool_action(1, 1, "rename_node", True, 1.0)
    telemetry.record_tool_action(1, 2, "delete_node", False, 1.0)
    telemetry.record_batch(1, 3, 2, 2, 0, False, None, 2.0, True)
    telemetry.record_compaction(1, 3, 1000, 100, "find_nodes")

    summary = telemetry.get_summary(1, "test complete")

    assert summary.turns_completed == 1
    assert summary.agent_steps == 2
    assert summary.model_calls == 2
    assert summary.total_input_tokens == 10
    assert summary.total_output_tokens == 5
    assert summary.total_tokens == 15
    assert summary.total_tokens_complete is False
    assert summary.usage_unavailable_count == 1
    assert summary.tool_action_count == 2
    assert summary.successful_action_count == 1
    assert summary.failed_action_count == 1
    assert summary.batch_count == 1
    assert summary.total_batched_actions == 2
    assert summary.compaction_count == 1
    assert summary.termination_reason == "test complete"


def agent_module_find_nodes():
    from agent.schemas import FindNodesAction

    return FindNodesAction(
        action="find_nodes",
        reason="inspect",
        node_name="Player",
    )
