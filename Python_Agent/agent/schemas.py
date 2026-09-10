from typing import Annotated, List, Literal, Optional, Union

from pydantic import (
    BaseModel,
    Field,
)

from config.settings import MAX_BATCH_SIZE

# ==========================================
# Base action
# ==========================================


class BaseAction(BaseModel):

    reason: str = Field(
    min_length=1
)


# ==========================================
# Scene inspection actions
# ==========================================


class GetSceneTreeAction(BaseAction):

    action: Literal["get_scene_tree"]


class FindNodesAction(BaseAction):

    action: Literal["find_nodes"]

    node_name: Optional[str] = None
    node_type: Optional[str] = None

    parent_path: Optional[str] = None

    name_match: Optional[
        Literal[
            "exact",
            "contains",
            "starts_with",
            "ends_with",
        ]
    ] = None

    include_root: Optional[bool] = None


class CountNodesAction(BaseAction):

    action: Literal["count_nodes"]

    node_name: Optional[str] = None
    node_type: Optional[str] = None

    parent_path: Optional[str] = None

    name_match: Optional[
        Literal[
            "exact",
            "contains",
            "starts_with",
            "ends_with",
        ]
    ] = None


class FindNodesByScriptAction(BaseAction):

    action: Literal["find_nodes_by_script"]

    script_path: str


class FindNodesByGroupAction(BaseAction):

    action: Literal["find_nodes_by_group"]

    group_name: str


class GetProjectSettingsAction(BaseAction):

    action: Literal["get_project_settings"]

    setting_names: Optional[list[str]] = None
    prefix: Optional[str] = None
    limit: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
    )


class GetNodePropertiesAction(BaseAction):

    action: Literal["get_node_properties"]

    node_path: str


class GetNodePropertyAction(BaseAction):

    action: Literal["get_node_property"]

    node_path: str

    property_name: str


class ValidateNodeTypeAction(BaseAction):

    action: Literal["validate_node_type"]

    node_type: str



class GetNodeClassInfoAction(BaseAction):

    action: Literal["get_node_class_info"]

    class_name: str = Field(min_length=1)


class ListNodeSignalsAction(BaseAction):

    action: Literal["list_node_signals"]

    node_path: str


class ListNodeGroupsAction(BaseAction):

    action: Literal["list_node_groups"]

    node_path: str


class ListAvailableNodeTypesAction(BaseAction):

    action: Literal["list_available_node_types"]

    inherits_from: Optional[str] = None

    name_contains: Optional[str] = None

    limit: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
    )


class ListAutoloadsAction(BaseAction):

    action: Literal["list_autoloads"]


class GetEditorStateAction(BaseAction):

    action: Literal["get_editor_state"]


class ListScenesInProjectAction(BaseAction):

    action: Literal["list_scenes_in_project"]


class GetUndoHistorySummaryAction(BaseAction):

    action: Literal["get_undo_history_summary"]


# ==========================================
# Scene mutation actions
# ==========================================


class CreateNodeAction(BaseAction):

    action: Literal["create_node"]

    parent_path: str

    node_type: str

    node_name: str


class RenameNodeAction(BaseAction):

    action: Literal["rename_node"]

    node_path: str

    new_name: str


class DeleteNodeAction(BaseAction):

    action: Literal["delete_node"]

    node_path: str


class ReparentNodeAction(BaseAction):

    action: Literal["reparent_node"]

    node_path: str

    new_parent_path: str


class DuplicateNodeAction(BaseAction):

    action: Literal["duplicate_node"]

    node_path: str

    new_parent_path: str

    new_name: str


class SetPropertiesAction(BaseAction):

    action: Literal["set_properties"]

    node_path: str

    properties_json: str


class MoveChildAction(BaseAction):

    action: Literal["move_child"]

    node_path: str

    new_index: int = Field(
        ge=0
    )




class AddToGroupAction(BaseAction):

    action: Literal["add_to_group"]

    node_path: str

    group_name: str


class RemoveFromGroupAction(BaseAction):

    action: Literal["remove_from_group"]

    node_path: str

    group_name: str


class ListConnectionsAction(BaseAction):

    action: Literal["list_node_connections"]

    node_path: str


class ConnectSignalAction(BaseAction):

    action: Literal["connect_signal"]

    node_path: str

    signal_name: str

    target_path: str

    method_name: str

    deferred: Optional[bool] = None


class DisconnectSignalAction(BaseAction):

    action: Literal["disconnect_signal"]

    node_path: str

    signal_name: str

    target_path: str

    method_name: str


class CreateScriptAction(BaseAction):

    action: Literal["create_script"]

    script_path: str

    content: str


class AttachScriptAction(BaseAction):

    action: Literal["attach_script"]

    node_path: str

    script_path: str


class DetachScriptAction(BaseAction):

    action: Literal["detach_script"]

    node_path: str


class GetScriptContentAction(BaseAction):

    action: Literal["get_script_content"]

    script_path: str


class ListScriptDiagnosticsAction(BaseAction):

    action: Literal["list_script_diagnostics"]

    script_path: str


class EditScriptAction(BaseAction):

    action: Literal["edit_script"]

    script_path: str

    content: str


class ReplaceInScriptAction(BaseAction):

    action: Literal["replace_in_script"]

    script_path: str

    old_string: str

    new_string: str


class GetClassDocumentationAction(BaseAction):

    action: Literal["get_class_documentation"]

    class_name: str

    sections: Optional[list[str]] = None


class SearchDocumentationAction(BaseAction):

    action: Literal["search_documentation"]

    query: str

    limit: Optional[int] = Field(
        default=None,
        ge=1,
        le=25,
    )


