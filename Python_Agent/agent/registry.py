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
    CreateNodeAction,
    DeleteNodeAction,
    DescribeCurrentSceneAction,
    DuplicateNodeAction,
    ExitSessionAction,
    FinalAnswerAction,
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
    return scene_tools.get_scene_tree()


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
    )


def _execute_get_node_properties(decision):
    return scene_tools.get_node_properties(
        node_path=(
            decision.node_path
        )
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
