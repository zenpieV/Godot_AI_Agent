"""
Minimal action registry for the Godot AI Agent.

Single source of truth for exactly four facts per action:

1. the action name (the AgentDecision discriminator value),
2. the Pydantic schema class representing the action,
3. the required non-empty fields enforced by
   godot_agent.validate_agent_action(),
4. read-only vs mutation classification.

It also holds the Python execution handler used by
godot_agent._execute_single_action().

Entries with handler=None are control actions. They never reach tool
dispatch (final_answer and exit_session are intercepted in the main
loop; batch is orchestrated by execute_batch_actions), but they still
participate in required-field validation, so they are registered with
their schema and required fields and no handler.

Deliberately NOT in this registry: prompt prose, Godot routing,
retry policy, provider logic, batch orchestration, telemetry, and
boundary fingerprint/mutation-target semantics. agent/boundary.py
remains the sole owner of mutation-target safety logic; this
registry's is_mutation flag exists only to make omissions detectable
by tests (see tests/test_registry.py).

This module must not import godot_agent (circular dependency).
Handlers call tools.scene_tools through the module object (late
binding) so tests can monkeypatch scene_tools functions directly.
"""

import json
from dataclasses import dataclass
from typing import Callable, Optional

from tools import scene_tools

from agent.schemas import (
    BatchAction,
    CountNodesAction,
    CreateNodeAction,
    DeleteNodeAction,
    DescribeCurrentSceneAction,
    DuplicateNodeAction,
    ExitSessionAction,
    FinalAnswerAction,
    FindNodesAction,
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
    DeleteResourceAction,
    RenameResourceAction,
    CreateDirectoryAction,
    RunSceneOfflineAction,
    ScanProjectIssuesAction,
    RenameScriptAction,
    FindReplaceAcrossFilesAction,
    CheckpointCreateAction,
    CheckpointListAction,
    CheckpointRestoreAction,
    RunProjectTestsAction,
    ValidateNodeTypeAction,
)

from tools import godot_docs
from tools import offline_runner
from tools import project_tests


@dataclass(frozen=True)
class ActionSpec:
    """Registry entry for one AgentDecision action."""

    name: str
    schema: type
    required_fields: tuple[str, ...]
    is_mutation: bool
    handler: Optional[Callable]


# ==========================================
# Execution handlers
# ==========================================
# One handler per executable action. Each handler preserves the
# exact behavior of the dispatch branch it replaces.


def _execute_get_scene_tree(decision):
    return scene_tools.get_scene_tree(
        max_depth=(
            decision.max_depth
        ),
    )


def _execute_find_nodes(decision):
    return scene_tools.find_nodes(
        node_name=(
            decision.node_name
        ),
        node_type=(
            decision.node_type
        ),
        parent_path=(
            decision.parent_path
        ),
        name_match=(
            decision.name_match
            or "exact"
        ),
        include_root=(
            decision.include_root
            if decision.include_root is not None
            else False
        ),
        include_subclasses=(
            decision.include_subclasses
            if decision.include_subclasses is not None
            else False
        ),
    )


def _execute_count_nodes(decision):
    return scene_tools.count_nodes(
        node_name=(
            decision.node_name
        ),
        node_type=(
            decision.node_type
        ),
        parent_path=(
            decision.parent_path
        ),
        name_match=(
            decision.name_match
            or "exact"
        ),
        include_subclasses=(
            decision.include_subclasses
            if decision.include_subclasses is not None
            else False
        ),
    )


def _execute_find_nodes_by_script(decision):
    return scene_tools.find_nodes_by_script(
        script_path=(
            decision.script_path
        ),
    )


def _execute_find_nodes_by_group(decision):
    return scene_tools.find_nodes_by_group(
        group_name=(
            decision.group_name
        ),
    )


def _execute_get_project_settings(decision):
    return scene_tools.get_project_settings(
        setting_names=(
            decision.setting_names
        ),
        prefix=(
            decision.prefix
        ),
        limit=(
            decision.limit
        ),
    )

