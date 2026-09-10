"""
Tests for the batch execution boundary enforcement logic.
"""

from agent.boundary import (
    compute_action_fingerprint,
    extract_mutation_target,
    is_action_blocked,
    check_decision_blocked,
)
from agent.schemas import (
    RenameNodeAction,
    DuplicateNodeAction,
    FindNodesAction,
    BatchAction,
    CreateNodeAction,
    DeleteNodeAction,
    ReparentNodeAction,
    SetPropertiesAction,
    MoveChildAction,
    AddToGroupAction,
    RemoveFromGroupAction,
    ConnectSignalAction,
    DisconnectSignalAction,
    CreateScriptAction,
    AttachScriptAction,
    DetachScriptAction,
    EditScriptAction,
    ReplaceInScriptAction,
    SaveSceneAction,
    CreateSceneAction,
    InstantiateSceneAction,
    AssignResourceToPropertyAction,
)


def _rename(path, name):
    return RenameNodeAction(
        reason="r",
        action="rename_node",
        node_path=path,
        new_name=name,
    )


def _duplicate(path, parent, name):
    return DuplicateNodeAction(
        reason="r",
        action="duplicate_node",
        node_path=path,
        new_parent_path=parent,
        new_name=name,
    )


def _create(parent, typ, name):
    return CreateNodeAction(
        reason="r",
        action="create_node",
        parent_path=parent,
        node_type=typ,
        node_name=name,
    )


def _delete(path):
    return DeleteNodeAction(
        reason="r",
        action="delete_node",
        node_path=path,
    )


def _reparent(path, new_parent):
    return ReparentNodeAction(
        reason="r",
        action="reparent_node",
        node_path=path,
        new_parent_path=new_parent,
    )


def _set_props(path, props):
    return SetPropertiesAction(
        reason="r",
        action="set_properties",
        node_path=path,
        properties_json=props,
    )


def _move_child(path, new_index):
    return MoveChildAction(
        reason="r",
        action="move_child",
        node_path=path,
        new_index=new_index,
    )


def _add_to_group(path, group_name):
    return AddToGroupAction(
        reason="r",
        action="add_to_group",
        node_path=path,
        group_name=group_name,
    )


def _remove_from_group(path, group_name):
    return RemoveFromGroupAction(
        reason="r",
        action="remove_from_group",
        node_path=path,
        group_name=group_name,
    )


def _connect_signal(path, signal_name, target_path, method_name, deferred=None):
    return ConnectSignalAction(
        reason="r",
        action="connect_signal",
        node_path=path,
        signal_name=signal_name,
        target_path=target_path,
        method_name=method_name,
        deferred=deferred,
    )


def _disconnect_signal(path, signal_name, target_path, method_name):
    return DisconnectSignalAction(
        reason="r",
        action="disconnect_signal",
        node_path=path,
        signal_name=signal_name,
        target_path=target_path,
        method_name=method_name,
    )


def _create_script(script_path, content):
    return CreateScriptAction(
        reason="r",
        action="create_script",
        script_path=script_path,
        content=content,
    )


def _attach_script(node_path, script_path):
    return AttachScriptAction(
        reason="r",
        action="attach_script",
        node_path=node_path,
        script_path=script_path,
    )


def _detach_script(node_path):
    return DetachScriptAction(
        reason="r",
        action="detach_script",
        node_path=node_path,
    )


def _edit_script(script_path, content):
    return EditScriptAction(
        reason="r",
        action="edit_script",
        script_path=script_path,
        content=content,
    )


def _replace_in_script(script_path, old_string, new_string):
    return ReplaceInScriptAction(
        reason="r",
        action="replace_in_script",
        script_path=script_path,
        old_string=old_string,
        new_string=new_string,
    )


def _save_scene():
    return SaveSceneAction(reason="r", action="save_scene")


def _create_scene(scene_path, root_node_type):
    return CreateSceneAction(
        reason="r",
        action="create_scene",
        scene_path=scene_path,
        root_node_type=root_node_type,
    )


