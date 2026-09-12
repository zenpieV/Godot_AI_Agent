"""
Tests for bridge input mode handling and the Plan/Act mode
surface (agent/bridge_input.py + agent/godot_agent.py helpers).

Contract:
- the input channel carries a per-turn mode ("plan"/"act"),
- stdin mode parses a leading "/plan " prefix,
- mode_directive() produces the per-turn instruction block,
- MAX_STEPS comes from config.settings (raised from the
  original 12 so complex tasks fit in one turn).
"""

import json

import pytest

from agent import bridge_input as bridge_input_module
from agent.bridge_input import fetch_pending_input


@pytest.fixture(scope="module")
def agent_module():
    """Bootstrap-import the agent module without live
    providers (same pattern as test_registry.py)."""
    import builtins

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


def _fake_urlopen(monkeypatch, payload, fail=False):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    def fake_urlopen(request, timeout=None):
        if fail:
            raise OSError("bridge down")
        return FakeResponse()

    monkeypatch.setattr(
        bridge_input_module.urllib.request,
        "urlopen",
        fake_urlopen,
    )


def test_fetch_returns_mode(monkeypatch):
    _fake_urlopen(
        monkeypatch,
        {
            "success": True,
            "pending": True,
            "text": "Plan the enemy setup.",
            "mode": "plan",
            "selected_model": "",
            "selected_provider": "",
        },
    )

    result = fetch_pending_input(
        bridge_url="http://127.0.0.1:9999"
    )

    assert result["reachable"] is True
    assert result["text"] == "Plan the enemy setup."
    assert result["mode"] == "plan"


def test_fetch_defaults_missing_mode_to_empty(monkeypatch):
    _fake_urlopen(
        monkeypatch,
        {"success": True, "text": "hello"},
    )

    result = fetch_pending_input(
        bridge_url="http://127.0.0.1:9999"
    )

    assert result["mode"] == ""


def test_fetch_unreachable_has_empty_fields(monkeypatch):
    _fake_urlopen(monkeypatch, {}, fail=True)

    result = fetch_pending_input(
        bridge_url="http://127.0.0.1:9999"
    )

    assert result["reachable"] is False
    assert result["text"] == ""
    assert result["mode"] == ""


def test_stdin_plan_prefix(agent_module, monkeypatch):
    import builtins

    monkeypatch.setattr(agent_module, "AGENT_INPUT_MODE", "stdin")

    monkeypatch.setattr(
        builtins,
        "input",
        lambda prompt="": "/plan create three enemy nodes",
    )

    text, mode = agent_module.read_user_request()

    assert (text, mode) == (
        "create three enemy nodes",
        "plan",
    )


def test_stdin_act_mode_default(agent_module, monkeypatch):
    import builtins

    monkeypatch.setattr(agent_module, "AGENT_INPUT_MODE", "stdin")

    monkeypatch.setattr(
        builtins,
        "input",
        lambda prompt="": "just do the thing",
    )

    text, mode = agent_module.read_user_request()

    assert (text, mode) == ("just do the thing", "act")


def test_stdin_bare_plan_falls_back_to_act(
    agent_module, monkeypatch, capsys
):
    import builtins

    monkeypatch.setattr(agent_module, "AGENT_INPUT_MODE", "stdin")

    monkeypatch.setattr(
        builtins,
        "input",
        lambda prompt="": "/plan",
    )

    text, mode = agent_module.read_user_request()

    # A bare /plan has nothing to plan: it is treated as a
    # normal act-mode request rather than an empty turn.
    assert (text, mode) == ("/plan", "act")
    assert "act mode" in capsys.readouterr().out


def test_mode_directive_blocks_mutations_in_plan(agent_module):
    plan = agent_module.mode_directive("plan")

    assert "PLAN" in plan
    assert "final_answer" in plan
    assert "refuse" in plan.lower()

    act = agent_module.mode_directive("act")

    assert act == "TURN MODE: ACT."


def test_max_steps_raised_and_settings_owned(agent_module):
    from config import settings

    assert settings.MAX_STEPS >= 30
    assert agent_module.MAX_STEPS == settings.MAX_STEPS


def test_plan_mode_violation_detection(agent_module):
    """The loop's plan-mode guard keys off
    is_mutation_action; pin the semantics for the actions a
    plan turn will realistically propose."""
    from agent.mutation import is_mutation_action

    # Mutations and file creation are refused in plan mode.
    assert is_mutation_action("create_node") is True
    assert is_mutation_action("create_script") is True
    assert is_mutation_action("create_scene") is True
    assert is_mutation_action("set_properties") is True

    # Inspections and control actions are allowed.
    assert is_mutation_action("find_nodes") is False
    assert is_mutation_action("get_scene_tree") is False
    assert is_mutation_action("final_answer") is False
