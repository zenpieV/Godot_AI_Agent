"""
Contract tests for the mutation architecture (agent/mutation.py).

Guarantees:
- mutation classification is consistent across the registry,
  agent/boundary.py, and agent/mutation.py,
- the structured mutation result contract (dict + boolean
  "success") is enforced, with contract violations recorded as
  failures, never as successes,
- verification status is derived only from the bridge's own
  "verified_*" claims and never fabricated,
- mutation telemetry records outcome, verification, and
  editor-reported undoability without replacing ToolActionTelemetry.
"""

from types import SimpleNamespace

import pytest

from agent import boundary, mutation
from agent.registry import ACTION_REGISTRY
from agent.telemetry import SessionObservability


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
    "delete_resource",
    "rename_resource",
    "create_directory",
    "run_scene_offline",
    "rename_script",
    "find_replace_across_files",
    "checkpoint_create",
    "checkpoint_restore",
    "run_project_tests",
}


# ==========================================
# 1. Classification consistency
# ==========================================


def test_registry_mutation_flags_match_canonical_set():
    """The registry's is_mutation flags match the known mutations."""
    flagged = {
        name
        for name, spec in ACTION_REGISTRY.items()
        if spec.is_mutation
    }
    assert flagged == MUTATION_ACTIONS


def test_registry_mutations_covered_by_boundary_metadata():
    """Every registry mutation is present in boundary.py metadata."""
    assert (
        set(boundary._MUTATION_TARGET_KEYS)
        == MUTATION_ACTIONS
    )
    assert (
        set(boundary._BATCH_ACTION_EQUIVALENCE_KEYS)
        == MUTATION_ACTIONS
    )


def test_is_mutation_action_delegates_to_registry():
    for name in MUTATION_ACTIONS:
        assert mutation.is_mutation_action(name) is True
    assert mutation.is_mutation_action("find_nodes") is False
    assert mutation.is_mutation_action("batch") is False
    assert mutation.is_mutation_action("nonexistent_action") is False


# ==========================================
# 2. Result contract validation
# ==========================================


def test_valid_contract_result_passes():
    ok, reason = mutation.validate_mutation_result(
        {"success": True}
    )
    assert ok is True
    assert reason == ""


@pytest.mark.parametrize(
    "bad_result",
    [
        "not a dict",
        None,
        {"success": "yes"},
        {"verified_exists": True},
    ],
    ids=["string", "none", "non_bool_success", "missing_success"],
)
def test_contract_violations_are_rejected(bad_result):
    ok, reason = mutation.validate_mutation_result(bad_result)
    assert ok is False
    assert "contract violation" in reason.lower()


# ==========================================
# 3. Verification status
# ==========================================


def test_verification_failed_on_unsuccessful_result():
    assert (
        mutation.classify_verification(
            {"success": False, "error": "boom"}
        )
        == mutation.VERIFICATION_FAILED
    )


def test_verification_unverified_without_claims():
    assert (
        mutation.classify_verification(
            {"success": True, "node_path": "Player"}
        )
        == mutation.VERIFICATION_UNVERIFIED
    )


def test_verification_verified_when_all_claims_true():
    assert (
        mutation.classify_verification(
            {
                "success": True,
                "verified_exists": True,
                "verified_owned": True,
            }
        )
        == mutation.VERIFICATION_VERIFIED
    )


def test_verification_failed_when_any_claim_false():
    assert (
        mutation.classify_verification(
            {
                "success": True,
                "verified_exists": True,
                "verified_owned": False,
            }
        )
        == mutation.VERIFICATION_FAILED
    )


def test_name_collision_detected_is_not_a_verification_claim():
    result = {
        "success": True,
        "name_collision_detected": False,
    }
    assert (
        mutation.classify_verification(result)
        == mutation.VERIFICATION_UNVERIFIED
    )



# ==========================================
# 4. Mutation records
# ==========================================


def _rename_decision():
    return SimpleNamespace(
        action="rename_node",
        node_path="Player",
        new_name="Hero",
    )