def _instantiate_scene(parent_path, scene_path, new_name=None):
    return InstantiateSceneAction(
        reason="r",
        action="instantiate_scene",
        parent_path=parent_path,
        scene_path=scene_path,
        new_name=new_name,
    )


def _assign_resource(node_path, property_name, resource_path):
    return AssignResourceToPropertyAction(
        reason="r",
        action="assign_resource_to_property",
        node_path=node_path,
        property_name=property_name,
        resource_path=resource_path,
    )


def _blocked_from_action(action, batch_index, batch_size):
    return [
        {
            "fingerprint": compute_action_fingerprint(action),
            "mutation_target": extract_mutation_target(action),
            "action": getattr(action, "action", None),
            "batch_index": batch_index,
            "batch_size": batch_size,
        }
    ]


def test_rename_fingerprint_matches_skipped():
    skipped = _rename("PlayerBatchFailureCopy", "ShouldBeSkipped")
    blocked = _blocked_from_action(skipped, 3, 3)
    proposed = _rename("PlayerBatchFailureCopy", "ShouldBeSkipped")
    is_blocked, entry = is_action_blocked(proposed, blocked)
    assert is_blocked is True
    assert entry["batch_index"] == 3


def test_rename_different_new_name_BLOCKED():
    """
    Bypass attempt: same node_path but different new_name.
    Must be BLOCKED by mutation-target enforcement even though
    the exact fingerprint differs.
    """
    skipped = _rename("PlayerBatchFailureCopy", "ShouldBeSkipped")
    blocked = _blocked_from_action(skipped, 3, 3)
    proposed = _rename("PlayerBatchFailureCopy", "RenamedPlayer")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_rename_different_node_not_blocked():
    """A rename targeting a DIFFERENT node is NOT blocked."""
    skipped = _rename("PlayerBatchFailureCopy", "ShouldBeSkipped")
    blocked = _blocked_from_action(skipped, 3, 3)
    proposed = _rename("CompletelyDifferentNode", "ShouldBeSkipped")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is False


def _find(name):
    return FindNodesAction(
        reason="inspect",
        action="find_nodes",
        node_name=name,
    )


def test_find_nodes_not_blocked():
    proposed = _find("Player")
    blocked = _blocked_from_action(_rename("Player", "X"), 3, 3)
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is False


def test_duplicate_fingerprint_matches():
    skipped = _duplicate("Player", ".", "Copy")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _duplicate("Player", ".", "Copy")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_duplicate_different_source_not_blocked():
    """A duplicate of a DIFFERENT source node is NOT blocked."""
    skipped = _duplicate("Player", ".", "Copy")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _duplicate("OtherNode", ".", "Copy")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is False


def test_empty_blocked_list_allows_anything():
    proposed = _rename("Player", "X")
    is_blocked, _ = is_action_blocked(proposed, [])
    assert is_blocked is False


def test_check_single_action_blocked_again():
    skipped = _rename("PlayerBatchFailureCopy", "ShouldBeSkipped")
    blocked = _blocked_from_action(skipped, 3, 3)
    proposed = _rename("PlayerBatchFailureCopy", "ShouldBeSkipped")
    result, reason, matches = check_decision_blocked(proposed, blocked)
    assert result is True
    assert "Blocked automatic resume" in reason
    assert len(matches) == 1


def test_check_batch_with_blocked_item():
    skipped = _rename("PlayerBatchFailureCopy", "ShouldBeSkipped")
    blocked = _blocked_from_action(skipped, 3, 3)
    proposed_batch = BatchAction(
        reason="resume batch",
        action="batch",
        actions=[
            _find("Player"),
            _rename("PlayerBatchFailureCopy", "ShouldBeSkipped"),
        ],
    )
    result, reason, matches = check_decision_blocked(
        proposed_batch, blocked
    )
    assert result is True
    assert "rename_node" in reason
    assert len(matches) >= 1


def test_check_batch_without_blocked_item():
    skipped = _rename("PlayerBatchFailureCopy", "ShouldBeSkipped")
    blocked = _blocked_from_action(skipped, 3, 3)
    proposed_batch = BatchAction(
        reason="recovery batch",
        action="batch",
        actions=[
            _find("Player"),
            _rename("OtherNode", "OtherName"),
        ],
    )
    result, reason, matches = check_decision_blocked(
        proposed_batch, blocked
    )
    assert result is False

