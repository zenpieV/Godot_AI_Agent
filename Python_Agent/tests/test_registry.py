"""
Tests for the minimal action registry (agent/registry.py).

Guarantees:
- the registry covers every AgentDecision action,
- each entry carries name, schema, required fields,
  read-only/mutation classification, and a handler,
- required fields match the previously hand-maintained
  ACTION_REQUIREMENTS mapping,
- registry dispatch reaches the same scene_tools wrappers as the
  previous if/elif chain (mocked, no real Godot),
- every registry mutation is present in agent/boundary.py mutation
  metadata, so a new mutation cannot silently bypass interrupted
  batch protection.
"""

import builtins
import json
from types import SimpleNamespace
from typing import get_args
from unittest.mock import Mock

import pytest

from agent import boundary
from agent.registry import ACTION_REGISTRY, ActionSpec
from agent.schemas import (
    AgentDecision,
    BatchableAction,
    CreateNodeAction,
    DeleteNodeAction,
    DuplicateNodeAction,
    FindNodesAction,
    GetNodePropertiesAction,
    GetNodePropertyAction,
    GetSceneTreeAction,
    ListAvailableNodeTypesAction,
    RenameNodeAction,
    ReparentNodeAction,
    SetPropertiesAction,
    ValidateNodeTypeAction,
)
from tools import scene_tools


# Control actions never reach tool dispatch; they are validated
# and then intercepted in the main loop (final_answer,
# exit_session) or orchestrated by execute_batch_actions (batch).
CONTROL_ACTIONS = {"batch", "final_answer", "exit_session"}

EXECUTABLE_ACTIONS = {
    "get_scene_tree",
    "find_nodes",
    "get_node_properties",
    "get_node_property",
    "validate_node_type",
    "list_available_node_types",
    "describe_current_scene",
    "create_node",
    "rename_node",
    "delete_node",
    "reparent_node",
    "duplicate_node",
    "set_properties",
}

MUTATION_ACTIONS = {
    "create_node",
    "rename_node",
    "delete_node",
    "reparent_node",
    "duplicate_node",
    "set_properties",
}

# The exact required-field mapping previously maintained by hand
# as ACTION_REQUIREMENTS in godot_agent.py. This test pins the
# registry to that behavior.
PREVIOUS_ACTION_REQUIREMENTS = {
    "get_scene_tree": (),
    "find_nodes": (),
    "get_node_properties": ("node_path",),
    "create_node": ("parent_path", "node_type", "node_name"),
    "rename_node": ("node_path", "new_name"),
    "delete_node": ("node_path",),
    "reparent_node": ("node_path", "new_parent_path"),
    "duplicate_node": ("node_path", "new_parent_path", "new_name"),
    "set_properties": ("node_path", "properties_json"),
    "describe_current_scene": (),
    "batch": ("actions",),
    "final_answer": ("final_answer",),
    "exit_session": ("exit_summary",),
}


def _union_members(annotated_union):
    """Return the member classes of an Annotated[Union[...], ...]."""
    union = get_args(annotated_union)[0]
    return set(get_args(union))


@pytest.fixture(scope="module")
def agent_module():
    """Import the real agent module without a live provider call.

    Mirrors the bootstrap fixture in test_provider_contract.py.
    """
    import models.gemini_provider as gemini_provider
    import models.groq_provider as groq_provider

    original_gemini = gemini_provider.ask_gemini
    original_groq = groq_provider.ask_groq
    original_input = builtins.input

    input_responses = iter(["bootstrap import"])

    def bootstrap_input(prompt):
        try:
            return next(input_responses)
        except StopIteration as error:
            raise EOFError from error

    def bootstrap_decision(**kwargs):
        return json.dumps(
            {
                "action": "final_answer",
                "reason": "import bootstrap",
                "final_answer": "import complete",
            }
        )

    gemini_provider.ask_gemini = bootstrap_decision
    groq_provider.ask_groq = bootstrap_decision
    builtins.input = bootstrap_input

    try:
        import agent.godot_agent as godot_agent
        yield godot_agent
    finally:
        gemini_provider.ask_gemini = original_gemini
        groq_provider.ask_groq = original_groq
        builtins.input = original_input