def test_record_from_successful_verified_mutation():
    decision = _rename_decision()
    record = mutation.build_mutation_record(
        decision,
        {
            "success": True,
            "node_path_after": "Hero",
            "verified_exists": True,
            "undoable": True,
        },
        turn_number=2,
        step_number=3,
        duration_ms=12.5,
    )

    assert record.action == "rename_node"
    assert record.target == (
        "rename_node",
        (("node_path", "Player"),),
    )
    assert record.success is True
    assert record.verification == mutation.VERIFICATION_VERIFIED
    assert record.undoable is True
    assert record.error is None
    assert record.contract_violation == ""
    assert record.turn_number == 2
    assert record.step_number == 3


def test_record_from_unverified_mutation():
    record = mutation.build_mutation_record(
        SimpleNamespace(action="create_node"),
        {"success": True, "node_path": "Root/NewNode"},
    )
    assert record.success is True
    assert record.verification == mutation.VERIFICATION_UNVERIFIED
    assert record.undoable is None


def test_record_from_failed_mutation_carries_error():
    record = mutation.build_mutation_record(
        SimpleNamespace(action="delete_node", node_path="Ghost"),
        {
            "success": False,
            "error": "Node not found: Ghost",
            "undoable": False,
        },
    )
    assert record.success is False
    assert record.verification == mutation.VERIFICATION_FAILED
    assert record.error == "Node not found: Ghost"
    assert record.undoable is False


def test_record_from_failed_mutation_uses_validation_error_fallback():
    record = mutation.build_mutation_record(
        SimpleNamespace(action="set_properties"),
        {"success": False, "validation_error": "bad property"},
    )
    assert record.error == "bad property"


def test_contract_violation_never_records_success():
    decision = _rename_decision()
    for bad_result in ("not a dict", {"ok": True}):
        record = mutation.build_mutation_record(
            decision, bad_result
        )
        assert record.success is False
        assert (
            record.verification
            == mutation.VERIFICATION_FAILED
        )
        assert record.undoable is None
        assert record.contract_violation != ""
        assert record.error == record.contract_violation


def test_record_is_frozen():
    record = mutation.build_mutation_record(
        _rename_decision(), {"success": True}
    )
    with pytest.raises(Exception):
        record.success = False


def test_record_from_move_child_verified_mutation():
    """A bridge move_child result with verification claims maps to
    a verified record carrying the editor-reported undoability."""
    record = mutation.build_mutation_record(
        SimpleNamespace(
            action="move_child", node_path="Second", new_index=2
        ),
        {
            "success": True,
            "action": "move_child",
            "moved": True,
            "old_index": 1,
            "new_index": 2,
            "sibling_order_before": ["A", "B", "C"],
            "sibling_order_after": ["A", "C", "B"],
            "verified_index": True,
            "verified_order": True,
            "undoable": True,
        },
        turn_number=1,
        step_number=4,
    )
    assert record.success is True
    assert record.verification == mutation.VERIFICATION_VERIFIED
    assert record.undoable is True
    assert record.target == (
        "move_child",
        (("node_path", "Second"),),
    )


def test_record_from_move_child_failed_verification():
    """A false verified_* claim downgrades the record to failed."""
    record = mutation.build_mutation_record(
        SimpleNamespace(
            action="move_child", node_path="Second", new_index=0
        ),
        {
            "success": True,
            "verified_index": True,
            "verified_order": False,
            "undoable": True,
        },
    )
    assert record.success is True  # bridge reported success
    assert record.verification == mutation.VERIFICATION_FAILED


def test_record_from_add_to_group_verified_mutation():
    """A bridge add_to_group result with verification maps to a
    verified record carrying the editor-reported undoability."""
    record = mutation.build_mutation_record(
        SimpleNamespace(
            action="add_to_group",
            node_path="Alpha",
            group_name="enemies",
        ),
        {
            "success": True,
            "action": "add_to_group",
            "changed": True,
            "was_member": False,
            "is_member": True,
            "verified_membership": True,
            "undoable": True,
        },
        turn_number=1,
        step_number=4,
    )
    assert record.success is True
    assert record.verification == mutation.VERIFICATION_VERIFIED
    assert record.undoable is True
    assert record.target == (
        "add_to_group",
        (("node_path", "Alpha"),),
    )


def test_record_from_add_to_group_idempotent_unverified():
    """An idempotent add (already a member) reports no verification
    claim; status is unverified, not failed."""
    record = mutation.build_mutation_record(
        SimpleNamespace(
            action="add_to_group",
            node_path="Alpha",
            group_name="enemies",
        ),
        {
            "success": True,
            "action": "add_to_group",
            "changed": False,
            "was_member": True,
            "is_member": True,
            "undoable": False,
        },
    )
    assert record.success is True
    assert record.verification == mutation.VERIFICATION_UNVERIFIED
    assert record.undoable is False


