"""
Catalog sync test: every registered action must be
documented in the system-prompt catalog. The catalog is
hand-maintained prose inside godot_agent.py's system
prompt; this test catches the drift where an action is
added to the registry but never explained to the model
(the model would then never select it).
"""

import builtins
import json

import pytest


@pytest.fixture(scope="module")
def agent_module():
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


def test_every_registered_action_is_in_catalog(agent_module):
    from agent.registry import ACTION_REGISTRY

    system_prompt = agent_module.conversation[0]["content"]

    missing = [
        name
        for name in ACTION_REGISTRY
        if name not in system_prompt
    ]

    assert missing == [], (
        "Actions missing from the system-prompt catalog: "
        + ", ".join(missing)
    )


def test_catalog_numbering_reaches_last_action(agent_module):
    from agent.registry import ACTION_REGISTRY

    system_prompt = agent_module.conversation[0]["content"]

    # The catalog numbers its entries; the highest number
    # must cover the total action count.
    import re

    numbers = [
        int(match)
        for match in re.findall(
            r"^(\d+)\. \w", system_prompt, re.MULTILINE
        )
    ]

    assert numbers, "catalog numbering not found"
    assert max(numbers) >= len(ACTION_REGISTRY), (
        "Catalog numbering ends at "
        + str(max(numbers))
        + " but the registry holds "
        + str(len(ACTION_REGISTRY))
        + " actions."
    )