def test_check_single_action_blocked():
    skipped = _rename("PlayerBatchFailureCopy", "ShouldBeSkipped")
    blocked = _blocked_from_action(skipped, 3, 3)
    proposed = _rename("PlayerBatchFailureCopy", "ShouldBeSkipped")
    result, reason, matches = check_decision_blocked(proposed, blocked)
    assert result is True
    assert "Blocked automatic resume" in reason
    assert len(matches) == 1


def test_create_node_equivalence():
    skipped = _create(".", "Node2D", "TestEnemy")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed_same = _create(".", "Node2D", "TestEnemy")
    is_blocked, _ = is_action_blocked(proposed_same, blocked)
    assert is_blocked is True
    proposed_diff = _create("Player", "Node2D", "TestEnemy")
    is_blocked, _ = is_action_blocked(proposed_diff, blocked)
    assert is_blocked is False


def test_delete_node_equivalence():
    skipped = _delete("OldEnemy")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed_same = _delete("OldEnemy")
    is_blocked, _ = is_action_blocked(proposed_same, blocked)
    assert is_blocked is True
    proposed_diff = _delete("OtherEnemy")
    is_blocked, _ = is_action_blocked(proposed_diff, blocked)
    assert is_blocked is False


def test_reparent_node_equivalence():
    skipped = _reparent("Player", "NewContainer")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed_same = _reparent("Player", "NewContainer")
    is_blocked, _ = is_action_blocked(proposed_same, blocked)
    assert is_blocked is True
    # Same target node, different new parent -> BLOCKED (target match)
    proposed_diff_parent = _reparent("Player", "OtherContainer")
    is_blocked, _ = is_action_blocked(proposed_diff_parent, blocked)
    assert is_blocked is True
    # Different target node -> NOT blocked
    proposed_diff_node = _reparent("OtherNode", "NewContainer")
    is_blocked, _ = is_action_blocked(proposed_diff_node, blocked)
    assert is_blocked is False


def test_set_properties_equivalence():
    skipped = _set_props("Player", '{"position": [100, 200]}')
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed_same = _set_props("Player", '{"position": [100, 200]}')
    is_blocked, _ = is_action_blocked(proposed_same, blocked)
    assert is_blocked is True
    # Same target node, different properties -> BLOCKED (target match)
    proposed_diff_props = _set_props("Player", '{"position": [50, 50]}')
    is_blocked, _ = is_action_blocked(proposed_diff_props, blocked)
    assert is_blocked is True
    # Different target node -> NOT blocked
    proposed_diff_node = _set_props("OtherNode", '{"position": [100, 200]}')
    is_blocked, _ = is_action_blocked(proposed_diff_node, blocked)
    assert is_blocked is False


def test_non_equivalent_action_allowed():
    skipped = _rename("PlayerBatchFailureCopy", "ShouldBeSkipped")
    blocked = _blocked_from_action(skipped, 3, 3)
    proposed = _find("DefinitelyDoesNotExist")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is False
    proposed2 = _rename("CompletelyDifferentNode", "NewName")
    is_blocked, _ = is_action_blocked(proposed2, blocked)
    assert is_blocked is False


def test_fingerprint_determinism():
    action = _rename("Player", "X")
    fp1 = compute_action_fingerprint(action)
    fp2 = compute_action_fingerprint(action)
    assert fp1 == fp2
    assert isinstance(fp1, tuple)
    assert fp1[0] == "rename_node"


def test_recovery_find_nodes_allowed_after_failure():
    """After a batch failure on rename, find_nodes is allowed."""
    skipped = _rename("PlayerBatchFailureCopy", "ShouldBeSkipped")
    blocked = _blocked_from_action(skipped, 3, 3)
    proposed = _find("DefinitelyDoesNotExist")
    result, reason, matches = check_decision_blocked(proposed, blocked)
    assert result is False

