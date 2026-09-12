"""
Batch execution boundary enforcement.

When a batch stops early due to a failed action, skipped actions are
recorded as "blocked" so that Python (not the model) prevents them
from being automatically resumed in subsequent reasoning steps.

Before any non-final decision is executed, the orchestrator calls
`check_decision_blocked()`. If a proposed action matches a blocked
skipped action, Python refuses to execute it, logs the rejection,
and returns a tool-result-shaped dict explaining why.

This module is intentionally free of any module-level side effects
(no logging setup, no user input, no Godot calls) so it can be
imported and tested without triggering the agent loop.
"""


_BATCH_ACTION_EQUIVALENCE_KEYS: dict[str, tuple[str, ...]] = {
    "rename_node": ("node_path", "new_name"),
    "duplicate_node": ("node_path", "new_parent_path", "new_name"),
    "create_node": ("parent_path", "node_type", "node_name"),
    "delete_node": ("node_path",),
    "reparent_node": ("node_path", "new_parent_path"),
    "set_properties": ("node_path", "properties_json"),
    "move_child": ("node_path", "new_index"),
    "add_to_group": ("node_path", "group_name"),
    "remove_from_group": ("node_path", "group_name"),
    "connect_signal": (
        "node_path",
        "signal_name",
        "target_path",
        "method_name",
        "deferred",
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
    "edit_script": ("script_path", "content"),
    "replace_in_script": (
        "script_path",
        "old_string",
        "new_string",
    ),
    "save_scene": (),
    "create_scene": ("scene_path", "root_node_type"),
    "instantiate_scene": (
        "parent_path",
        "scene_path",
        "new_name",
    ),
    "assign_resource_to_property": (
        "node_path",
        "property_name",
        "resource_path",
    ),
    "run_scene": ("scene_path",),
    "stop_run": (),
    "open_scene": ("scene_path",),
    "save_scene_as": ("scene_path",),
    "set_project_settings": ("settings_json",),
    "create_resource": (
        "resource_path",
        "resource_type",
        "properties_json",
    ),
    # Resource file operations: a skipped delete blocks
    # any re-proposal against the same path; a skipped
    # rename blocks the same source->destination pair.
    "delete_resource": ("resource_path",),
    "rename_resource": (
        "resource_path",
        "new_resource_path",
    ),
    "create_directory": ("directory_path",),
    "run_scene_offline": ("scene_path", "timeout", "max_output_chars"),
    # Script refactoring: the mutated resource is the script
    # file itself; a skipped rename of a script blocks any
    # further rename of the same source script regardless of
    # the requested destination.
    "rename_script": (
        "script_path",
        "new_script_path",
    ),
    # Multi-file replacement mutates the PROJECT (a set of
    # files), not one resource; the fingerprint covers the
    # exact request, so a skipped call blocks only an
    # identical re-proposal (like set_project_settings).
    "find_replace_across_files": (
        "old_string",
        "new_string",
        "extensions",
        "prefix",
        "max_files",
    ),
    "checkpoint_create": ("label",),
    "checkpoint_restore": ("checkpoint_id",),
    "run_project_tests": ("timeout",),
}

# Fields identifying the RESOURCE being mutated (the "target"),
# independent of the desired resulting state.
#
# This is the key to preventing parameter-change bypass: a skipped
# rename of "Player" must block ANY future rename of "Player",
# regardless of what new_name the model proposes.
#
# For create_node there is no pre-existing resource, so the target
# is empty - exact fingerprint equivalence is sufficient.

_MUTATION_TARGET_KEYS: dict[str, tuple[str, ...]] = {
    "rename_node": ("node_path",),
    "duplicate_node": ("node_path",),
    "create_node": (),
    "delete_node": ("node_path",),
    "reparent_node": ("node_path",),
    "set_properties": ("node_path",),
    "move_child": ("node_path",),
    "add_to_group": ("node_path",),
    "remove_from_group": ("node_path",),
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
    # create_script mutates the PROJECT (a file), not the
    # scene; the mutated resource is the script file itself.
    "create_script": ("script_path",),
    # attach/detach mutate the node's script attachment, so
    # the target is the node (same conservatism as the
    # group mutations: a skipped attach on Player blocks
    # any further attach on Player regardless of script).
    "attach_script": ("node_path",),
    "detach_script": ("node_path",),
    # Script file edits: the mutated resource is the file.
    "edit_script": ("script_path",),
    "replace_in_script": ("script_path",),
    # save_scene has no parameters; exact fingerprint
    # equivalence alone is meaningful.
    "save_scene": (),
    # Scene file creation: the mutated resource is the file.
    "create_scene": ("scene_path",),
    # Instancing mutates the parent's children; a skipped
    # instantiate blocks further instantiation into the
    # same parent regardless of scene or name.
    "instantiate_scene": ("parent_path",),
    # Resource assignment mutates the node (same
    # conservatism as set_properties).
    "assign_resource_to_property": ("node_path",),
    # Process control (run/stop) has no scene resource;
    # exact fingerprint equivalence only (like save_scene).
    "run_scene": (),
    "stop_run": (),
    # Scene navigation and save-as target the file.
    "open_scene": ("scene_path",),
    "save_scene_as": ("scene_path",),
    # Project settings mutation: the fingerprint covers the
    # exact key/value set; a skipped call blocks any other
    # settings call until the model re-proposes it exactly.
    "set_project_settings": (),
    # File-backed resource creation: the mutated resource
    # is the file.
    "create_resource": ("resource_path",),
    # Resource file operations mutate the file at the
    # given path (the source file, for renames - same
    # conservatism as rename_script: a skipped rename
    # blocks any further rename of the same source).
    "delete_resource": ("resource_path",),
    "rename_resource": ("resource_path",),
    "create_directory": ("directory_path",),
    # Offline execution spawns a process; fingerprint
    # equivalence only.
    "run_scene_offline": (),
    # Script rename/move: the mutated resource is the
    # source script file. A skipped rename of a script
    # blocks any further rename of the same script
    # regardless of destination.
    "rename_script": ("script_path",),
    # Multi-file replacement has no single target
    # resource; exact fingerprint equivalence only
    # (like set_project_settings).
    "find_replace_across_files": (),
    "checkpoint_create": ("label",),
    "checkpoint_restore": ("checkpoint_id",),
    "run_project_tests": (),
}


def extract_mutation_target(
    action,
) -> tuple[str, tuple[tuple[str, object], ...]]:
    """
    Extract the identity of the resource being mutated by this action,
    independent of the desired resulting state.

    For example, rename_node("Player", "X") and rename_node("Player", "Y")
    both have the same mutation target: ("Player",). This allows
    enforcement to block automatic resumption of a skipped mutation
    even when the model changes non-target parameters to evade an
    exact fingerprint match.

    Read-only / inspection actions return a target that will never
    match a blocked mutation target.
    """

    action_type = getattr(action, "action", None)

    if action_type not in _MUTATION_TARGET_KEYS:
        return (str(action_type), ())

    keys = _MUTATION_TARGET_KEYS[action_type]

    if not keys:
        return (str(action_type), ())

    field_values = []
    for key in keys:
        field_values.append(
            (key, getattr(action, key, None))
        )

    return (str(action_type), tuple(field_values))


def compute_action_fingerprint(
    action,
) -> tuple[str, tuple[tuple[str, object], ...]]:
    """
    Extract the minimal identity of a mutation action used for
    batch-resume equivalence checking. Returns a tuple of
    (action_type, sorted_key_fields) that can be compared for exact
    equivalence against a blocked skipped action.

    Read-only / inspection actions are not part of the equivalence
    system: they return a fingerprint that will never match a blocked
    mutation action.
    """

    action_type = getattr(
        action,
        "action",
        None,
    )

    if (
        action_type
        not in _BATCH_ACTION_EQUIVALENCE_KEYS
    ):
        return (
            str(action_type),
            (),
        )

    keys = _BATCH_ACTION_EQUIVALENCE_KEYS[
        action_type
    ]

    field_values = []
    for key in keys:
        field_values.append(
            (
                key,
                getattr(
                    action,
                    key,
                    None,
                ),
            )
        )

    return (
        str(action_type),
        tuple(field_values),
    )


def is_action_blocked(
    action,
    blocked_actions: list[dict],
) -> tuple[bool, dict]:
    """
    Return (True, matching_blocked_entry) if the given action is
    equivalent to one of the blocked skipped actions from an
    interrupted batch. Otherwise return (False, {}).

    Two checks are performed:

    1. Exact fingerprint match: same action type and same execution
       fields (e.g. node_path + new_name for rename_node). This blocks
       the literal resumption of the skipped action.

    2. Mutation target match: same action type and same mutation target
       resource (e.g. node_path for rename_node). This blocks parameter-
       change bypasses where the model changes new_name (or other
       non-target fields) to evade the exact fingerprint check while
       still targeting the same skipped resource.

    Read-only / inspection actions are never blocked.
    """

    fingerprint = compute_action_fingerprint(action)
    mutation_target = extract_mutation_target(action)

    for blocked_entry in blocked_actions:
        if blocked_entry.get("fingerprint") == fingerprint:
            return (True, blocked_entry)

        blocked_target = blocked_entry.get("mutation_target")
        if (
            blocked_target is not None
            and blocked_target == mutation_target
            and blocked_target != (str(mutation_target[0]), ())
        ):
            return (True, blocked_entry)

    return (False, {})


def check_decision_blocked(
    decision,
    blocked_actions: list[dict],
) -> tuple[bool, str, list[dict]]:
    """
    Check a proposed decision against the blocked skipped actions.

    Handles both single-action decisions and batch decisions.
    For a batch, every item is checked; if any item matches a
    blocked action, the whole batch is rejected.

    Returns:
        (blocked, reason, matches)
    """

    if not blocked_actions:
        return (
            False,
            "",
            [],
        )

    if decision.action == "batch":
        matches = []
        for (
            sub_action
        ) in decision.actions:
            (
                blocked,
                entry,
            ) = is_action_blocked(
                sub_action,
                blocked_actions,
            )
            if blocked:
                matches.append(
                    {
                        "action": (
                            sub_action.action
                        ),
                        "decision_index": (
                            getattr(
                                sub_action,
                                "action_index",
                                None,
                            )
                        ),
                        "blocked_entry": entry,
                    }
                )

        if matches:
            match_descriptions = []
            for m in matches:
                blocked = m[
                    "blocked_entry"
                ]
                match_descriptions.append(
                    f"{m['action']} (blocked: skipped batch action {blocked.get('batch_index')}/{blocked.get('batch_size')})"
                )
            reason = (
                "Blocked automatic resume of skipped batch action(s): "
                + "; ".join(
                    match_descriptions
                )
            )
            return (
                True,
                reason,
                matches,
            )

        return (
            False,
            "",
            [],
        )

    blocked, entry = is_action_blocked(
        decision,
        blocked_actions,
    )
    if blocked:
        reason = (
            f"Blocked automatic resume of skipped batch action "
            f"{entry.get('batch_index')}/{entry.get('batch_size')} "
            f"({entry.get('action')})."
        )
        return (
            True,
            reason,
            [
                {
                    "action": (
                        decision.action
                    ),
                    "blocked_entry": entry,
                }
            ],
        )

    return (
        False,
        "",
        [],
    )