def test_registry_covers_all_agent_decision_actions():
    """Every AgentDecision member is registered, and nothing extra."""
    decision_members = {
        cls.__name__ for cls in _union_members(AgentDecision)
    }
    registry_schemas = {
        spec.schema.__name__ for spec in ACTION_REGISTRY.values()
    }
    assert registry_schemas == decision_members
    assert set(ACTION_REGISTRY.keys()) == (
        EXECUTABLE_ACTIONS | CONTROL_ACTIONS
    )


def test_registry_entries_have_complete_facts():
    """Each entry carries all five registry facts in valid shape."""
    assert len(ACTION_REGISTRY) == len(set(ACTION_REGISTRY))
    for name, spec in ACTION_REGISTRY.items():
        assert isinstance(spec, ActionSpec)
        assert spec.name == name
        assert isinstance(spec.required_fields, tuple)
        assert all(
            isinstance(field, str) for field in spec.required_fields
        )
        assert isinstance(spec.is_mutation, bool)
        if name in CONTROL_ACTIONS:
            assert spec.handler is None
        else:
            assert callable(spec.handler)
        assert spec.is_mutation == (name in MUTATION_ACTIONS)


def test_registry_required_fields_match_previous_behavior():
    """Registry required fields preserve the legacy mapping."""
    registry_fields = {
        name: spec.required_fields
        for name, spec in ACTION_REGISTRY.items()
    }
    # The 13 pre-existing actions must keep their exact legacy
    # ACTION_REQUIREMENTS mapping.
    for name, fields in PREVIOUS_ACTION_REQUIREMENTS.items():
        assert registry_fields[name] == fields
    # Tool Expansion V2 addition.
    assert registry_fields["validate_node_type"] == ("node_type",)
    assert registry_fields["get_node_property"] == (
        "node_path",
        "property_name",
    )
    assert registry_fields["list_available_node_types"] == ()


def test_registry_schemas_match_batchable_union():
    """Executable action schemas are exactly the BatchableAction set."""
    batchable_schemas = {
        cls.__name__ for cls in _union_members(BatchableAction)
    }
    executable_schemas = {
        spec.schema.__name__
        for name, spec in ACTION_REGISTRY.items()
        if spec.handler is not None
    }
    assert batchable_schemas == executable_schemas


def test_mutations_are_represented_in_boundary_metadata():
    """Every registry mutation exists in boundary mutation metadata."""
    registered_mutations = {
        name
        for name, spec in ACTION_REGISTRY.items()
        if spec.is_mutation
    }
    assert registered_mutations == MUTATION_ACTIONS
    for name in registered_mutations:
        assert name in boundary._MUTATION_TARGET_KEYS, (
            f"{name} is classified as a mutation but is missing from "
            "boundary._MUTATION_TARGET_KEYS; it would bypass "
            "interrupted-batch protection."
        )
        assert name in boundary._BATCH_ACTION_EQUIVALENCE_KEYS, (
            f"{name} is classified as a mutation but is missing from "
            "boundary._BATCH_ACTION_EQUIVALENCE_KEYS."
        )


def test_boundary_mutations_are_all_registered():
    """No boundary mutation entry is missing from the registry."""
    for name in boundary._MUTATION_TARGET_KEYS:
        spec = ACTION_REGISTRY.get(name)
        assert spec is not None, (
            f"boundary._MUTATION_TARGET_KEYS contains '{name}' but "
            "the registry does not."
        )
        assert spec.is_mutation is True


def test_read_only_and_control_not_classified_as_mutations():
    for name in EXECUTABLE_ACTIONS - MUTATION_ACTIONS:
        assert ACTION_REGISTRY[name].is_mutation is False
    for name in CONTROL_ACTIONS:
        assert ACTION_REGISTRY[name].is_mutation is False