def test_record_from_remove_from_group_failed_verification():
    """A false verified_membership claim downgrades the record to
    failed even though the bridge reported success."""
    record = mutation.build_mutation_record(
        SimpleNamespace(
            action="remove_from_group",
            node_path="Alpha",
            group_name="enemies",
        ),
        {
            "success": True,
            "action": "remove_from_group",
            "changed": True,
            "was_member": True,
            "is_member": True,
            "verified_membership": False,
            "undoable": True,
        },
    )
    assert record.success is True  # bridge reported success
    assert record.verification == mutation.VERIFICATION_FAILED


def test_record_from_connect_signal_verified_mutation():
    """A bridge connect_signal result with a true verified_connection
    maps to a verified record; the target is the connection identity."""
    record = mutation.build_mutation_record(
        SimpleNamespace(
            action="connect_signal",
            node_path="Alpha",
            signal_name="pressed",
            target_path="Beta",
            method_name="on_pressed",
        ),
        {
            "success": True,
            "action": "connect_signal",
            "changed": True,
            "was_connected": False,
            "is_connected": True,
            "verified_connection": True,
            "undoable": True,
        },
        turn_number=2,
        step_number=3,
    )
    assert record.success is True
    assert record.verification == mutation.VERIFICATION_VERIFIED
    assert record.undoable is True
    assert record.target == (
        "connect_signal",
        (
            ("node_path", "Alpha"),
            ("signal_name", "pressed"),
            ("target_path", "Beta"),
            ("method_name", "on_pressed"),
        ),
    )


def test_record_from_connect_signal_idempotent_verified():
    """An idempotent connect (already connected) still carries the
    bridge's verified_connection claim; status is verified."""
    record = mutation.build_mutation_record(
        SimpleNamespace(
            action="connect_signal",
            node_path="Alpha",
            signal_name="pressed",
            target_path="Beta",
            method_name="on_pressed",
        ),
        {
            "success": True,
            "action": "connect_signal",
            "changed": False,
            "was_connected": True,
            "is_connected": True,
            "verified_connection": True,
            "undoable": False,
        },
    )
    assert record.success is True
    assert record.verification == mutation.VERIFICATION_VERIFIED
    assert record.undoable is False


def test_record_from_disconnect_signal_failed_verification():
    """A false verified_connection claim downgrades the record to
    failed even though the bridge reported success."""
    record = mutation.build_mutation_record(
        SimpleNamespace(
            action="disconnect_signal",
            node_path="Alpha",
            signal_name="pressed",
            target_path="Beta",
            method_name="on_pressed",
        ),
        {
            "success": True,
            "action": "disconnect_signal",
            "changed": True,
            "was_connected": True,
            "is_connected": True,
            "verified_connection": False,
            "undoable": True,
        },
    )
    assert record.success is True  # bridge reported success
    assert record.verification == mutation.VERIFICATION_FAILED


def test_record_from_create_script_verified_but_not_undoable():
    """create_script is the first mutation whose real change is NOT
    undoable (file creation): the record must carry the bridge's
    undoable: false while still verifying via the write-back check."""
    record = mutation.build_mutation_record(
        SimpleNamespace(
            action="create_script",
            script_path="res://scripts/probe.gd",
            content="extends Node\n",
        ),
        {
            "success": True,
            "action": "create_script",
            "changed": True,
            "parse_ok": True,
            "verified_write": True,
            "undoable": False,
        },
        turn_number=1,
        step_number=2,
    )
    assert record.success is True
    assert record.verification == mutation.VERIFICATION_VERIFIED
    assert record.undoable is False
    assert record.target == (
        "create_script",
        (("script_path", "res://scripts/probe.gd"),),
    )


def test_record_from_create_script_failed_write_verification():
    """A false verified_write claim (file content mismatch) downgrades
    the record to failed."""
    record = mutation.build_mutation_record(
        SimpleNamespace(
            action="create_script",
            script_path="res://scripts/probe.gd",
            content="extends Node\n",
        ),
        {
            "success": True,
            "action": "create_script",
            "changed": True,
            "parse_ok": True,
            "verified_write": False,
            "undoable": False,
        },
    )
    assert record.success is True  # bridge reported success
    assert record.verification == mutation.VERIFICATION_FAILED


