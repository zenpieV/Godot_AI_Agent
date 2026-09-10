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
import logging
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
    CountNodesAction,
    FindNodesByScriptAction,
    FindNodesByGroupAction,
    GetProjectSettingsAction,
    ListAutoloadsAction,
    GetEditorStateAction,
    ListScenesInProjectAction,
    GetUndoHistorySummaryAction,
    GetNodePropertiesAction,
    GetNodePropertyAction,
    GetNodeClassInfoAction,
    GetSceneTreeAction,
    ListAvailableNodeTypesAction,
    ListNodeSignalsAction,
    ListNodeGroupsAction,
    RenameNodeAction,
    ReparentNodeAction,
    SetPropertiesAction,
    MoveChildAction,
    AddToGroupAction,
    RemoveFromGroupAction,
    ListConnectionsAction,
    ConnectSignalAction,
    DisconnectSignalAction,
    CreateScriptAction,
    AttachScriptAction,
    DetachScriptAction,
    GetScriptContentAction,
    ListScriptDiagnosticsAction,
    EditScriptAction,
    ReplaceInScriptAction,
    GetClassDocumentationAction,
    SearchDocumentationAction,
    SaveSceneAction,
    CreateSceneAction,
    InstantiateSceneAction,
    GetSceneDependenciesAction,
    GetSceneTreeOfAction,
    ListOpenScenesAction,
    GetPropertyInfoAction,
    GetNodeChildrenSummaryAction,
    AssignResourceToPropertyAction,
    GetResourceInfoAction,
    ListProjectFilesAction,
    SearchInFilesAction,
    GetGlobalClassListAction,
    GetInputMapAction,
    RunSceneAction,
    StopRunAction,
    GetRuntimeOutputAction,
    OpenSceneAction,
    SaveSceneAsAction,
    SetProjectSettingsAction,
    CreateResourceAction,
    RunSceneOfflineAction,
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
    "count_nodes",
    "find_nodes_by_script",
    "find_nodes_by_group",
    "get_project_settings",
    "list_autoloads",
    "get_editor_state",
    "list_scenes_in_project",
    "get_undo_history_summary",
    "get_node_properties",
    "get_node_property",
    "get_node_class_info",
    "list_node_signals",
    "list_node_groups",
    "validate_node_type",
    "list_available_node_types",
    "describe_current_scene",
    "create_node",
    "rename_node",
    "delete_node",
    "reparent_node",
    "duplicate_node",
    "set_properties",
    "move_child",
    "add_to_group",
    "remove_from_group",
    "list_node_connections",
    "connect_signal",
    "disconnect_signal",
    "create_script",
    "attach_script",
    "detach_script",
    "get_script_content",
    "list_script_diagnostics",
    "edit_script",
    "replace_in_script",
    "get_class_documentation",
    "search_documentation",
    "save_scene",
    "create_scene",
    "instantiate_scene",
    "get_scene_dependencies",
    "get_scene_tree_of",
    "list_open_scenes",
    "get_property_info",
    "get_node_children_summary",
    "assign_resource_to_property",
    "get_resource_info",
    "list_project_files",
    "search_in_files",
    "get_global_class_list",
    "get_input_map",
    "run_scene",
    "stop_run",
    "get_runtime_output",
    "open_scene",
    "save_scene_as",
    "set_project_settings",
    "create_resource",
    "run_scene_offline",
}

MUTATION_ACTIONS = {
    "create_node",
    "rename_node",
    "delete_node",
    "reparent_node",
    "duplicate_node",
    "set_properties",
    "move_child",
    "add_to_group",
    "remove_from_group",
    "connect_signal",
    "disconnect_signal",
    "create_script",
    "attach_script",
    "detach_script",
    "edit_script",
    "replace_in_script",
    "save_scene",
    "create_scene",
    "instantiate_scene",
    "assign_resource_to_property",
    "run_scene",
    "stop_run",
    "open_scene",
    "save_scene_as",
    "set_project_settings",
    "create_resource",
    "run_scene_offline",
}