def _execute_list_autoloads(decision):
    return scene_tools.list_autoloads()

def _execute_get_editor_state(decision):
    return scene_tools.get_editor_state()

def _execute_list_scenes_in_project(decision):
    return scene_tools.list_scenes_in_project()

def _execute_get_undo_history_summary(decision):
    return scene_tools.get_undo_history_summary()


def _execute_get_node_properties(decision):
    return scene_tools.get_node_properties(
        node_path=(
            decision.node_path
        ),
        property_names=(
            decision.property_names
        ),
    )


def _execute_get_node_property(decision):
    return scene_tools.get_node_property(
        node_path=(
            decision.node_path
        ),
        property_name=(
            decision.property_name
        ),
    )


def _execute_get_node_class_info(decision):
    return scene_tools.get_node_class_info(
        class_name=(
            decision.class_name
        ),
    )


def _execute_list_node_signals(decision):
    return scene_tools.list_node_signals(
        node_path=(
            decision.node_path
        ),
    )


def _execute_list_node_groups(decision):
    return scene_tools.list_node_groups(
        node_path=(
            decision.node_path
        ),
    )


def _execute_validate_node_type(decision):
    return scene_tools.validate_node_type(
        node_type=(
            decision.node_type
        )
    )


def _execute_list_available_node_types(decision):
    return scene_tools.list_available_node_types(
        inherits_from=(
            decision.inherits_from
        ),
        name_contains=(
            decision.name_contains
        ),
        limit=(
            decision.limit
        ),
    )


def _execute_set_properties(decision):
    parsed_properties = (
        json.loads(
            decision.properties_json
        )
    )

    return scene_tools.set_properties(
        node_path=(
            decision.node_path
        ),
        properties=(
            parsed_properties
        ),
    )


def _execute_create_node(decision):
    return scene_tools.create_node(
        parent_path=(
            decision.parent_path
        ),
        node_type=(
            decision.node_type
        ),
        node_name=(
            decision.node_name
        ),
    )


def _execute_rename_node(decision):
    return scene_tools.rename_node(
        node_path=(
            decision.node_path
        ),
        new_name=(
            decision.new_name
        ),
    )


def _execute_delete_node(decision):
    return scene_tools.delete_node(
        node_path=(
            decision.node_path
        )
    )


def _execute_reparent_node(decision):
    return scene_tools.reparent_node(
        node_path=(
            decision.node_path
        ),
        new_parent_path=(
            decision.new_parent_path
        ),
    )


def _execute_duplicate_node(decision):
    return scene_tools.duplicate_node(
        node_path=(
            decision.node_path
        ),
        new_parent_path=(
            decision.new_parent_path
        ),
        new_name=(
            decision.new_name
        ),
    )


def _execute_move_child(decision):
    return scene_tools.move_child(
        node_path=(
            decision.node_path
        ),
        new_index=(
            decision.new_index
        ),
    )


def _execute_add_to_group(decision):
    return scene_tools.add_to_group(
        node_path=(
            decision.node_path
        ),
        group_name=(
            decision.group_name
        ),
    )


def _execute_remove_from_group(decision):
    return scene_tools.remove_from_group(
        node_path=(
            decision.node_path
        ),
        group_name=(
            decision.group_name
        ),
    )


def _execute_list_node_connections(decision):
    return scene_tools.list_node_connections(
        node_path=(
            decision.node_path
        ),
    )


def _execute_connect_signal(decision):
    return scene_tools.connect_signal(
        node_path=(
            decision.node_path
        ),
        signal_name=(
            decision.signal_name
        ),
        target_path=(
            decision.target_path
        ),
        method_name=(
            decision.method_name
        ),
        deferred=(
            decision.deferred
            if decision.deferred is not None
            else False
        ),
    )