def test_batch_containing_bypassed_rename_BLOCKED():
    """
    A new batch containing a rename that targets the same node
    as a skipped action (with different new_name) must be
    rejected before any item executes.
    """
    skipped = _rename("PlayerBatchFailureCopy", "ShouldBeSkipped")
    blocked = _blocked_from_action(skipped, 3, 3)
    proposed_batch = BatchAction(
        reason="resume batch",
        action="batch",
        actions=[
            _find("Player"),
            _rename("PlayerBatchFailureCopy", "RenamedPlayer"),
        ],
    )
    result, reason, matches = check_decision_blocked(
        proposed_batch, blocked
    )
    assert result is True
    assert "rename_node" in reason
    assert len(matches) >= 1


def test_demonstrated_bypass_BLOCKED():
    """
    The exact bypass from the bug report:
    Batch: [duplicate Player, rename MissingNode (fails), rename Copy->Skipped (skipped)]
    Model then proposes: rename Copy -> RenamedPlayer (different new_name).
    Must be BLOCKED.
    """
    skipped = _rename("PlayerBatchFailureCopy", "ShouldBeSkipped")
    blocked = _blocked_from_action(skipped, 3, 3)
    proposed = _rename("PlayerBatchFailureCopy", "RenamedPlayer")
    result, reason, matches = check_decision_blocked(proposed, blocked)
    assert result is True
    assert "Blocked automatic resume" in reason


def test_duplicate_different_name_BLOCKED():
    """
    Skipped duplicate_node("Player", ".", "Copy") must block
    duplicate_node("Player", ".", "OtherCopy") because the
    source target (node_path) is the same.
    """
    skipped = _duplicate("Player", ".", "Copy")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _duplicate("Player", ".", "OtherCopy")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_set_properties_different_values_BLOCKED():
    """
    Skipped set_properties("Player", "{...}") must block
    set_properties("Player", "{...different...}") because
    the target node is the same.
    """
    skipped = _set_props("Player", '{"position": [100, 200]}')
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _set_props("Player", '{"position": [999, 999]}')
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_reparent_different_target_BLOCKED():
    """
    Skipped reparent_node("Player", "A") must block
    reparent_node("Player", "B") because the target node is the same.
    """
    skipped = _reparent("Player", "ContainerA")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _reparent("Player", "ContainerB")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_delete_same_node_BLOCKED():
    """
    Skipped delete_node("OldEnemy") must block a subsequent
    delete_node("OldEnemy") even if exact match (already covered)
    but also confirms target-level logic for delete.
    """
    skipped = _delete("OldEnemy")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _delete("OldEnemy")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_mutation_target_extraction():
    """extract_mutation_target returns the node identity, not new_name."""
    rename_action = _rename("Player", "AnyName")
    target = extract_mutation_target(rename_action)
    assert target == ("rename_node", (("node_path", "Player"),))

    delete_action = _delete("SomeNode")
    target = extract_mutation_target(delete_action)
    assert target == ("delete_node", (("node_path", "SomeNode"),))

    move_action = _move_child("SomeNode", 2)
    target = extract_mutation_target(move_action)
    assert target == ("move_child", (("node_path", "SomeNode"),))

    add_action = _add_to_group("SomeNode", "enemies")
    target = extract_mutation_target(add_action)
    assert target == (
        "add_to_group",
        (("node_path", "SomeNode"),),
    )

    remove_action = _remove_from_group("SomeNode", "enemies")
    target = extract_mutation_target(remove_action)
    assert target == (
        "remove_from_group",
        (("node_path", "SomeNode"),),
    )

    # Read-only action: target has empty fields
    find_action = _find("Something")
    target = extract_mutation_target(find_action)
    assert target == ("find_nodes", ())


def test_move_child_fingerprint_matches_skipped():
    skipped = _move_child("Player", 0)
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _move_child("Player", 0)
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_move_child_different_index_BLOCKED():
    """
    Bypass attempt: same node_path but a different new_index.
    Must be BLOCKED by mutation-target enforcement even though
    the exact fingerprint differs.
    """
    skipped = _move_child("Player", 0)
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _move_child("Player", 2)
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_move_child_different_node_not_blocked():
    skipped = _move_child("Player", 0)
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _move_child("Enemy", 0)
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is False