# The exact required-field mapping previously maintained by hand
# as ACTION_REQUIREMENTS in godot_agent.py. This test pins the
# registry to that behavior.
PREVIOUS_ACTION_REQUIREMENTS = {
    "get_scene_tree": (),
    "find_nodes": (),
    "count_nodes": (),
    "find_nodes_by_script": ("script_path",),
    "find_nodes_by_group": ("group_name",),
    "get_project_settings": (),
    "list_autoloads": (),
    "get_editor_state": (),
    "list_scenes_in_project": (),
    "get_undo_history_summary": (),
    "get_node_properties": ("node_path",),
    "get_node_class_info": ("class_name",),
    "list_node_signals": ("node_path",),
    "list_node_groups": ("node_path",),
    "create_node": ("parent_path", "node_type", "node_name"),
    "rename_node": ("node_path", "new_name"),
    "delete_node": ("node_path",),
    "reparent_node": ("node_path", "new_parent_path"),
    "duplicate_node": ("node_path", "new_parent_path", "new_name"),
    "set_properties": ("node_path", "properties_json"),
    "move_child": ("node_path",),
    "add_to_group": ("node_path", "group_name"),
    "remove_from_group": ("node_path", "group_name"),
    "list_node_connections": ("node_path",),
    "connect_signal": (
        "node_path",
        "signal_name",
        "target_path",
        "method_name",
    ),
    "disconnect_signal": (
        "node_path",
        "signal_name",
        "target_path",
        "method_name",
    ),
    "create_script": ("script_path", "content"),
    "attach_script": ("node_path", "script_path"),
    "detach_script": ("node_path",),
    "get_script_content": ("script_path",),
    "list_script_diagnostics": ("script_path",),
    "edit_script": ("script_path", "content"),
    "replace_in_script": ("script_path", "old_string", "new_string"),
    "get_class_documentation": ("class_name",),
    "search_documentation": ("query",),
    "save_scene": (),
    "create_scene": ("scene_path", "root_node_type"),
    "instantiate_scene": ("parent_path", "scene_path"),
    "get_scene_dependencies": ("scene_path",),
    "get_scene_tree_of": ("scene_path",),
    "list_open_scenes": (),
    "get_property_info": ("node_path", "property_name"),
    "get_node_children_summary": ("node_path",),
    "assign_resource_to_property": (
        "node_path",
        "property_name",
        "resource_path",
    ),
    "get_resource_info": ("resource_path",),
    "list_project_files": (),
    "search_in_files": ("query",),
    "get_global_class_list": (),
    "get_input_map": (),
    "run_scene": (),
    "stop_run": (),
    "get_runtime_output": (),
    "open_scene": ("scene_path",),
    "save_scene_as": ("scene_path",),
    "set_project_settings": ("settings_json",),
    "create_resource": (
        "resource_path",
        "resource_type",
        "properties_json",
    ),
    "run_scene_offline": ("scene_path",),
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


def test_get_node_class_info_is_read_only_and_not_in_boundary():
    """get_node_class_info is a read-only inspection action."""
    spec = ACTION_REGISTRY["get_node_class_info"]
    assert spec.is_mutation is False
    assert "get_node_class_info" not in boundary._MUTATION_TARGET_KEYS
    assert "get_node_class_info" not in boundary._BATCH_ACTION_EQUIVALENCE_KEYS


def test_list_node_signals_is_read_only_and_not_in_boundary():
    """list_node_signals is a read-only inspection action."""
    spec = ACTION_REGISTRY["list_node_signals"]
    assert spec.is_mutation is False
    assert "list_node_signals" not in boundary._MUTATION_TARGET_KEYS
    assert "list_node_signals" not in boundary._BATCH_ACTION_EQUIVALENCE_KEYS


def test_list_node_groups_is_read_only_and_not_in_boundary():
    """list_node_groups is a read-only inspection action."""
    spec = ACTION_REGISTRY["list_node_groups"]
    assert spec.is_mutation is False
    assert "list_node_groups" not in boundary._MUTATION_TARGET_KEYS
    assert "list_node_groups" not in boundary._BATCH_ACTION_EQUIVALENCE_KEYS


def test_list_node_connections_is_read_only_and_not_in_boundary():
    """list_node_connections is a read-only inspection action."""
    spec = ACTION_REGISTRY["list_node_connections"]
    assert spec.is_mutation is False
    assert "list_node_connections" not in boundary._MUTATION_TARGET_KEYS
    assert (
        "list_node_connections"
        not in boundary._BATCH_ACTION_EQUIVALENCE_KEYS
    )


def test_get_script_content_is_read_only_and_not_in_boundary():
    """get_script_content is a read-only inspection action."""
    spec = ACTION_REGISTRY["get_script_content"]
    assert spec.is_mutation is False
    assert "get_script_content" not in boundary._MUTATION_TARGET_KEYS
    assert (
        "get_script_content"
        not in boundary._BATCH_ACTION_EQUIVALENCE_KEYS
    )


def test_list_script_diagnostics_is_read_only_and_not_in_boundary():
    """list_script_diagnostics is a read-only inspection action."""
    spec = ACTION_REGISTRY["list_script_diagnostics"]
    assert spec.is_mutation is False
    assert "list_script_diagnostics" not in boundary._MUTATION_TARGET_KEYS
    assert (
        "list_script_diagnostics"
        not in boundary._BATCH_ACTION_EQUIVALENCE_KEYS
    )


def test_python_side_inspectors_are_read_only_and_not_in_boundary():
    """The Python-side documentation tools never touch the bridge
    and are plain read-only inspections."""
    for name in (
        "get_class_documentation",
        "search_documentation",
    ):
        spec = ACTION_REGISTRY[name]
        assert spec.is_mutation is False
        assert name not in boundary._MUTATION_TARGET_KEYS
        assert name not in boundary._BATCH_ACTION_EQUIVALENCE_KEYS


def test_file_based_mutations_are_registered_in_boundary():
    """save_scene has no fields (exact fingerprint only); the other
    file/scene mutations carry their target keys."""
    for name, expected in (
        ("save_scene", ()),
        ("create_scene", ("scene_path",)),
        ("edit_script", ("script_path",)),
        ("replace_in_script", ("script_path",)),
        ("instantiate_scene", ("parent_path",)),
        ("assign_resource_to_property", ("node_path",)),
    ):
        assert boundary._MUTATION_TARGET_KEYS[name] == expected


def test_scene_and_property_inspectors_are_read_only():
    """Batch 2/3 read-only tools are read-only and boundary-free."""
    for name in (
        "get_scene_dependencies",
        "get_scene_tree_of",
        "list_open_scenes",
        "get_property_info",
        "get_node_children_summary",
        "get_resource_info",
        "list_project_files",
        "search_in_files",
        "get_global_class_list",
        "get_input_map",
    ):
        spec = ACTION_REGISTRY[name]
        assert spec.is_mutation is False
        assert name not in boundary._MUTATION_TARGET_KEYS
        assert name not in boundary._BATCH_ACTION_EQUIVALENCE_KEYS


def test_count_nodes_is_read_only_and_not_in_boundary():
    """count_nodes is a read-only inspection action."""
    spec = ACTION_REGISTRY["count_nodes"]
    assert spec.is_mutation is False
    assert "count_nodes" not in boundary._MUTATION_TARGET_KEYS
    assert "count_nodes" not in boundary._BATCH_ACTION_EQUIVALENCE_KEYS


def test_find_nodes_by_script_is_read_only_and_not_in_boundary():
    """find_nodes_by_script is a read-only inspection action."""
    spec = ACTION_REGISTRY["find_nodes_by_script"]
    assert spec.is_mutation is False
    assert "find_nodes_by_script" not in boundary._MUTATION_TARGET_KEYS
    assert "find_nodes_by_script" not in boundary._BATCH_ACTION_EQUIVALENCE_KEYS


def test_find_nodes_by_group_is_read_only_and_not_in_boundary():
    """find_nodes_by_group is a read-only inspection action."""
    spec = ACTION_REGISTRY["find_nodes_by_group"]
    assert spec.is_mutation is False
    assert "find_nodes_by_group" not in boundary._MUTATION_TARGET_KEYS
    assert "find_nodes_by_group" not in boundary._BATCH_ACTION_EQUIVALENCE_KEYS


def test_get_project_settings_is_read_only_and_not_in_boundary():
    """get_project_settings is a read-only inspection action."""
    spec = ACTION_REGISTRY["get_project_settings"]
    assert spec.is_mutation is False
    assert "get_project_settings" not in boundary._MUTATION_TARGET_KEYS
    assert "get_project_settings" not in boundary._BATCH_ACTION_EQUIVALENCE_KEYS


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
        "count_nodes-defaults",
        CountNodesAction(
            reason="r", action="count_nodes", node_name="Enemy"
        ),
        "count_nodes",
        {
            "node_name": "Enemy",
            "node_type": None,
            "parent_path": None,
            "name_match": "exact",
        },
    ),
    (
        "count_nodes-explicit",
        CountNodesAction(
            reason="r",
            action="count_nodes",
            node_type="Area2D",
            parent_path="Level",
            name_match="starts_with",
        ),
        "count_nodes",
        {
            "node_name": None,
            "node_type": "Area2D",
            "parent_path": "Level",
            "name_match": "starts_with",
        },
    ),
    (
        "find_nodes_by_script",
        FindNodesByScriptAction(
            reason="r",
            action="find_nodes_by_script",
            script_path="res://scripts/player.gd",
        ),
        "find_nodes_by_script",
        {"script_path": "res://scripts/player.gd"},
    ),
    (
        "find_nodes_by_group",
        FindNodesByGroupAction(
            reason="r",
            action="find_nodes_by_group",
            group_name="enemies",
        ),
        "find_nodes_by_group",
        {"group_name": "enemies"},
    ),
    (
        "get_project_settings-names",
        GetProjectSettingsAction(
            reason="r",
            action="get_project_settings",
            setting_names=["display/window/size/viewport_width"],
        ),
        "get_project_settings",
        {
            "setting_names": ["display/window/size/viewport_width"],
            "prefix": None,
            "limit": None,
        },
    ),
    (
        "get_project_settings-prefix",
        GetProjectSettingsAction(
            reason="r",
            action="get_project_settings",
            prefix="display/window/size/",
            limit=10,
        ),
        "get_project_settings",
        {
            "setting_names": None,
            "prefix": "display/window/size/",
            "limit": 10,
        },
    ),
    (
        "list_autoloads",
        ListAutoloadsAction(reason="r", action="list_autoloads"),
        "list_autoloads",
        {},
    ),
    (
        "get_editor_state",
        GetEditorStateAction(reason="r", action="get_editor_state"),
        "get_editor_state",
        {},
    ),
    (
        "list_scenes_in_project",
        ListScenesInProjectAction(
            reason="r", action="list_scenes_in_project"
        ),
        "list_scenes_in_project",
        {},
    ),
    (
        "get_undo_history_summary",
        GetUndoHistorySummaryAction(
            reason="r", action="get_undo_history_summary"
        ),
        "get_undo_history_summary",
        {},
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
        "get_node_class_info",
        GetNodeClassInfoAction(
            reason="r",
            action="get_node_class_info",
            class_name="Node2D",
        ),
        "get_node_class_info",
        {"class_name": "Node2D"},
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
        "move_child",
        MoveChildAction(
            reason="r",
            action="move_child",
            node_path="Player",
            new_index=2,
        ),
        "move_child",
        {"node_path": "Player", "new_index": 2},
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
    (
        "list_node_signals",
        ListNodeSignalsAction(
            reason="r",
            action="list_node_signals",
            node_path="Player",
        ),
        "list_node_signals",
        {"node_path": "Player"},
    ),
    (
        "list_node_groups",
        ListNodeGroupsAction(
            reason="r",
            action="list_node_groups",
            node_path="Player",
        ),
        "list_node_groups",
        {"node_path": "Player"},
    ),
    (
        "list_node_connections",
        ListConnectionsAction(
            reason="r",
            action="list_node_connections",
            node_path="Player",
        ),
        "list_node_connections",
        {"node_path": "Player"},
    ),
    (
        "connect_signal-defaults",
        ConnectSignalAction(
            reason="r",
            action="connect_signal",
            node_path="Player",
            signal_name="pressed",
            target_path="Enemy",
            method_name="on_pressed",
        ),
        "connect_signal",
        {
            "node_path": "Player",
            "signal_name": "pressed",
            "target_path": "Enemy",
            "method_name": "on_pressed",
            "deferred": False,
        },
    ),
    (
        "connect_signal-deferred",
        ConnectSignalAction(
            reason="r",
            action="connect_signal",
            node_path="Player",
            signal_name="tree_entered",
            target_path=".",
            method_name="queue_free",
            deferred=True,
        ),
        "connect_signal",
        {
            "node_path": "Player",
            "signal_name": "tree_entered",
            "target_path": ".",
            "method_name": "queue_free",
            "deferred": True,
        },
    ),
    (
        "disconnect_signal",
        DisconnectSignalAction(
            reason="r",
            action="disconnect_signal",
            node_path="Player",
            signal_name="pressed",
            target_path="Enemy",
            method_name="on_pressed",
        ),
        "disconnect_signal",
        {
            "node_path": "Player",
            "signal_name": "pressed",
            "target_path": "Enemy",
            "method_name": "on_pressed",
        },
    ),
    (
        "create_script",
        CreateScriptAction(
            reason="r",
            action="create_script",
            script_path="res://scripts/probe.gd",
            content="extends Node\n",
        ),
        "create_script",
        {
            "script_path": "res://scripts/probe.gd",
            "content": "extends Node\n",
        },
    ),
    (
        "attach_script",
        AttachScriptAction(
            reason="r",
            action="attach_script",
            node_path="Player",
            script_path="res://scripts/probe.gd",
        ),
        "attach_script",
        {
            "node_path": "Player",
            "script_path": "res://scripts/probe.gd",
        },
    ),
    (
        "detach_script",
        DetachScriptAction(
            reason="r",
            action="detach_script",
            node_path="Player",
        ),
        "detach_script",
        {"node_path": "Player"},
    ),
    (
        "get_script_content",
        GetScriptContentAction(
            reason="r",
            action="get_script_content",
            script_path="res://scripts/probe.gd",
        ),
        "get_script_content",
        {"script_path": "res://scripts/probe.gd"},
    ),
    (
        "list_script_diagnostics",
        ListScriptDiagnosticsAction(
            reason="r",
            action="list_script_diagnostics",
            script_path="res://scripts/probe.gd",
        ),
        "list_script_diagnostics",
        {"script_path": "res://scripts/probe.gd"},
    ),
    (
        "edit_script",
        EditScriptAction(
            reason="r",
            action="edit_script",
            script_path="res://scripts/probe.gd",
            content="extends Node\n",
        ),
        "edit_script",
        {
            "script_path": "res://scripts/probe.gd",
            "content": "extends Node\n",
        },
    ),
    (
        "replace_in_script",
        ReplaceInScriptAction(
            reason="r",
            action="replace_in_script",
            script_path="res://scripts/probe.gd",
            old_string="10",
            new_string="20",
        ),
        "replace_in_script",
        {
            "script_path": "res://scripts/probe.gd",
            "old_string": "10",
            "new_string": "20",
        },
    ),
    (
        "save_scene",
        SaveSceneAction(reason="r", action="save_scene"),
        "save_scene",
        {},
    ),
    (
        "create_scene",
        CreateSceneAction(
            reason="r",
            action="create_scene",
            scene_path="res://scenes/probe.tscn",
            root_node_type="Node2D",
        ),
        "create_scene",
        {
            "scene_path": "res://scenes/probe.tscn",
            "root_node_type": "Node2D",
        },
    ),
    (
        "instantiate_scene",
        InstantiateSceneAction(
            reason="r",
            action="instantiate_scene",
            parent_path=".",
            scene_path="res://scenes/probe.tscn",
        ),
        "instantiate_scene",
        {
            "parent_path": ".",
            "scene_path": "res://scenes/probe.tscn",
            "new_name": None,
        },
    ),
    (
        "get_scene_dependencies",
        GetSceneDependenciesAction(
            reason="r",
            action="get_scene_dependencies",
            scene_path="res://scenes/probe.tscn",
        ),
        "get_scene_dependencies",
        {"scene_path": "res://scenes/probe.tscn"},
    ),
    (
        "get_scene_tree_of",
        GetSceneTreeOfAction(
            reason="r",
            action="get_scene_tree_of",
            scene_path="res://scenes/probe.tscn",
        ),
        "get_scene_tree_of",
        {"scene_path": "res://scenes/probe.tscn"},
    ),
    (
        "list_open_scenes",
        ListOpenScenesAction(
            reason="r", action="list_open_scenes"
        ),
        "list_open_scenes",
        {},
    ),
    (
        "get_property_info",
        GetPropertyInfoAction(
            reason="r",
            action="get_property_info",
            node_path="Player",
            property_name="position",
        ),
        "get_property_info",
        {
            "node_path": "Player",
            "property_name": "position",
        },
    ),
    (
        "get_node_children_summary",
        GetNodeChildrenSummaryAction(
            reason="r",
            action="get_node_children_summary",
            node_path="Player",
        ),
        "get_node_children_summary",
        {"node_path": "Player"},
    ),
    (
        "assign_resource_to_property",
        AssignResourceToPropertyAction(
            reason="r",
            action="assign_resource_to_property",
            node_path="Player",
            property_name="texture",
            resource_path="res://icon.svg",
        ),
        "assign_resource_to_property",
        {
            "node_path": "Player",
            "property_name": "texture",
            "resource_path": "res://icon.svg",
        },
    ),
    (
        "get_resource_info",
        GetResourceInfoAction(
            reason="r",
            action="get_resource_info",
            resource_path="res://icon.svg",
        ),
        "get_resource_info",
        {"resource_path": "res://icon.svg"},
    ),
    (
        "list_project_files",
        ListProjectFilesAction(
            reason="r",
            action="list_project_files",
            prefix="scripts",
            extensions=["gd"],
        ),
        "list_project_files",
        {
            "prefix": "scripts",
            "extensions": ["gd"],
            "limit": None,
        },
    ),
    (
        "search_in_files",
        SearchInFilesAction(
            reason="r",
            action="search_in_files",
            query="extends",
        ),
        "search_in_files",
        {
            "query": "extends",
            "extensions": None,
            "limit": None,
        },
    ),
    (
        "get_global_class_list",
        GetGlobalClassListAction(
            reason="r", action="get_global_class_list"
        ),
        "get_global_class_list",
        {},
    ),
    (
        "get_input_map",
        GetInputMapAction(reason="r", action="get_input_map"),
        "get_input_map",
        {},
    ),
    (
        "run_scene-defaults",
        RunSceneAction(reason="r", action="run_scene"),
        "run_scene",
        {"scene_path": None},
    ),
    (
        "run_scene-path",
        RunSceneAction(
            reason="r",
            action="run_scene",
            scene_path="res://scenes/probe.tscn",
        ),
        "run_scene",
        {"scene_path": "res://scenes/probe.tscn"},
    ),
    (
        "stop_run",
        StopRunAction(reason="r", action="stop_run"),
        "stop_run",
        {},
    ),
    (
        "get_runtime_output-defaults",
        GetRuntimeOutputAction(
            reason="r", action="get_runtime_output"
        ),
        "get_runtime_output",
        {"clear": False},
    ),
    (
        "get_runtime_output-clear",
        GetRuntimeOutputAction(
            reason="r", action="get_runtime_output", clear=True
        ),
        "get_runtime_output",
        {"clear": True},
    ),
    (
        "open_scene",
        OpenSceneAction(
            reason="r",
            action="open_scene",
            scene_path="res://scenes/probe.tscn",
        ),
        "open_scene",
        {"scene_path": "res://scenes/probe.tscn"},
    ),
    (
        "save_scene_as",
        SaveSceneAsAction(
            reason="r",
            action="save_scene_as",
            scene_path="res://scenes/probe.tscn",
        ),
        "save_scene_as",
        {"scene_path": "res://scenes/probe.tscn"},
    ),
    (
        "set_project_settings",
        SetProjectSettingsAction(
            reason="r",
            action="set_project_settings",
            settings_json='{"display/window/size/viewport_width": 640}',
        ),
        "set_project_settings",
        {
            "settings": {
                "display/window/size/viewport_width": 640
            }
        },
    ),
    (
        "create_resource",
        CreateResourceAction(
            reason="r",
            action="create_resource",
            resource_path="res://resources/probe.tres",
            resource_type="Curve",
            properties_json='{"_min": 0.0, "_max": 1.0}',
        ),
        "create_resource",
        {
            "resource_path": "res://resources/probe.tres",
            "resource_type": "Curve",
            "properties": {"_min": 0.0, "_max": 1.0},
        },
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


def test_offline_runner_dispatch_reaches_offline_runner_module(
    agent_module, monkeypatch
):
    """run_scene_offline is a Python-side tool: its handler calls
    tools.offline_runner, never the bridge."""
    from tools import offline_runner

    mock_runner = Mock(return_value={"success": True, "via": "offline"})
    monkeypatch.setattr(
        offline_runner, "run_scene_offline", mock_runner
    )

    result = agent_module._execute_single_action(
        RunSceneOfflineAction(
            reason="r",
            action="run_scene_offline",
            scene_path="res://scenes/probe.tscn",
            timeout=10,
        )
    )

    assert result == {"success": True, "via": "offline"}
    mock_runner.assert_called_once_with(
        scene_path="res://scenes/probe.tscn", timeout=10
    )


def test_docs_tools_dispatch_reaches_godot_docs_module(
    agent_module, monkeypatch
):
    """The documentation tools are Python-side: their registry
    handlers call tools.godot_docs, never the bridge."""
    from tools import godot_docs

    mock_docs = Mock(return_value={"success": True, "via": "docs"})
    monkeypatch.setattr(
        godot_docs, "get_class_documentation", mock_docs
    )

    result = agent_module._execute_single_action(
        GetClassDocumentationAction(
            reason="r",
            action="get_class_documentation",
            class_name="Node2D",
            sections=["brief", "signals"],
        )
    )

    assert result == {"success": True, "via": "docs"}
    mock_docs.assert_called_once_with(
        class_name="Node2D", sections=["brief", "signals"]
    )

    mock_search = Mock(return_value={"success": True, "via": "search"})
    monkeypatch.setattr(
        godot_docs, "search_documentation", mock_search
    )

    result = agent_module._execute_single_action(
        SearchDocumentationAction(
            reason="r",
            action="search_documentation",
            query="timer",
            limit=5,
        )
    )

    assert result == {"success": True, "via": "search"}
    mock_search.assert_called_once_with(query="timer", limit=5)


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


def test_move_child_batch_uses_same_execution_and_mutation_telemetry(
    agent_module, monkeypatch
):
    """move_child inside a batch flows through the same dispatch,
    and both tool-action and mutation telemetry are recorded."""
    telemetry = agent_module.SessionObservability("move-batch")
    calls = []

    def fake_move_child(node_path, new_index):
        calls.append((node_path, new_index))
        return {
            "success": True,
            "action": "move_child",
            "moved": True,
            "old_index": 0,
            "new_index": 1,
            "sibling_order_before": ["A", "B"],
            "sibling_order_after": ["B", "A"],
            "verified_index": True,
            "verified_order": True,
            "undoable": True,
        }

    monkeypatch.setattr(scene_tools, "move_child", fake_move_child)

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "batch",
                "reason": "Move the node.",
                "actions": [
                    {
                        "action": "move_child",
                        "reason": "Move to index 1.",
                        "node_path": "A",
                        "new_index": 1,
                    }
                ],
            }
        )
    )

    result = agent_module.execute_batch_actions(
        decision,
        "Move A to index 1.",
        logging.getLogger("test-move-child"),
        observability=telemetry,
        turn_number=1,
        step_number=1,
    )

    assert result["success"] is True
    assert calls == [("A", 1)]
    assert result["results"][0]["action"] == "move_child"
    assert len(telemetry.tool_actions) == 1
    assert telemetry.tool_actions[0].action == "move_child"
    assert len(telemetry.mutations) == 1
    assert telemetry.mutations[0].action == "move_child"
    assert telemetry.mutations[0].verification == "verified"
    assert telemetry.mutations[0].undoable is True

