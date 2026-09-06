import builtins
import json
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from agent.boundary import (
    check_decision_blocked,
    compute_action_fingerprint,
    extract_mutation_target,
)
from agent.schemas import (
    BatchAction,
    BatchableAction,
    ExitSessionAction,
    FinalAnswerAction,
    RenameNodeAction,
)
from agent.telemetry import (
    ProviderResult,
    SessionObservability,
    TokenUsage,
)


@pytest.fixture(scope="module")
def agent_module():
    """Import the real agent functions without starting a live provider call."""
    import models.gemini_provider as gemini_provider
    import models.groq_provider as groq_provider

    original_gemini = gemini_provider.ask_gemini
    original_groq = groq_provider.ask_groq
    original_input = builtins.input

    input_responses = iter(
        [
            "bootstrap import",
        ]
    )

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


def test_valid_structured_action_and_final_answer(agent_module):
    action = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "rename_node",
                "reason": "Use the known path.",
                "node_path": "Player",
                "new_name": "Hero",
            }
        )
    )
    final = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "final_answer",
                "reason": "The operation is complete.",
                "final_answer": "Done.",
            }
        )
    )

    assert isinstance(action, RenameNodeAction)
    assert isinstance(final, FinalAnswerAction)


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        '{"action": "rename_node", "reason": "missing path", "new_name": "Hero"}',
        '{"action": "does_not_exist", "reason": "invalid action"}',
    ],
)
def test_malformed_missing_and_invalid_actions_are_rejected(
    agent_module,
    payload,
):
    with pytest.raises(ValidationError):
        agent_module.AGENT_DECISION_ADAPTER.validate_json(payload)


def test_invalid_action_arguments_are_rejected(agent_module):
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "set_properties",
                "reason": "Invalid property payload.",
                "node_path": "Player",
                "properties_json": "not json",
            }
        )
    )

    valid, error = agent_module.validate_agent_action(decision)

    assert valid is False
    assert "valid serialized JSON" in error


def test_nested_parameters_normalize_then_validate(agent_module):
    normalized = agent_module.normalize_agent_response(
        json.dumps(
            {
                "action": "create_node",
                "reason": "Create the requested node.",
                "parameters": {
                    "parent_path": ".",
                    "node_type": "Node2D",
                    "node_name": "Probe",
                },
            }
        )
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(normalized)

    assert decision.action == "create_node"
    assert decision.parent_path == "."


def test_provider_error_propagates_through_ask_model(agent_module, monkeypatch):
    provider_error = RuntimeError("provider unavailable")
    monkeypatch.setattr(agent_module, "MODEL_PROVIDER", "gemini")
    monkeypatch.setattr(
        agent_module,
        "ask_gemini",
        Mock(side_effect=provider_error),
    )

    with pytest.raises(RuntimeError, match="provider unavailable"):
        agent_module.ask_model([])


def test_tool_result_continuation_and_multi_step_decisions(agent_module, monkeypatch):
    responses = iter(
        [
            json.dumps(
                {
                    "action": "find_nodes",
                    "reason": "Locate the target.",
                    "node_name": "Player",
                }
            ),
            json.dumps(
                {
                    "action": "final_answer",
                    "reason": "The result identifies the target.",
                    "final_answer": "Player is at Player.",
                }
            ),
        ]
    )
    provider = Mock(side_effect=lambda **kwargs: next(responses))
    monkeypatch.setattr(agent_module, "MODEL_PROVIDER", "gemini")
    monkeypatch.setattr(agent_module, "ask_gemini", provider)

    conversation = [
        {"role": "user", "content": "Find Player."},
    ]
    first = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        agent_module.ask_model(conversation)
    )
    conversation.extend(
        [
            {"role": "assistant", "content": first.model_dump_json()},
            {
                "role": "tool",
                "content": json.dumps(
                    {
                        "success": True,
                        "nodes": [{"path": "Player"}],
                    }
                ),
            },
        ]
    )
    second = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        agent_module.ask_model(conversation)
    )

    assert first.action == "find_nodes"
    assert second.action == "final_answer"
    assert provider.call_count == 2
    assert provider.call_args_list[1].kwargs["conversation"][-1]["role"] == "tool"