def _execute_disconnect_signal(decision):
    return scene_tools.disconnect_signal(
        node_path=(
            decision.node_path
        ),
        signal_name=(
            decision.signal_name
        ),
        target_path=(
            decision.target_path
        ),
        method_name=(
            decision.method_name
        ),
    )


def _execute_create_script(decision):
    return scene_tools.create_script(
        script_path=(
            decision.script_path
        ),
        content=(
            decision.content
        ),
    )


def _execute_attach_script(decision):
    return scene_tools.attach_script(
        node_path=(
            decision.node_path
        ),
        script_path=(
            decision.script_path
        ),
    )


def _execute_detach_script(decision):
    return scene_tools.detach_script(
        node_path=(
            decision.node_path
        ),
    )


def _execute_get_script_content(decision):
    return scene_tools.get_script_content(
        script_path=(
            decision.script_path
        ),
        start_line=(
            decision.start_line
        ),
        line_count=(
            decision.line_count
        ),
    )


def _execute_list_script_diagnostics(decision):
    return scene_tools.list_script_diagnostics(
        script_path=(
            decision.script_path
        ),
    )


def _execute_edit_script(decision):
    return scene_tools.edit_script(
        script_path=(
            decision.script_path
        ),
        content=(
            decision.content
        ),
    )


def _execute_replace_in_script(decision):
    return scene_tools.replace_in_script(
        script_path=(
            decision.script_path
        ),
        old_string=(
            decision.old_string
        ),
        new_string=(
            decision.new_string
        ),
    )


def _execute_get_class_documentation(decision):
    return godot_docs.get_class_documentation(
        class_name=(
            decision.class_name
        ),
        sections=(
            decision.sections
        ),
    )


def _execute_search_documentation(decision):
    return godot_docs.search_documentation(
        query=(
            decision.query
        ),
        limit=(
            decision.limit
        ),
    )


def _execute_save_scene(decision):
    return scene_tools.save_scene()


def _execute_create_scene(decision):
    return scene_tools.create_scene(
        scene_path=(
            decision.scene_path
        ),
        root_node_type=(
            decision.root_node_type
        ),
    )


def _execute_instantiate_scene(decision):
    return scene_tools.instantiate_scene(
        parent_path=(
            decision.parent_path
        ),
        scene_path=(
            decision.scene_path
        ),
        new_name=(
            decision.new_name
        ),
    )


def _execute_get_scene_dependencies(decision):
    return scene_tools.get_scene_dependencies(
        scene_path=(
            decision.scene_path
        ),
    )


def _execute_get_scene_tree_of(decision):
    return scene_tools.get_scene_tree_of(
        scene_path=(
            decision.scene_path
        ),
        max_depth=(
            decision.max_depth
        ),
    )


def _execute_list_open_scenes(decision):
    return scene_tools.list_open_scenes()


def _execute_get_property_info(decision):
    return scene_tools.get_property_info(
        node_path=(
            decision.node_path
        ),
        property_name=(
            decision.property_name
        ),
    )


def _execute_get_node_children_summary(decision):
    return scene_tools.get_node_children_summary(
        node_path=(
            decision.node_path
        ),
    )


def _execute_assign_resource_to_property(decision):
    return scene_tools.assign_resource_to_property(
        node_path=(
            decision.node_path
        ),
        property_name=(
            decision.property_name
        ),
        resource_path=(
            decision.resource_path
        ),
    )


def _execute_get_resource_info(decision):
    return scene_tools.get_resource_info(
        resource_path=(
            decision.resource_path
        ),
    )


def _execute_list_project_files(decision):
    return scene_tools.list_project_files(
        prefix=(
            decision.prefix
        ),
        extensions=(
            decision.extensions
        ),
        limit=(
            decision.limit
        ),
    )


def _execute_search_in_files(decision):
    return scene_tools.search_in_files(
        query=(
            decision.query
        ),
        extensions=(
            decision.extensions
        ),
        limit=(
            decision.limit
        ),
    )