def test_add_to_group_fingerprint_matches_skipped():
    skipped = _add_to_group("Player", "enemies")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _add_to_group("Player", "enemies")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_add_to_group_different_group_BLOCKED():
    """
    Bypass attempt: same node_path but a different group_name.
    Must be BLOCKED by mutation-target enforcement even though
    the exact fingerprint differs.
    """
    skipped = _add_to_group("Player", "enemies")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _add_to_group("Player", "allies")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_add_to_group_different_node_not_blocked():
    skipped = _add_to_group("Player", "enemies")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _add_to_group("Enemy", "enemies")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is False


def test_remove_from_group_fingerprint_matches_skipped():
    skipped = _remove_from_group("Player", "enemies")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _remove_from_group("Player", "enemies")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_remove_from_group_different_group_BLOCKED():
    skipped = _remove_from_group("Player", "enemies")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _remove_from_group("Player", "allies")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_remove_from_group_different_node_not_blocked():
    skipped = _remove_from_group("Player", "enemies")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _remove_from_group("Enemy", "enemies")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is False


def test_connect_signal_fingerprint_matches_skipped():
    skipped = _connect_signal("Player", "pressed", "Enemy", "on_pressed")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _connect_signal("Player", "pressed", "Enemy", "on_pressed")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_connect_signal_different_method_not_blocked():
    """
    A different method is a DIFFERENT connection resource, not a
    bypass: the mutation target covers the full connection identity
    (node_path, signal_name, target_path, method_name).
    """
    skipped = _connect_signal("Player", "pressed", "Enemy", "on_pressed")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _connect_signal("Player", "pressed", "Enemy", "on_timeout")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is False


def test_connect_signal_deferred_change_BLOCKED():
    """
    Bypass attempt: same connection identity but deferred toggled.
    Must be BLOCKED by mutation-target enforcement even though the
    exact fingerprint differs.
    """
    skipped = _connect_signal(
        "Player", "pressed", "Enemy", "on_pressed", deferred=False
    )
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _connect_signal(
        "Player", "pressed", "Enemy", "on_pressed", deferred=True
    )
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_disconnect_signal_fingerprint_matches_skipped():
    skipped = _disconnect_signal("Player", "pressed", "Enemy", "on_pressed")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _disconnect_signal("Player", "pressed", "Enemy", "on_pressed")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_disconnect_signal_different_signal_not_blocked():
    skipped = _disconnect_signal("Player", "pressed", "Enemy", "on_pressed")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _disconnect_signal("Player", "timeout", "Enemy", "on_pressed")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is False


def test_signal_mutation_target_extraction():
    """connect_signal/disconnect_signal targets cover the connection
    identity, not the desired result state."""
    connect_action = _connect_signal(
        "Player", "pressed", "Enemy", "on_pressed"
    )
    target = extract_mutation_target(connect_action)
    assert target == (
        "connect_signal",
        (
            ("node_path", "Player"),
            ("signal_name", "pressed"),
            ("target_path", "Enemy"),
            ("method_name", "on_pressed"),
        ),
    )

    disconnect_action = _disconnect_signal(
        "Player", "pressed", "Enemy", "on_pressed"
    )
    target = extract_mutation_target(disconnect_action)
    assert target == (
        "disconnect_signal",
        (
            ("node_path", "Player"),
            ("signal_name", "pressed"),
            ("target_path", "Enemy"),
            ("method_name", "on_pressed"),
        ),
    )


def test_create_script_fingerprint_matches_skipped():
    skipped = _create_script("res://scripts/a.gd", "extends Node\n")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _create_script("res://scripts/a.gd", "extends Node\n")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_create_script_different_content_BLOCKED():
    """
    Bypass attempt: same script_path but different content. Must be
    BLOCKED by mutation-target enforcement (target is the script
    file) even though the exact fingerprint differs.
    """
    skipped = _create_script("res://scripts/a.gd", "extends Node\n")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _create_script("res://scripts/a.gd", "extends Node2D\n")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_create_script_different_path_not_blocked():
    skipped = _create_script("res://scripts/a.gd", "extends Node\n")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _create_script("res://scripts/b.gd", "extends Node\n")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is False