def test_agent_session_keeps_state_across_user_turns(agent_module, monkeypatch):
    conversation = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "first turn"},
    ]
    session = agent_module.AgentSession(
        conversation,
        logging.getLogger("agent-session-test"),
        "first turn",
    )
    session.execution_result_records.append(
        {"step": 1, "action": "create_node"}
    )
    session.blocked_skipped_actions.append(
        {"action": "rename_node"}
    )

    monkeypatch.setattr(
        builtins,
        "input",
        lambda prompt: "second turn",
    )

    steps = session.iter_steps(3)
    assert next(steps) == 0

    session.complete_turn()

    assert next(steps) == 0
    assert session.current_request == "second turn"
    assert len(session.execution_result_records) == 1
    assert len(session.blocked_skipped_actions) == 1
    assert conversation[-1]["role"] == "user"
    assert "second turn" in conversation[-1]["content"]

    session.closed = True


def test_agent_session_termination_preserves_state(agent_module):
    conversation = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "current turn"},
    ]
    execution_history = [
        {"step": 1, "action": "create_node"},
    ]
    blocked_actions = [
        {"action": "rename_node"},
    ]
    session = agent_module.AgentSession(
        conversation,
        logging.getLogger("agent-session-termination-test"),
        "current turn",
    )
    session.execution_result_records.extend(execution_history)
    session.blocked_skipped_actions.extend(blocked_actions)

    session.terminate()

    assert session.closed is True
    assert session.conversation is conversation
    assert session.execution_result_records == execution_history
    assert session.blocked_skipped_actions == blocked_actions


def test_terminated_session_does_not_begin_another_turn(
    agent_module,
    monkeypatch,
):
    session = agent_module.AgentSession(
        [{"role": "user", "content": "current turn"}],
        logging.getLogger("agent-session-closed-test"),
        "current turn",
    )
    session.terminate()
    input_mock = Mock(side_effect=AssertionError("input was called"))
    monkeypatch.setattr(builtins, "input", input_mock)

    steps = session.iter_steps(3)

    with pytest.raises(StopIteration):
        next(steps)

    input_mock.assert_not_called()


def test_exit_command_terminates_without_prompting_again(
    agent_module,
    monkeypatch,
):
    session = agent_module.AgentSession(
        [{"role": "user", "content": "current turn"}],
        logging.getLogger("agent-session-exit-command-test"),
        "current turn",
    )
    inputs = iter([agent_module.AgentSession.TERMINATION_COMMAND])
    monkeypatch.setattr(builtins, "input", lambda prompt: next(inputs))

    assert session.begin_next_turn() is False
    assert session.closed is True


def test_context_compaction_uses_existing_implementation(agent_module):
    logger = logging.getLogger("provider-contract-test")
    conversation = [
        {"role": "tool", "content": "x" * 1000},
        {"role": "tool", "content": "y" * 1000},
        {"role": "tool", "content": "z" * 1000},
    ]
    records = [
        {
            "step": index,
            "action": "find_nodes",
            "conversation_index": index,
            "tool_result": {"success": True, "nodes": []},
            "compacted": False,
        }
        for index in range(3)
    ]

    agent_module.compact_conversation(conversation, records, logger)

    assert "AGENT EXECUTION RESULT SUMMARY" in conversation[0]["content"]
    assert conversation[1]["content"] == "y" * 1000
    assert conversation[2]["content"] == "z" * 1000


def test_batch_boundary_blocks_exact_and_same_target_resume():
    skipped = RenameNodeAction(
        action="rename_node",
        reason="skipped",
        node_path="Player",
        new_name="SkippedName",
    )
    blocked = [
        {
            "fingerprint": compute_action_fingerprint(skipped),
            "mutation_target": extract_mutation_target(skipped),
            "action": skipped.action,
            "batch_index": 2,
            "batch_size": 2,
        }
    ]

    exact_blocked, _, _ = check_decision_blocked(skipped, blocked)
    bypass_blocked, _, _ = check_decision_blocked(
        skipped.model_copy(update={"new_name": "DifferentName"}),
        blocked,
    )
    recovery_allowed, _, _ = check_decision_blocked(
        agent_module_find_nodes(),
        blocked,
    )

    assert exact_blocked is True
    assert bypass_blocked is True
    assert recovery_allowed is False