def _execute_get_global_class_list(decision):
    return scene_tools.get_global_class_list()


def _execute_get_input_map(decision):
    return scene_tools.get_input_map()


def _execute_run_scene(decision):
    return scene_tools.run_scene(
        scene_path=(
            decision.scene_path
        ),
    )


def _execute_stop_run(decision):
    return scene_tools.stop_run()


def _execute_get_runtime_output(decision):
    return scene_tools.get_runtime_output(
        clear=(
            decision.clear
            if decision.clear is not None
            else False
        ),
    )


def _execute_open_scene(decision):
    return scene_tools.open_scene(
        scene_path=(
            decision.scene_path
        ),
    )


def _execute_save_scene_as(decision):
    return scene_tools.save_scene_as(
        scene_path=(
            decision.scene_path
        ),
    )


def _execute_set_project_settings(decision):
    parsed_settings = (
        json.loads(
            decision.settings_json
        )
    )

    return scene_tools.set_project_settings(
        settings=(
            parsed_settings
        ),
    )


def _execute_run_scene_offline(decision):
    return offline_runner.run_scene_offline(
        scene_path=(
            decision.scene_path
        ),
        timeout=(
            decision.timeout
        ),
        max_output_chars=(
            decision.max_output_chars
        ),
    )


def _execute_create_resource(decision):
    parsed_properties = (
        json.loads(
            decision.properties_json
        )
    )

    return scene_tools.create_resource(
        resource_path=(
            decision.resource_path
        ),
        resource_type=(
            decision.resource_type
        ),
        properties=(
            parsed_properties
        ),
    )


def _execute_delete_resource(decision):
    return scene_tools.delete_resource(
        resource_path=(
            decision.resource_path
        ),
    )


def _execute_rename_resource(decision):
    return scene_tools.rename_resource(
        resource_path=(
            decision.resource_path
        ),
        new_resource_path=(
            decision.new_resource_path
        ),
    )


def _execute_create_directory(decision):
    return scene_tools.create_directory(
        directory_path=(
            decision.directory_path
        ),
    )


def _execute_scan_project_issues(decision):
    return scene_tools.scan_project_issues(
        prefix=(
            decision.prefix
        ),
        limit=(
            decision.limit
        ),
    )


def _execute_rename_script(decision):
    return scene_tools.rename_script(
        script_path=(
            decision.script_path
        ),
        new_script_path=(
            decision.new_script_path
        ),
    )


def _execute_find_replace_across_files(decision):
    return scene_tools.find_replace_across_files(
        old_string=(
            decision.old_string
        ),
        new_string=(
            decision.new_string
        ),
        extensions=(
            decision.extensions
        ),
        prefix=(
            decision.prefix
        ),
        max_files=(
            decision.max_files
        ),
    )


def _execute_checkpoint_create(decision):
    return scene_tools.checkpoint_create(
        label=(
            decision.label
        ),
    )


def _execute_checkpoint_list(decision):
    return scene_tools.checkpoint_list()


def _execute_checkpoint_restore(decision):
    return scene_tools.checkpoint_restore(
        checkpoint_id=(
            decision.checkpoint_id
        ),
    )


def _execute_run_project_tests(decision):
    return project_tests.run_project_tests(
        timeout=(
            decision.timeout
        ),
    )


def _execute_describe_current_scene(decision):
    # Temporary prototype handler: vision is not connected yet,
    # so this returns a fixed placeholder instead of asking Godot.
    return (
        "Vision is not connected yet. "
        "The current scene screenshot "
        "cannot yet be analyzed."
    )


# ==========================================
# Registry
# ==========================================