def test_attach_script_fingerprint_matches_skipped():
    skipped = _attach_script("Player", "res://scripts/a.gd")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _attach_script("Player", "res://scripts/a.gd")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_attach_script_different_script_BLOCKED():
    """
    Bypass attempt: same node but a different script_path. Must be
    BLOCKED by mutation-target enforcement (target is the node's
    script attachment) even though the exact fingerprint differs.
    """
    skipped = _attach_script("Player", "res://scripts/a.gd")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _attach_script("Player", "res://scripts/b.gd")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_attach_script_different_node_not_blocked():
    skipped = _attach_script("Player", "res://scripts/a.gd")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _attach_script("Enemy", "res://scripts/a.gd")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is False


def test_detach_script_fingerprint_matches_skipped():
    skipped = _detach_script("Player")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _detach_script("Player")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_detach_script_different_node_not_blocked():
    skipped = _detach_script("Player")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _detach_script("Enemy")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is False


def test_edit_script_different_content_BLOCKED():
    """Same file, different content: target is the script file."""
    skipped = _edit_script("res://scripts/a.gd", "extends Node\n")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _edit_script("res://scripts/a.gd", "extends Node2D\n")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_edit_script_different_file_not_blocked():
    skipped = _edit_script("res://scripts/a.gd", "extends Node\n")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _edit_script("res://scripts/b.gd", "extends Node\n")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is False


def test_replace_in_script_different_replacement_BLOCKED():
    """Same file, different anchored edit: target is the file."""
    skipped = _replace_in_script("res://scripts/a.gd", "10", "20")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _replace_in_script("res://scripts/a.gd", "10", "30")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_replace_in_script_different_file_not_blocked():
    skipped = _replace_in_script("res://scripts/a.gd", "10", "20")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _replace_in_script("res://scripts/b.gd", "10", "20")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is False


def test_save_scene_fingerprint_matches_skipped():
    skipped = _save_scene()
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _save_scene()
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_create_scene_different_root_type_BLOCKED():
    """Same scene file, different root type: target is the file."""
    skipped = _create_scene("res://scenes/a.tscn", "Node2D")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _create_scene("res://scenes/a.tscn", "Node3D")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_create_scene_different_file_not_blocked():
    skipped = _create_scene("res://scenes/a.tscn", "Node2D")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _create_scene("res://scenes/b.tscn", "Node2D")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is False


def test_instantiate_scene_different_scene_BLOCKED():
    """Same parent, different scene: target is the parent."""
    skipped = _instantiate_scene("World", "res://scenes/a.tscn")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _instantiate_scene("World", "res://scenes/b.tscn")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_instantiate_scene_different_parent_not_blocked():
    skipped = _instantiate_scene("World", "res://scenes/a.tscn")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _instantiate_scene("Level", "res://scenes/a.tscn")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is False


def test_assign_resource_different_resource_BLOCKED():
    """Same node (target is the node), different resource."""
    skipped = _assign_resource("Player", "texture", "res://a.png")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _assign_resource("Player", "texture", "res://b.png")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is True


def test_assign_resource_different_node_not_blocked():
    skipped = _assign_resource("Player", "texture", "res://a.png")
    blocked = _blocked_from_action(skipped, 2, 3)
    proposed = _assign_resource("Enemy", "texture", "res://a.png")
    is_blocked, _ = is_action_blocked(proposed, blocked)
    assert is_blocked is False


def test_new_mutation_target_extraction():
    """Target extraction for the six new mutations."""
    assert extract_mutation_target(
        _edit_script("res://s.gd", "x")
    ) == ("edit_script", (("script_path", "res://s.gd"),))

    assert extract_mutation_target(
        _replace_in_script("res://s.gd", "a", "b")
    ) == ("replace_in_script", (("script_path", "res://s.gd"),))

    assert extract_mutation_target(_save_scene()) == (
        "save_scene",
        (),
    )

    assert extract_mutation_target(
        _create_scene("res://a.tscn", "Node2D")
    ) == ("create_scene", (("scene_path", "res://a.tscn"),))

    assert extract_mutation_target(
        _instantiate_scene("World", "res://a.tscn")
    ) == ("instantiate_scene", (("parent_path", "World"),))

    assert extract_mutation_target(
        _assign_resource("Player", "texture", "res://a.png")
    ) == ("assign_resource_to_property", (("node_path", "Player"),))