def test_add_remove_group_batch_uses_same_execution_and_mutation_telemetry(
    agent_module, monkeypatch
):
    """add_to_group/remove_from_group inside a batch flow through the
    same dispatch, and both tool-action and mutation telemetry are
    recorded."""
    telemetry = agent_module.SessionObservability("group-batch")
    calls = []

    def fake_add_to_group(node_path, group_name):
        calls.append(("add", node_path, group_name))
        return {
            "success": True,
            "action": "add_to_group",
            "changed": True,
            "was_member": False,
            "is_member": True,
            "verified_membership": True,
            "undoable": True,
        }

    def fake_remove_from_group(node_path, group_name):
        calls.append(("remove", node_path, group_name))
        return {
            "success": True,
            "action": "remove_from_group",
            "changed": True,
            "was_member": True,
            "is_member": False,
            "verified_membership": True,
            "undoable": True,
        }

    monkeypatch.setattr(scene_tools, "add_to_group", fake_add_to_group)
    monkeypatch.setattr(
        scene_tools, "remove_from_group", fake_remove_from_group
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "batch",
                "reason": "Manage groups.",
                "actions": [
                    {
                        "action": "add_to_group",
                        "reason": "Add to enemies.",
                        "node_path": "Alpha",
                        "group_name": "enemies",
                    },
                    {
                        "action": "remove_from_group",
                        "reason": "Remove from foes.",
                        "node_path": "Beta",
                        "group_name": "foes",
                    },
                ],
            }
        )
    )

    result = agent_module.execute_batch_actions(
        decision,
        "Manage groups.",
        logging.getLogger("test-group-batch"),
        observability=telemetry,
        turn_number=1,
        step_number=1,
    )

    assert result["success"] is True
    assert calls == [
        ("add", "Alpha", "enemies"),
        ("remove", "Beta", "foes"),
    ]
    assert len(telemetry.tool_actions) == 2
    assert telemetry.tool_actions[0].action == "add_to_group"
    assert telemetry.tool_actions[1].action == "remove_from_group"
    assert len(telemetry.mutations) == 2
    assert telemetry.mutations[0].action == "add_to_group"
    assert telemetry.mutations[0].verification == "verified"
    assert telemetry.mutations[0].undoable is True
    assert telemetry.mutations[1].action == "remove_from_group"
    assert telemetry.mutations[1].verification == "verified"
    assert telemetry.mutations[1].undoable is True


