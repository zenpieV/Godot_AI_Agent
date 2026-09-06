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

    # Read-only action: target has empty fields
    find_action = _find("Something")
    target = extract_mutation_target(find_action)
    assert target == ("find_nodes", ())

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
    print("All boundary enforcement tests PASSED")