def agent_module_find_nodes():
    from agent.schemas import FindNodesAction

    return FindNodesAction(
        action="find_nodes",
        reason="inspect",
        node_name="Player",
    )


def test_exit_session_action_validates(agent_module):
    """ExitSessionAction validates successfully."""
    action = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "exit_session",
                "reason": "session complete",
                "exit_summary": "All tasks finished.",
            }
        )
    )
    assert isinstance(action, ExitSessionAction)
    assert action.action == "exit_session"
    assert action.exit_summary == "All tasks finished."


def test_exit_session_requires_exit_summary(agent_module):
    """exit_summary is required for exit_session."""
    with pytest.raises(ValidationError):
        agent_module.AGENT_DECISION_ADAPTER.validate_json(
            json.dumps(
                {
                    "action": "exit_session",
                    "reason": "done",
                }
            )
        )


def test_exit_session_is_valid_agent_decision(agent_module):
    """exit_session is accepted as a valid AgentDecision."""
    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "exit_session",
                "reason": "work complete",
                "exit_summary": "Done.",
            }
        )
    )
    assert decision.action == "exit_session"


def test_exit_session_closes_session(agent_module):
    """exit_session closes an active AgentSession."""
    session = agent_module.AgentSession(
        [{"role": "user", "content": "current turn"}],
        logging.getLogger("exit-session-close-test"),
        "current turn",
    )
    assert session.closed is False

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "exit_session",
                "reason": "done",
                "exit_summary": "Session complete.",
            }
        )
    )

    # Simulate the dispatch: terminate and continue
    session.terminate()

    assert session.closed is True
    assert session.turn_completed is False


def test_exit_session_does_not_begin_another_turn(
    agent_module,
    monkeypatch,
):
    """exit_session does not prompt for another user turn."""
    session = agent_module.AgentSession(
        [{"role": "user", "content": "current turn"}],
        logging.getLogger("exit-session-no-turn-test"),
        "current turn",
    )
    session.terminate()
    input_mock = Mock(side_effect=AssertionError("input was called"))
    monkeypatch.setattr(builtins, "input", input_mock)

    steps = session.iter_steps(3)

    with pytest.raises(StopIteration):
        next(steps)

    input_mock.assert_not_called()


def test_final_answer_leaves_session_open(
    agent_module,
    monkeypatch,
):
    """final_answer completes the turn but leaves the session open."""
    session = agent_module.AgentSession(
        [{"role": "user", "content": "current turn"}],
        logging.getLogger("final-answer-open-test"),
        "current turn",
    )

    decision = agent_module.AGENT_DECISION_ADAPTER.validate_json(
        json.dumps(
            {
                "action": "final_answer",
                "reason": "done",
                "final_answer": "Done.",
            }
        )
    )

    assert decision.action == "final_answer"

    # Simulate dispatch: complete_turn, then continue
    session.complete_turn()
    assert session.turn_completed is True
    assert session.closed is False

    # Now iter_steps would call begin_next_turn, which prompts
    inputs = iter(["next request"])
    monkeypatch.setattr(builtins, "input", lambda prompt: next(inputs))

    steps = session.iter_steps(3)
    # The generator should be able to produce a step
    # because the session is not closed
    try:
        next(steps)
    except StopIteration:
        pytest.fail(
            "iter_steps should not exhaust when session is open"
        )


def test_exit_command_still_terminates(agent_module, monkeypatch):
    """/exit still terminates the session."""
    session = agent_module.AgentSession(
        [{"role": "user", "content": "current turn"}],
        logging.getLogger("exit-command-test"),
        "current turn",
    )
    inputs = iter([agent_module.AgentSession.TERMINATION_COMMAND])
    monkeypatch.setattr(
        builtins, "input", lambda prompt: next(inputs)
    )

    assert session.begin_next_turn() is False
    assert session.closed is True