class SaveSceneAction(BaseAction):

    action: Literal["save_scene"]


class CreateSceneAction(BaseAction):

    action: Literal["create_scene"]

    scene_path: str

    root_node_type: str


class InstantiateSceneAction(BaseAction):

    action: Literal["instantiate_scene"]

    parent_path: str

    scene_path: str

    new_name: Optional[str] = None


class GetSceneDependenciesAction(BaseAction):

    action: Literal["get_scene_dependencies"]

    scene_path: str


class GetSceneTreeOfAction(BaseAction):

    action: Literal["get_scene_tree_of"]

    scene_path: str


class ListOpenScenesAction(BaseAction):

    action: Literal["list_open_scenes"]


class GetPropertyInfoAction(BaseAction):

    action: Literal["get_property_info"]

    node_path: str

    property_name: str


class GetNodeChildrenSummaryAction(BaseAction):

    action: Literal["get_node_children_summary"]

    node_path: str


class AssignResourceToPropertyAction(BaseAction):

    action: Literal["assign_resource_to_property"]

    node_path: str

    property_name: str

    resource_path: str


class GetResourceInfoAction(BaseAction):

    action: Literal["get_resource_info"]

    resource_path: str


class ListProjectFilesAction(BaseAction):

    action: Literal["list_project_files"]

    prefix: Optional[str] = None

    extensions: Optional[list[str]] = None

    limit: Optional[int] = Field(
        default=None,
        ge=1,
        le=500,
    )


class SearchInFilesAction(BaseAction):

    action: Literal["search_in_files"]

    query: str

    extensions: Optional[list[str]] = None

    limit: Optional[int] = Field(
        default=None,
        ge=1,
        le=50,
    )


class GetGlobalClassListAction(BaseAction):

    action: Literal["get_global_class_list"]


class GetInputMapAction(BaseAction):

    action: Literal["get_input_map"]


class RunSceneAction(BaseAction):

    action: Literal["run_scene"]

    scene_path: Optional[str] = None


class StopRunAction(BaseAction):

    action: Literal["stop_run"]


class GetRuntimeOutputAction(BaseAction):

    action: Literal["get_runtime_output"]

    clear: Optional[bool] = None


class OpenSceneAction(BaseAction):

    action: Literal["open_scene"]

    scene_path: str


class SaveSceneAsAction(BaseAction):

    action: Literal["save_scene_as"]

    scene_path: str


class SetProjectSettingsAction(BaseAction):

    action: Literal["set_project_settings"]

    settings_json: str


class CreateResourceAction(BaseAction):

    action: Literal["create_resource"]

    resource_path: str

    resource_type: str

    properties_json: str



class RunSceneOfflineAction(BaseAction):

    action: Literal["run_scene_offline"]

    scene_path: str

    timeout: Optional[int] = Field(
        default=None,
        ge=1,
        le=120,
    )

# ==========================================
# Temporary prototype actions
# ==========================================


class DescribeCurrentSceneAction(BaseAction):

    action: Literal["describe_current_scene"]


# ==========================================
# Bounded batch action
# ==========================================
#
# A batch lets the model propose a short, ordered sequence of
# actions to execute in one host round-trip instead of one
# model call per action. It deliberately reuses the exact same
# per-action classes used for a standalone single-action
# decision - a batch item is validated identically to a
# top-level decision, just executed in sequence with a
# stop-on-first-failure boundary (enforced by the agent loop,
# not by this schema).
#
# final_answer is intentionally excluded: a batch is for
# executing known mutations/inspections, not for concluding
# the task. final_answer must always be its own decision.

BatchableAction = Annotated[
    Union[
        GetSceneTreeAction,
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
        ListNodeSignalsAction,
        ListNodeGroupsAction,
        ValidateNodeTypeAction,
        ListAvailableNodeTypesAction,
        CreateNodeAction,
        RenameNodeAction,
        DeleteNodeAction,
        ReparentNodeAction,
        DuplicateNodeAction,
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
        DescribeCurrentSceneAction,
    ],
    Field(
        discriminator="action"
    ),
]


class BatchAction(BaseAction):

    action: Literal["batch"]

    actions: List[BatchableAction] = Field(
        min_length=1,
        max_length=MAX_BATCH_SIZE,
    )


# ==========================================
# Final response
# ==========================================


class FinalAnswerAction(BaseAction):

    action: Literal["final_answer"]

    final_answer: str


# ==========================================
# Session termination
# ==========================================
#
# exit_session terminates the entire persistent AgentSession.
# It is distinct from final_answer, which ends only the current
# user turn and leaves the session alive for further turns.
#
# exit_session is intentionally excluded from BatchableAction:
# session termination must be its own explicit decision.

class ExitSessionAction(BaseAction):

    action: Literal["exit_session"]

    exit_summary: str


# ==========================================
# Discriminated union
# ==========================================


AgentDecision = Annotated[
    Union[
        GetSceneTreeAction,
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
        ListNodeSignalsAction,
        ListNodeGroupsAction,
        ValidateNodeTypeAction,
        ListAvailableNodeTypesAction,
        CreateNodeAction,
        RenameNodeAction,
        DeleteNodeAction,
        ReparentNodeAction,
        DuplicateNodeAction,
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
        DescribeCurrentSceneAction,
        BatchAction,
        FinalAnswerAction,
        ExitSessionAction,
    ],
    Field(
        discriminator="action"
    ),
]


# ==========================================
# Schema wrapper for model providers
# ==========================================


class AgentDecisionResponse(BaseModel):

    decision: AgentDecision