def test_signal_batch_uses_same_execution_and_mutation_telemetry(
    agent_module, monkeypatch
):
    """connect_signal/disconnect_signal inside a batch flow through
    the same dispatch, and both tool-action and mutation telemetry
    are recorded."""
    telemetry = agent_module.SessionObservability("signal-batch")
    calls = []

    def fake_connect_signal(
        node_path, signal_name, target_path, method_name, deferred=False
    ):
        calls.append(("connect", node_path, signal_name, target_path, method_name))
        return {
            "success": True,
            "action": "connect_signal",
            "changed": True,
            "was_connected": False,
            "is_connected": True,
            "verified_connection": True,
            "undoable": True,
        }

    def fake_disconnect_signal(
        node_path, signal_name, target_path, method_name
    ):
        calls.append(("disconnect", node_path, signal_name, target_path, method_name))
        return {
            "success": True,
            "action": "disconnect_signal",
            "changed": True,
            "was_connected": True,
            "is_connected": False,
            "verified_connection": True,
            "undoable": True,
        }

    monkeypatch.setattr(scene_tools, "connect_signal", fake_connect_signal)
    monkeypatch.setattr(
        scene_tools, "disconnect_signal", fake_disconnect_signal
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "batch",
                "reason": "Rewire signals.",
                "actions": [
                    {
                        "action": "connect_signal",
                        "reason": "Wire pressed to handler.",
                        "node_path": "Alpha",
                        "signal_name": "pressed",
                        "target_path": "Beta",
                        "method_name": "on_pressed",
                    },
                    {
                        "action": "disconnect_signal",
                        "reason": "Drop stale wiring.",
                        "node_path": "Beta",
                        "signal_name": "timeout",
                        "target_path": "Gamma",
                        "method_name": "on_timeout",
                    },
                ],
            }
        )
    )

    result = agent_module.execute_batch_actions(
        decision,
        "Rewire signals.",
        logging.getLogger("test-signal-batch"),
        observability=telemetry,
        turn_number=1,
        step_number=1,
    )

    assert result["success"] is True
    assert calls == [
        ("connect", "Alpha", "pressed", "Beta", "on_pressed"),
        ("disconnect", "Beta", "timeout", "Gamma", "on_timeout"),
    ]
    assert len(telemetry.tool_actions) == 2
    assert telemetry.tool_actions[0].action == "connect_signal"
    assert telemetry.tool_actions[1].action == "disconnect_signal"
    assert len(telemetry.mutations) == 2
    assert telemetry.mutations[0].action == "connect_signal"
    assert telemetry.mutations[0].verification == "verified"
    assert telemetry.mutations[0].undoable is True
    assert telemetry.mutations[1].action == "disconnect_signal"
    assert telemetry.mutations[1].verification == "verified"
    assert telemetry.mutations[1].undoable is True