def test_exit_session_preserves_session_state(agent_module):
    """Termination preserves accumulated conversation/state."""
    conversation = [{"role": "user", "content": "turn 1"}]
    session = agent_module.AgentSession(
        conversation,
        logging.getLogger("exit-session-state-test"),
        "turn 1",
    )
    session.execution_result_records.extend(
        [{"step": 0, "action": "find_nodes"}]
    )
    session.blocked_skipped_actions.append(
        {"action": "rename_node"}
    )

    session.terminate()

    assert session.closed is True
    assert session.conversation is conversation
    assert len(session.execution_result_records) == 1
    assert len(session.blocked_skipped_actions) == 1


def test_exit_session_excluded_from_batch():
    """exit_session is excluded from BatchableAction."""
    from pydantic import TypeAdapter

    from agent.schemas import BatchableAction

    adapter = TypeAdapter(BatchableAction)
    with pytest.raises(ValidationError):
        adapter.validate_json(
            json.dumps(
                {
                    "action": "exit_session",
                    "reason": "done",
                    "exit_summary": "Should not be batchable.",
                }
            )
        )


def test_iter_steps_terminates_after_close(agent_module):
    """
    After session.terminate() is called while iter_steps() is
    suspended at a yield, the generator must immediately raise
    StopIteration on the next advance and must not yield another
    step. This prevents unnecessary model/API calls after
    exit_session.
    """
    session = agent_module.AgentSession(
        [{"role": "user", "content": "current turn"}],
        logging.getLogger("iter-steps-terminate-test"),
        "current turn",
    )
    steps = session.iter_steps(5)

    first = next(steps)
    assert first == 0
    assert session.closed is False

    # Simulate exit_session handler: terminate while suspended
    session.terminate()
    assert session.closed is True

    with pytest.raises(StopIteration):
        next(steps)


def test_list_nodes_is_not_in_batchable_action():
    """Regression: list_nodes is an obsolete prototype action.

    It must NOT be accepted as a BatchableAction. Previously, list_nodes
    was batchable and its Python implementation returned a list instead
    of a dict, causing:
        AttributeError: 'list' object has no attribute 'get'
    inside execute_batch_actions().
    """
    from pydantic import TypeAdapter

    adapter = TypeAdapter(BatchableAction)
    with pytest.raises(ValidationError):
        adapter.validate_json(
            json.dumps(
                {
                    "action": "list_nodes",
                    "reason": "should be rejected",
                }
            )
        )


def test_list_nodes_is_not_in_agent_decision():
    """list_nodes must not be a valid top-level AgentDecision either."""
    from pydantic import TypeAdapter

    from agent.schemas import AgentDecision

    adapter = TypeAdapter(AgentDecision)
    with pytest.raises(ValidationError):
        adapter.validate_json(
            json.dumps(
                {
                    "action": "list_nodes",
                    "reason": "should be rejected",
                }
            )
        )


def test_model_usage_available_is_recorded(agent_module, monkeypatch):
    telemetry = SessionObservability("usage-session")
    monkeypatch.setattr(agent_module, "MODEL_PROVIDER", "gemini")
    monkeypatch.setattr(
        agent_module,
        "ask_gemini",
        lambda **kwargs: ProviderResult(
            text='{"action":"final_answer"}',
            usage=TokenUsage(11, 7, 18, True),
        ),
    )

    result = agent_module.ask_model(
        [], telemetry, turn_number=2, step_number=3
    )

    assert result == '{"action":"final_answer"}'
    call = telemetry.model_calls[0]
    assert call.provider == "gemini"
    assert call.model == agent_module.GEMINI_MODEL
    assert call.usage.input_tokens == 11
    assert call.usage.output_tokens == 7
    assert call.usage.total_tokens == 18
    assert call.usage.available is True
    assert call.duration_ms >= 0