def test_record_from_attach_script_verified_mutation():
    record = mutation.build_mutation_record(
        SimpleNamespace(
            action="attach_script",
            node_path="Alpha",
            script_path="res://scripts/probe.gd",
        ),
        {
            "success": True,
            "action": "attach_script",
            "changed": True,
            "was_attached": False,
            "is_attached": True,
            "verified_attachment": True,
            "undoable": True,
        },
    )
    assert record.success is True
    assert record.verification == mutation.VERIFICATION_VERIFIED
    assert record.undoable is True
    assert record.target == (
        "attach_script",
        (("node_path", "Alpha"),),
    )


def test_record_from_detach_script_idempotent_verified():
    """An idempotent detach (no script attached) still carries the
    bridge's verified_attachment claim; status is verified."""
    record = mutation.build_mutation_record(
        SimpleNamespace(
            action="detach_script",
            node_path="Alpha",
        ),
        {
            "success": True,
            "action": "detach_script",
            "changed": False,
            "was_attached": False,
            "is_attached": False,
            "verified_attachment": True,
            "undoable": False,
        },
    )
    assert record.success is True
    assert record.verification == mutation.VERIFICATION_VERIFIED
    assert record.undoable is False


def test_record_from_edit_script_verified_non_undoable():
    """edit_script is a real, non-undoable file mutation; the
    record carries undoable: false with the write-back claim."""
    record = mutation.build_mutation_record(
        SimpleNamespace(
            action="edit_script",
            script_path="res://scripts/probe.gd",
            content="extends Node\n",
        ),
        {
            "success": True,
            "action": "edit_script",
            "changed": True,
            "parse_ok": True,
            "verified_write": True,
            "undoable": False,
        },
    )
    assert record.success is True
    assert record.verification == mutation.VERIFICATION_VERIFIED
    assert record.undoable is False


def test_record_from_replace_in_script_failed_verification():
    """A false verified_write claim downgrades the record."""
    record = mutation.build_mutation_record(
        SimpleNamespace(
            action="replace_in_script",
            script_path="res://scripts/probe.gd",
            old_string="10",
            new_string="20",
        ),
        {
            "success": True,
            "action": "replace_in_script",
            "changed": True,
            "verified_write": False,
            "undoable": False,
        },
    )
    assert record.success is True
    assert record.verification == mutation.VERIFICATION_FAILED


def test_record_from_save_scene_verified_non_undoable():
    record = mutation.build_mutation_record(
        SimpleNamespace(action="save_scene"),
        {
            "success": True,
            "action": "save_scene",
            "changed": True,
            "verified_write": True,
            "undoable": False,
        },
    )
    assert record.success is True
    assert record.verification == mutation.VERIFICATION_VERIFIED
    assert record.undoable is False
    assert record.target == ("save_scene", ())


def test_record_from_create_scene_failed_write():
    record = mutation.build_mutation_record(
        SimpleNamespace(
            action="create_scene",
            scene_path="res://scenes/a.tscn",
            root_node_type="Node2D",
        ),
        {
            "success": True,
            "action": "create_scene",
            "changed": True,
            "verified_write": False,
            "undoable": False,
        },
    )
    assert record.success is True
    assert record.verification == mutation.VERIFICATION_FAILED


def test_record_from_instantiate_scene_verified_mutation():
    record = mutation.build_mutation_record(
        SimpleNamespace(
            action="instantiate_scene",
            parent_path="World",
            scene_path="res://scenes/enemy.tscn",
        ),
        {
            "success": True,
            "action": "instantiate_scene",
            "changed": True,
            "verified_instance": True,
            "undoable": True,
        },
    )
    assert record.success is True
    assert record.verification == mutation.VERIFICATION_VERIFIED
    assert record.undoable is True
    assert record.target == (
        "instantiate_scene",
        (("parent_path", "World"),),
    )