def test_script_batch_uses_same_execution_and_mutation_telemetry(
    agent_module, monkeypatch
):
    """create_script/attach_script/detach_script inside a batch flow
    through the same dispatch, and both tool-action and mutation
    telemetry are recorded. create_script reports undoable: false
    (file creation is not undoable) and must still be recorded as a
    verified mutation."""
    telemetry = agent_module.SessionObservability("script-batch")
    calls = []

    def fake_create_script(script_path, content):
        calls.append(("create", script_path))
        return {
            "success": True,
            "action": "create_script",
            "changed": True,
            "parse_ok": True,
            "verified_write": True,
            "undoable": False,
        }

    def fake_attach_script(node_path, script_path):
        calls.append(("attach", node_path, script_path))
        return {
            "success": True,
            "action": "attach_script",
            "changed": True,
            "was_attached": False,
            "is_attached": True,
            "verified_attachment": True,
            "undoable": True,
        }

    def fake_detach_script(node_path):
        calls.append(("detach", node_path))
        return {
            "success": True,
            "action": "detach_script",
            "changed": True,
            "was_attached": True,
            "is_attached": False,
            "verified_attachment": True,
            "undoable": True,
        }

    monkeypatch.setattr(scene_tools, "create_script", fake_create_script)
    monkeypatch.setattr(scene_tools, "attach_script", fake_attach_script)
    monkeypatch.setattr(scene_tools, "detach_script", fake_detach_script)

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "batch",
                "reason": "Wire up a probe script.",
                "actions": [
                    {
                        "action": "create_script",
                        "reason": "Create the probe script.",
                        "script_path": "res://scripts/probe.gd",
                        "content": "extends Node\n",
                    },
                    {
                        "action": "attach_script",
                        "reason": "Attach it to Alpha.",
                        "node_path": "Alpha",
                        "script_path": "res://scripts/probe.gd",
                    },
                    {
                        "action": "detach_script",
                        "reason": "Detach it again.",
                        "node_path": "Alpha",
                    },
                ],
            }
        )
    )

    result = agent_module.execute_batch_actions(
        decision,
        "Wire up a probe script.",
        logging.getLogger("test-script-batch"),
        observability=telemetry,
        turn_number=1,
        step_number=1,
    )

    assert result["success"] is True
    assert calls == [
        ("create", "res://scripts/probe.gd"),
        ("attach", "Alpha", "res://scripts/probe.gd"),
        ("detach", "Alpha"),
    ]
    assert len(telemetry.tool_actions) == 3
    assert telemetry.tool_actions[0].action == "create_script"
    assert len(telemetry.mutations) == 3
    assert telemetry.mutations[0].action == "create_script"
    assert telemetry.mutations[0].verification == "verified"
    assert telemetry.mutations[0].undoable is False
    assert telemetry.mutations[1].action == "attach_script"
    assert telemetry.mutations[1].verification == "verified"
    assert telemetry.mutations[1].undoable is True
    assert telemetry.mutations[2].action == "detach_script"
    assert telemetry.mutations[2].verification == "verified"
    assert telemetry.mutations[2].undoable is True