def test_model_usage_unavailable_is_not_fabricated(agent_module, monkeypatch):
    telemetry = SessionObservability("unknown-usage-session")
    monkeypatch.setattr(agent_module, "MODEL_PROVIDER", "gemini")
    monkeypatch.setattr(
        agent_module,
        "ask_gemini",
        lambda **kwargs: ProviderResult(
            text='{"action":"final_answer"}'
        ),
    )

    agent_module.ask_model([], telemetry, turn_number=1, step_number=1)

    usage = telemetry.model_calls[0].usage
    assert usage.available is False
    assert usage.input_tokens is None
    assert usage.output_tokens is None
    assert usage.total_tokens is None


def test_model_failure_records_duration_and_error(agent_module, monkeypatch):
    telemetry = SessionObservability("failure-session")
    monkeypatch.setattr(agent_module, "MODEL_PROVIDER", "gemini")
    monkeypatch.setattr(
        agent_module,
        "ask_gemini",
        Mock(side_effect=RuntimeError("provider unavailable")),
    )

    with pytest.raises(RuntimeError, match="provider unavailable"):
        agent_module.ask_model([], telemetry, turn_number=1, step_number=1)

    call = telemetry.model_calls[0]
    assert call.success is False
    assert call.duration_ms >= 0
    assert "provider unavailable" in call.error


def test_batch_telemetry_preserves_batch_boundary(agent_module, monkeypatch):
    telemetry = SessionObservability("batch-session")
    decision = BatchAction(
        action="batch",
        reason="run known actions",
        actions=[
            RenameNodeAction(
                action="rename_node",
                reason="first",
                node_path="A",
                new_name="B",
            ),
            RenameNodeAction(
                action="rename_node",
                reason="second",
                node_path="B",
                new_name="C",
            ),
        ],
    )
    monkeypatch.setattr(
        agent_module,
        "execute_single_action",
        lambda decision, **kwargs: {"success": True},
    )

    result = agent_module.execute_batch_actions(
        decision,
        "rename the nodes",
        logging.getLogger("batch-telemetry-test"),
        observability=telemetry,
        turn_number=1,
        step_number=2,
    )

    assert result["success"] is True
    batch = telemetry.batches[0]
    assert batch.batch_size == 2
    assert batch.succeeded_count == 2
    assert batch.failed_count == 0
    assert batch.stopped_early is False
    assert batch.duration_ms >= 0


def test_session_summary_aggregates_known_and_unknown_usage():
    telemetry = SessionObservability("summary-session")
    telemetry.record_model_call(
        "call-1", 1, 1, "gemini", "test-model", 4.0,
        TokenUsage(10, 5, 15, True), True,
    )
    telemetry.record_model_call(
        "call-2", 1, 2, "ollama", "test-model", 2.0,
        TokenUsage(), True,
    )
    telemetry.record_tool_action(1, 1, "rename_node", True, 1.0)
    telemetry.record_tool_action(1, 2, "delete_node", False, 1.0)
    telemetry.record_batch(1, 3, 2, 2, 0, False, None, 2.0, True)
    telemetry.record_compaction(1, 3, 1000, 100, "find_nodes")

    summary = telemetry.get_summary(1, "test complete")

    assert summary.turns_completed == 1
    assert summary.agent_steps == 2
    assert summary.model_calls == 2
    assert summary.total_input_tokens == 10
    assert summary.total_output_tokens == 5
    assert summary.total_tokens == 15
    assert summary.total_tokens_complete is False
    assert summary.usage_unavailable_count == 1
    assert summary.tool_action_count == 2
    assert summary.successful_action_count == 1
    assert summary.failed_action_count == 1
    assert summary.batch_count == 1
    assert summary.total_batched_actions == 2
    assert summary.compaction_count == 1
    assert summary.termination_reason == "test complete"


def agent_module_find_nodes():
    from agent.schemas import FindNodesAction

    return FindNodesAction(
        action="find_nodes",
        reason="inspect",
        node_name="Player",
    )
