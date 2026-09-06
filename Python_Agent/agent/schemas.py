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


class ListAvailableNodeTypesAction(BaseAction):

    action: Literal["list_available_node_types"]

    inherits_from: Optional[str] = None

    name_contains: Optional[str] = None

    limit: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
    )


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
        GetNodePropertiesAction,
        GetNodePropertyAction,
        ValidateNodeTypeAction,
        ListAvailableNodeTypesAction,
        CreateNodeAction,
        RenameNodeAction,
        DeleteNodeAction,
        ReparentNodeAction,
        DuplicateNodeAction,
        SetPropertiesAction,
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
        GetNodePropertiesAction,
        GetNodePropertyAction,
        ValidateNodeTypeAction,
        ListAvailableNodeTypesAction,
        CreateNodeAction,
        RenameNodeAction,
        DeleteNodeAction,
        ReparentNodeAction,
        DuplicateNodeAction,
        SetPropertiesAction,
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