def test_record_from_assign_resource_verified_mutation():
    record = mutation.build_mutation_record(
        SimpleNamespace(
            action="assign_resource_to_property",
            node_path="Player",
            property_name="texture",
            resource_path="res://icon.svg",
        ),
        {
            "success": True,
            "action": "assign_resource_to_property",
            "changed": True,
            "verified_assignment": True,
            "undoable": True,
        },
    )
    assert record.success is True
    assert record.verification == mutation.VERIFICATION_VERIFIED
    assert record.undoable is True
    assert record.target == (
        "assign_resource_to_property",
        (("node_path", "Player"),),
    )


# ==========================================
# 5. Telemetry integration
# ==========================================


@pytest.fixture(scope="module")
def godot_agent_module():
    """Import agent.godot_agent the same way test_provider_contract
    does: providers and input are stubbed so the import bootstrap
    turn completes without any live provider call or stdin read."""
    import builtins
    import json

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


def test_record_mutation_appends_mutation_telemetry():
    obs = SessionObservability("mut-tel")
    record = mutation.build_mutation_record(
        _rename_decision(),
        {"success": True, "verified_exists": True, "undoable": True},
        turn_number=1,
        step_number=2,
        duration_ms=5.0,
    )
    obs.record_mutation(record, model_call_id="mc1")

    assert len(obs.mutations) == 1
    entry = obs.mutations[0]
    assert entry.session_id == "mut-tel"
    assert entry.action == "rename_node"
    assert entry.success is True
    assert entry.verification == mutation.VERIFICATION_VERIFIED
    assert entry.undoable is True
    assert entry.model_call_id == "mc1"
    assert entry.contract_violation == ""


def test_summary_counts_mutations():
    obs = SessionObservability("mut-sum")
    obs.record_mutation(
        mutation.build_mutation_record(
            _rename_decision(),
            {"success": True, "verified_exists": True},
            turn_number=1,
            step_number=1,
        )
    )
    obs.record_mutation(
        mutation.build_mutation_record(
            SimpleNamespace(action="create_node"),
            {"success": True},
            turn_number=1,
            step_number=2,
        )
    )
    obs.record_mutation(
        mutation.build_mutation_record(
            SimpleNamespace(action="delete_node"),
            {"success": False, "error": "nope"},
            turn_number=1,
            step_number=3,
        )
    )

    summary = obs.get_summary(
        turns_completed=1,
        termination_reason="test",
    )
    assert summary.mutation_count == 3
    assert summary.successful_mutation_count == 2
    assert summary.failed_mutation_count == 1
    assert summary.unverified_mutation_count == 1


def test_mutation_recorded_in_addition_to_tool_action_telemetry(
    godot_agent_module,
):
    """The existing tool-action telemetry contract is preserved."""
    from agent.schemas import RenameNodeAction
    from tools import scene_tools

    godot_agent = godot_agent_module
    obs = SessionObservability("mut-hook")
    calls = []
    original = scene_tools.rename_node

    def fake_rename_node(node_path, new_name):
        calls.append((node_path, new_name))
        return {
            "success": True,
            "verified_exists": True,
            "undoable": True,
        }

    scene_tools.rename_node = fake_rename_node
    try:
        result = godot_agent.execute_single_action(
            RenameNodeAction(
                reason="r",
                action="rename_node",
                node_path="Player",
                new_name="Hero",
            ),
            observability=obs,
            turn_number=1,
            step_number=1,
        )
    finally:
        scene_tools.rename_node = original

    assert result["success"] is True
    assert calls == [("Player", "Hero")]
    assert len(obs.tool_actions) == 1
    assert obs.tool_actions[0].action == "rename_node"
    assert len(obs.mutations) == 1
    assert obs.mutations[0].success is True
    assert obs.mutations[0].verification == "verified"


def test_non_mutation_action_records_no_mutation_telemetry(
    godot_agent_module,
):
    from agent.schemas import FindNodesAction
    from tools import scene_tools

    godot_agent = godot_agent_module
    obs = SessionObservability("no-mut")
    original = scene_tools.find_nodes

    def fake_find_nodes(**kwargs):
        return {"success": True, "matches": []}

    scene_tools.find_nodes = fake_find_nodes
    try:
        godot_agent.execute_single_action(
            FindNodesAction(
                reason="r",
                action="find_nodes",
                node_name="Player",
            ),
            observability=obs,
        )
    finally:
        scene_tools.find_nodes = original

    assert len(obs.tool_actions) == 1
    assert obs.mutations == []