def test_validate_node_type_is_read_only_and_never_blocked():
    """validate_node_type is read-only and immune to the boundary."""
    spec = ACTION_REGISTRY["validate_node_type"]
    assert spec.is_mutation is False
    assert "validate_node_type" not in boundary._MUTATION_TARGET_KEYS

    decision = ValidateNodeTypeAction(
        reason="r", action="validate_node_type", node_type="Node2D"
    )

    # Even with a blocked skipped rename recorded, a read-only
    # validate_node_type decision must never be blocked.
    blocked_actions = [
        {
            "fingerprint": (
                "rename_node",
                (("node_path", "Player"), ("new_name", "X")),
            ),
            "mutation_target": (
                "rename_node",
                (("node_path", "Player"),),
            ),
            "batch_index": 2,
            "batch_size": 3,
            "action": "rename_node",
        }
    ]

    (
        is_blocked,
        reason,
        matches,
    ) = boundary.check_decision_blocked(decision, blocked_actions)

    assert is_blocked is False
    assert reason == ""
    assert matches == []


def test_get_node_property_is_read_only_and_not_in_boundary():
    """get_node_property is a read-only inspection action."""
    spec = ACTION_REGISTRY["get_node_property"]
    assert spec.is_mutation is False
    assert "get_node_property" not in boundary._MUTATION_TARGET_KEYS
    assert "get_node_property" not in boundary._BATCH_ACTION_EQUIVALENCE_KEYS


def test_list_available_node_types_is_read_only_and_not_in_boundary():
    """ClassDB discovery is a batchable inspection action."""
    spec = ACTION_REGISTRY["list_available_node_types"]
    assert spec.is_mutation is False
    assert "list_available_node_types" not in boundary._MUTATION_TARGET_KEYS
    assert "list_available_node_types" not in boundary._BATCH_ACTION_EQUIVALENCE_KEYS


def test_unknown_action_returns_structured_failure(agent_module):
    result = agent_module._execute_single_action(
        SimpleNamespace(action="does_not_exist")
    )
    assert result["success"] is False
    assert "Invalid agent action: does_not_exist" in result["error"]


def test_control_actions_are_not_dispatchable(agent_module):
    for name in CONTROL_ACTIONS:
        result = agent_module._execute_single_action(
            SimpleNamespace(action=name)
        )
        assert result["success"] is False