_ACTION_SPECS = (
    # --- Read-only scene inspection ---
    ActionSpec(
        name="get_scene_tree",
        schema=GetSceneTreeAction,
        required_fields=(),
        is_mutation=False,
        handler=_execute_get_scene_tree,
    ),
    ActionSpec(
        name="find_nodes",
        schema=FindNodesAction,
        required_fields=(),
        is_mutation=False,
        handler=_execute_find_nodes,
    ),
    ActionSpec(
        name="count_nodes",
        schema=CountNodesAction,
        required_fields=(),
        is_mutation=False,
        handler=_execute_count_nodes,
    ),
    ActionSpec(
        name="find_nodes_by_script",
        schema=FindNodesByScriptAction,
        required_fields=("script_path",),
        is_mutation=False,
        handler=_execute_find_nodes_by_script,
    ),
    ActionSpec(
        name="find_nodes_by_group",
        schema=FindNodesByGroupAction,
        required_fields=("group_name",),
        is_mutation=False,
        handler=_execute_find_nodes_by_group,
    ),
    ActionSpec(
        name="get_project_settings",
        schema=GetProjectSettingsAction,
        required_fields=(),
        is_mutation=False,
        handler=_execute_get_project_settings,
    ),
    ActionSpec(
        name="list_autoloads",
        schema=ListAutoloadsAction,
        required_fields=(),
        is_mutation=False,
        handler=_execute_list_autoloads,
    ),
    ActionSpec(
        name="get_editor_state",
        schema=GetEditorStateAction,
        required_fields=(),
        is_mutation=False,
        handler=_execute_get_editor_state,
    ),
    ActionSpec(
        name="list_scenes_in_project",
        schema=ListScenesInProjectAction,
        required_fields=(),
        is_mutation=False,
        handler=_execute_list_scenes_in_project,
    ),
    ActionSpec(
        name="get_undo_history_summary",
        schema=GetUndoHistorySummaryAction,
        required_fields=(),
        is_mutation=False,
        handler=_execute_get_undo_history_summary,
    ),
    ActionSpec(
        name="get_node_properties",
        schema=GetNodePropertiesAction,
        required_fields=("node_path",),
        is_mutation=False,
        handler=_execute_get_node_properties,
    ),
    ActionSpec(
        name="get_node_property",
        schema=GetNodePropertyAction,
        required_fields=(
            "node_path",
            "property_name",
        ),
        is_mutation=False,
        handler=_execute_get_node_property,
    ),
    ActionSpec(
        name="get_node_class_info",
        schema=GetNodeClassInfoAction,
        required_fields=("class_name",),
        is_mutation=False,
        handler=_execute_get_node_class_info,
    ),
    ActionSpec(
        name="list_node_signals",
        schema=ListNodeSignalsAction,
        required_fields=("node_path",),
        is_mutation=False,
        handler=_execute_list_node_signals,
    ),
    ActionSpec(
        name="list_node_groups",
        schema=ListNodeGroupsAction,
        required_fields=("node_path",),
        is_mutation=False,
        handler=_execute_list_node_groups,
    ),
    ActionSpec(
        name="validate_node_type",
        schema=ValidateNodeTypeAction,
        required_fields=("node_type",),
        is_mutation=False,
        handler=_execute_validate_node_type,
    ),
    ActionSpec(
        name="list_available_node_types",
        schema=ListAvailableNodeTypesAction,
        required_fields=(),
        is_mutation=False,
        handler=_execute_list_available_node_types,
    ),
    ActionSpec(
        name="describe_current_scene",
        schema=DescribeCurrentSceneAction,
        required_fields=(),
        is_mutation=False,
        handler=_execute_describe_current_scene,
    ),
    # --- Scene mutations: every entry here must also be
    # registered in agent/boundary.py _MUTATION_TARGET_KEYS and
    # _BATCH_ACTION_EQUIVALENCE_KEYS; tests/test_registry.py
    # enforces this so a new mutation cannot silently bypass
    # interrupted-batch protection. ---
    ActionSpec(
        name="create_node",
        schema=CreateNodeAction,
        required_fields=(
            "parent_path",
            "node_type",
            "node_name",
        ),
        is_mutation=True,
        handler=_execute_create_node,
    ),
    ActionSpec(
        name="rename_node",
        schema=RenameNodeAction,
        required_fields=(
            "node_path",
            "new_name",
        ),
        is_mutation=True,
        handler=_execute_rename_node,
    ),
    ActionSpec(
        name="delete_node",
        schema=DeleteNodeAction,
        required_fields=("node_path",),
        is_mutation=True,
        handler=_execute_delete_node,
    ),
    ActionSpec(
        name="reparent_node",
        schema=ReparentNodeAction,
        required_fields=(
            "node_path",
            "new_parent_path",
        ),
        is_mutation=True,
        handler=_execute_reparent_node,
    ),
    ActionSpec(
        name="duplicate_node",
        schema=DuplicateNodeAction,
        required_fields=(
            "node_path",
            "new_parent_path",
            "new_name",
        ),
        is_mutation=True,
        handler=_execute_duplicate_node,
    ),
    ActionSpec(
        name="set_properties",
        schema=SetPropertiesAction,
        required_fields=(
            "node_path",
            "properties_json",
        ),
        is_mutation=True,
        handler=_execute_set_properties,
    ),
    ActionSpec(
        name="move_child",
        schema=MoveChildAction,
        required_fields=(
            "node_path",
        ),
        is_mutation=True,
        handler=_execute_move_child,
    ),
    ActionSpec(
        name="add_to_group",
        schema=AddToGroupAction,
        required_fields=(
            "node_path",
            "group_name",
        ),
        is_mutation=True,
        handler=_execute_add_to_group,
    ),
    ActionSpec(
        name="remove_from_group",
        schema=RemoveFromGroupAction,
        required_fields=(
            "node_path",
            "group_name",
        ),
        is_mutation=True,
        handler=_execute_remove_from_group,
    ),
    ActionSpec(
        name="list_node_connections",
        schema=ListConnectionsAction,
        required_fields=("node_path",),
        is_mutation=False,
        handler=_execute_list_node_connections,
    ),
    ActionSpec(
        name="connect_signal",
        schema=ConnectSignalAction,
        required_fields=(
            "node_path",
            "signal_name",
            "target_path",
            "method_name",
        ),
        is_mutation=True,
        handler=_execute_connect_signal,
    ),
    ActionSpec(
        name="disconnect_signal",
        schema=DisconnectSignalAction,
        required_fields=(
            "node_path",
            "signal_name",
            "target_path",
            "method_name",
        ),
        is_mutation=True,
        handler=_execute_disconnect_signal,
    ),
    ActionSpec(
        name="create_script",
        schema=CreateScriptAction,
        required_fields=(
            "script_path",
            "content",
        ),
        is_mutation=True,
        handler=_execute_create_script,
    ),
    ActionSpec(
        name="attach_script",
        schema=AttachScriptAction,
        required_fields=(
            "node_path",
            "script_path",
        ),
        is_mutation=True,
        handler=_execute_attach_script,
    ),
    ActionSpec(
        name="detach_script",
        schema=DetachScriptAction,
        required_fields=("node_path",),
        is_mutation=True,
        handler=_execute_detach_script,
    ),
    ActionSpec(
        name="get_script_content",
        schema=GetScriptContentAction,
        required_fields=("script_path",),
        is_mutation=False,
        handler=_execute_get_script_content,
    ),
    ActionSpec(
        name="list_script_diagnostics",
        schema=ListScriptDiagnosticsAction,
        required_fields=("script_path",),
        is_mutation=False,
        handler=_execute_list_script_diagnostics,
    ),
    ActionSpec(
        name="edit_script",
        schema=EditScriptAction,
        required_fields=(
            "script_path",
            "content",
        ),
        is_mutation=True,
        handler=_execute_edit_script,
    ),
    ActionSpec(
        name="replace_in_script",
        schema=ReplaceInScriptAction,
        required_fields=(
            "script_path",
            "old_string",
            "new_string",
        ),
        is_mutation=True,
        handler=_execute_replace_in_script,
    ),
    ActionSpec(
        name="get_class_documentation",
        schema=GetClassDocumentationAction,
        required_fields=("class_name",),
        is_mutation=False,
        handler=_execute_get_class_documentation,
    ),
    ActionSpec(
        name="search_documentation",
        schema=SearchDocumentationAction,
        required_fields=("query",),
        is_mutation=False,
        handler=_execute_search_documentation,
    ),
    ActionSpec(
        name="save_scene",
        schema=SaveSceneAction,
        required_fields=(),
        is_mutation=True,
        handler=_execute_save_scene,
    ),
    ActionSpec(
        name="create_scene",
        schema=CreateSceneAction,
        required_fields=(
            "scene_path",
            "root_node_type",
        ),
        is_mutation=True,
        handler=_execute_create_scene,
    ),
    ActionSpec(
        name="instantiate_scene",
        schema=InstantiateSceneAction,
        required_fields=(
            "parent_path",
            "scene_path",
        ),
        is_mutation=True,
        handler=_execute_instantiate_scene,
    ),
    ActionSpec(
        name="get_scene_dependencies",
        schema=GetSceneDependenciesAction,
        required_fields=("scene_path",),
        is_mutation=False,
        handler=_execute_get_scene_dependencies,
    ),
    ActionSpec(
        name="get_scene_tree_of",
        schema=GetSceneTreeOfAction,
        required_fields=("scene_path",),
        is_mutation=False,
        handler=_execute_get_scene_tree_of,
    ),
    ActionSpec(
        name="list_open_scenes",
        schema=ListOpenScenesAction,
        required_fields=(),
        is_mutation=False,
        handler=_execute_list_open_scenes,
    ),
    ActionSpec(
        name="get_property_info",
        schema=GetPropertyInfoAction,
        required_fields=(
            "node_path",
            "property_name",
        ),
        is_mutation=False,
        handler=_execute_get_property_info,
    ),
    ActionSpec(
        name="get_node_children_summary",
        schema=GetNodeChildrenSummaryAction,
        required_fields=("node_path",),
        is_mutation=False,
        handler=_execute_get_node_children_summary,
    ),
    ActionSpec(
        name="assign_resource_to_property",
        schema=AssignResourceToPropertyAction,
        required_fields=(
            "node_path",
            "property_name",
            "resource_path",
        ),
        is_mutation=True,
        handler=_execute_assign_resource_to_property,
    ),
    ActionSpec(
        name="get_resource_info",
        schema=GetResourceInfoAction,
        required_fields=("resource_path",),
        is_mutation=False,
        handler=_execute_get_resource_info,
    ),
    ActionSpec(
        name="list_project_files",
        schema=ListProjectFilesAction,
        required_fields=(),
        is_mutation=False,
        handler=_execute_list_project_files,
    ),
    ActionSpec(
        name="search_in_files",
        schema=SearchInFilesAction,
        required_fields=("query",),
        is_mutation=False,
        handler=_execute_search_in_files,
    ),
    ActionSpec(
        name="get_global_class_list",
        schema=GetGlobalClassListAction,
        required_fields=(),
        is_mutation=False,
        handler=_execute_get_global_class_list,
    ),
    ActionSpec(
        name="get_input_map",
        schema=GetInputMapAction,
        required_fields=(),
        is_mutation=False,
        handler=_execute_get_input_map,
    ),
    ActionSpec(
        name="run_scene",
        schema=RunSceneAction,
        required_fields=(),
        is_mutation=True,
        handler=_execute_run_scene,
    ),
    ActionSpec(
        name="stop_run",
        schema=StopRunAction,
        required_fields=(),
        is_mutation=True,
        handler=_execute_stop_run,
    ),
    ActionSpec(
        name="get_runtime_output",
        schema=GetRuntimeOutputAction,
        required_fields=(),
        is_mutation=False,
        handler=_execute_get_runtime_output,
    ),
    ActionSpec(
        name="open_scene",
        schema=OpenSceneAction,
        required_fields=("scene_path",),
        is_mutation=True,
        handler=_execute_open_scene,
    ),
    ActionSpec(
        name="save_scene_as",
        schema=SaveSceneAsAction,
        required_fields=("scene_path",),
        is_mutation=True,
        handler=_execute_save_scene_as,
    ),
    ActionSpec(
        name="set_project_settings",
        schema=SetProjectSettingsAction,
        required_fields=("settings_json",),
        is_mutation=True,
        handler=_execute_set_project_settings,
    ),
    ActionSpec(
        name="run_scene_offline",
        schema=RunSceneOfflineAction,
        required_fields=("scene_path",),
        is_mutation=True,
        handler=_execute_run_scene_offline,
    ),
    ActionSpec(
        name="create_resource",
        schema=CreateResourceAction,
        required_fields=(
            "resource_path",
            "resource_type",
            "properties_json",
        ),
        is_mutation=True,
        handler=_execute_create_resource,
    ),
    ActionSpec(
        name="delete_resource",
        schema=DeleteResourceAction,
        required_fields=("resource_path",),
        is_mutation=True,
        handler=_execute_delete_resource,
    ),
    ActionSpec(
        name="rename_resource",
        schema=RenameResourceAction,
        required_fields=(
            "resource_path",
            "new_resource_path",
        ),
        is_mutation=True,
        handler=_execute_rename_resource,
    ),
    ActionSpec(
        name="create_directory",
        schema=CreateDirectoryAction,
        required_fields=("directory_path",),
        is_mutation=True,
        handler=_execute_create_directory,
    ),
    ActionSpec(
        name="scan_project_issues",
        schema=ScanProjectIssuesAction,
        required_fields=(),
        is_mutation=False,
        handler=_execute_scan_project_issues,
    ),
    ActionSpec(
        name="rename_script",
        schema=RenameScriptAction,
        required_fields=(
            "script_path",
            "new_script_path",
        ),
        is_mutation=True,
        handler=_execute_rename_script,
    ),
    ActionSpec(
        name="find_replace_across_files",
        schema=FindReplaceAcrossFilesAction,
        required_fields=(
            "old_string",
            "new_string",
        ),
        is_mutation=True,
        handler=_execute_find_replace_across_files,
    ),
    ActionSpec(
        name="checkpoint_create",
        schema=CheckpointCreateAction,
        required_fields=(),
        is_mutation=True,
        handler=_execute_checkpoint_create,
    ),
    ActionSpec(
        name="checkpoint_list",
        schema=CheckpointListAction,
        required_fields=(),
        is_mutation=False,
        handler=_execute_checkpoint_list,
    ),
    ActionSpec(
        name="checkpoint_restore",
        schema=CheckpointRestoreAction,
        required_fields=("checkpoint_id",),
        is_mutation=True,
        handler=_execute_checkpoint_restore,
    ),
    ActionSpec(
        name="run_project_tests",
        schema=RunProjectTestsAction,
        required_fields=(),
        is_mutation=True,
        handler=_execute_run_project_tests,
    ),
    # --- Control actions (no tool dispatch; intercepted in the
    # main loop / orchestrated by execute_batch_actions) ---
    ActionSpec(
        name="batch",
        schema=BatchAction,
        required_fields=("actions",),
        is_mutation=False,
        handler=None,
    ),
    ActionSpec(
        name="final_answer",
        schema=FinalAnswerAction,
        required_fields=("final_answer",),
        is_mutation=False,
        handler=None,
    ),
    ActionSpec(
        name="exit_session",
        schema=ExitSessionAction,
        required_fields=("exit_summary",),
        is_mutation=False,
        handler=None,
    ),
)


ACTION_REGISTRY: dict[str, ActionSpec] = {
    spec.name: spec
    for spec in _ACTION_SPECS
}