def test_script_mutation_target_extraction():
    """Script mutation targets: the file for create_script, the
    node's attachment for attach/detach."""
    create_action = _create_script("res://scripts/a.gd", "extends Node\n")
    target = extract_mutation_target(create_action)
    assert target == (
        "create_script",
        (("script_path", "res://scripts/a.gd"),),
    )

    attach_action = _attach_script("Player", "res://scripts/a.gd")
    target = extract_mutation_target(attach_action)
    assert target == (
        "attach_script",
        (("node_path", "Player"),),
    )

    detach_action = _detach_script("Player")
    target = extract_mutation_target(detach_action)
    assert target == (
        "detach_script",
        (("node_path", "Player"),),
    )

if __name__ == "__main__":
    test_rename_fingerprint_matches_skipped()
    test_rename_different_new_name_BLOCKED()
    test_rename_different_node_not_blocked()
    test_find_nodes_not_blocked()
    test_duplicate_fingerprint_matches()
    test_duplicate_different_source_not_blocked()
    test_empty_blocked_list_allows_anything()
    test_check_single_action_blocked()
    test_check_batch_with_blocked_item()
    test_check_batch_without_blocked_item()
    test_create_node_equivalence()
    test_delete_node_equivalence()
    test_reparent_node_equivalence()
    test_set_properties_equivalence()
    test_non_equivalent_action_allowed()
    test_fingerprint_determinism()
    test_recovery_find_nodes_allowed_after_failure()
    test_batch_containing_bypassed_rename_BLOCKED()
    test_demonstrated_bypass_BLOCKED()
    test_duplicate_different_name_BLOCKED()
    test_set_properties_different_values_BLOCKED()
    test_reparent_different_target_BLOCKED()
    test_delete_same_node_BLOCKED()
    test_mutation_target_extraction()
    test_move_child_fingerprint_matches_skipped()
    test_move_child_different_index_BLOCKED()
    test_move_child_different_node_not_blocked()
    test_connect_signal_fingerprint_matches_skipped()
    test_connect_signal_different_method_not_blocked()
    test_connect_signal_deferred_change_BLOCKED()
    test_disconnect_signal_fingerprint_matches_skipped()
    test_disconnect_signal_different_signal_not_blocked()
    test_signal_mutation_target_extraction()
    test_create_script_fingerprint_matches_skipped()
    test_create_script_different_content_BLOCKED()
    test_create_script_different_path_not_blocked()
    test_attach_script_fingerprint_matches_skipped()
    test_attach_script_different_script_BLOCKED()
    test_attach_script_different_node_not_blocked()
    test_detach_script_fingerprint_matches_skipped()
    test_detach_script_different_node_not_blocked()
    test_script_mutation_target_extraction()
    test_edit_script_different_content_BLOCKED()
    test_edit_script_different_file_not_blocked()
    test_replace_in_script_different_replacement_BLOCKED()
    test_replace_in_script_different_file_not_blocked()
    test_save_scene_fingerprint_matches_skipped()
    test_create_scene_different_root_type_BLOCKED()
    test_create_scene_different_file_not_blocked()
    test_instantiate_scene_different_scene_BLOCKED()
    test_instantiate_scene_different_parent_not_blocked()
    test_assign_resource_different_resource_BLOCKED()
    test_assign_resource_different_node_not_blocked()
    test_new_mutation_target_extraction()
    test_add_to_group_fingerprint_matches_skipped()
    test_add_to_group_different_group_BLOCKED()
    test_add_to_group_different_node_not_blocked()
    test_remove_from_group_fingerprint_matches_skipped()
    test_remove_from_group_different_group_BLOCKED()
    test_remove_from_group_different_node_not_blocked()
    print("All boundary enforcement tests PASSED")