# (action name, decision, scene_tools function to mock,
#  expected kwargs)
DISPATCH_CASES = [
    (
        "get_scene_tree",
        GetSceneTreeAction(reason="r", action="get_scene_tree"),
        "get_scene_tree",
        {},
    ),
    (
        "find_nodes-defaults",
        FindNodesAction(
            reason="r", action="find_nodes", node_name="Player"
        ),
        "find_nodes",
        {
            "node_name": "Player",
            "node_type": None,
            "parent_path": None,
            "name_match": "exact",
            "include_root": False,
        },
    ),
    (
        "find_nodes-explicit",
        FindNodesAction(
            reason="r",
            action="find_nodes",
            node_type="Sprite2D",
            name_match="contains",
            include_root=True,
        ),
        "find_nodes",
        {
            "node_name": None,
            "node_type": "Sprite2D",
            "parent_path": None,
            "name_match": "contains",
            "include_root": True,
        },
    ),
    (
        "get_node_properties",
        GetNodePropertiesAction(
            reason="r", action="get_node_properties", node_path="Player"
        ),
        "get_node_properties",
        {"node_path": "Player"},
    ),
    (
        "get_node_property",
        GetNodePropertyAction(
            reason="r",
            action="get_node_property",
            node_path="Player",
            property_name="position",
        ),
        "get_node_property",
        {"node_path": "Player", "property_name": "position"},
    ),
    (
        "get_node_property-name",
        GetNodePropertyAction(
            reason="r",
            action="get_node_property",
            node_path="Player",
            property_name="name",
        ),
        "get_node_property",
        {"node_path": "Player", "property_name": "name"},
    ),
    (
        "list_available_node_types",
        ListAvailableNodeTypesAction(
            reason="r",
            action="list_available_node_types",
            inherits_from="Node2D",
            name_contains="Body",
            limit=10,
        ),
        "list_available_node_types",
        {
            "inherits_from": "Node2D",
            "name_contains": "Body",
            "limit": 10,
        },
    ),
    (
        "create_node",
        CreateNodeAction(
            reason="r",
            action="create_node",
            parent_path=".",
            node_type="Node2D",
            node_name="Probe",
        ),
        "create_node",
        {"parent_path": ".", "node_type": "Node2D", "node_name": "Probe"},
    ),
    (
        "rename_node",
        RenameNodeAction(
            reason="r",
            action="rename_node",
            node_path="Player",
            new_name="Hero",
        ),
        "rename_node",
        {"node_path": "Player", "new_name": "Hero"},
    ),
    (
        "delete_node",
        DeleteNodeAction(
            reason="r", action="delete_node", node_path="Player"
        ),
        "delete_node",
        {"node_path": "Player"},
    ),
    (
        "reparent_node",
        ReparentNodeAction(
            reason="r",
            action="reparent_node",
            node_path="Player",
            new_parent_path="Enemies",
        ),
        "reparent_node",
        {"node_path": "Player", "new_parent_path": "Enemies"},
    ),
    (
        "duplicate_node",
        DuplicateNodeAction(
            reason="r",
            action="duplicate_node",
            node_path="Player",
            new_parent_path="Enemies",
            new_name="PlayerCopy",
        ),
        "duplicate_node",
        {
            "node_path": "Player",
            "new_parent_path": "Enemies",
            "new_name": "PlayerCopy",
        },
    ),
    (
        "set_properties",
        SetPropertiesAction(
            reason="r",
            action="set_properties",
            node_path="Player",
            properties_json='{"visible": true}',
        ),
        "set_properties",
        {"node_path": "Player", "properties": {"visible": True}},
    ),
    (
        "validate_node_type",
        ValidateNodeTypeAction(
            reason="r",
            action="validate_node_type",
            node_type="Node2D",
        ),
        "validate_node_type",
        {"node_type": "Node2D"},
    ),
]


@pytest.mark.parametrize(
    "action_name,decision,target,expected_kwargs",
    DISPATCH_CASES,
    ids=[case[0] for case in DISPATCH_CASES],
)
def test_dispatch_reaches_same_scene_tools_wrapper(
    agent_module, monkeypatch, action_name, decision, target, expected_kwargs
):
    """Registry dispatch calls the identical scene_tools wrapper."""
    mock_fn = Mock(return_value={"success": True, "via": target})
    monkeypatch.setattr(scene_tools, target, mock_fn)

    result = agent_module._execute_single_action(decision)

    assert result == {"success": True, "via": target}
    mock_fn.assert_called_once_with(**expected_kwargs)


def test_describe_current_scene_handler_placeholder(agent_module):
    result = agent_module._execute_single_action(
        SimpleNamespace(action="describe_current_scene")
    )
    assert result == (
        "Vision is not connected yet. "
        "The current scene screenshot "
        "cannot yet be analyzed."
    )


def test_execute_single_action_wrapper_still_records_telemetry(
    agent_module, monkeypatch
):
    """execute_single_action keeps its telemetry contract."""
    telemetry = agent_module.SessionObservability("registry-telemetry")
    mock_rename = Mock(return_value={"success": True})
    monkeypatch.setattr(scene_tools, "rename_node", mock_rename)

    result = agent_module.execute_single_action(
        RenameNodeAction(
            reason="r",
            action="rename_node",
            node_path="Player",
            new_name="Hero",
        ),
        observability=telemetry,
        turn_number=1,
        step_number=1,
    )

    assert result["success"] is True
    assert len(telemetry.tool_actions) == 1
    assert telemetry.tool_actions[0].action == "rename_node"
    assert telemetry.tool_actions[0].success is True
