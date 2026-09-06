# AGENT_HANDOFF.md

## Purpose

This file is the compact operational handoff for a new AI
coding/debugging session working on the Godot AI Agent project.

Read this file first, then inspect the referenced source files before
changing anything.

**Handoff date:** 2026-09-06

------------------------------------------------------------------------

# 1. What This Project Is

This is a Godot Editor AI Agent.

The architecture is split deliberately:

``` text
Python
  = reasoning, providers, decision schema, orchestration

Godot EditorPlugin
  = editor-native scene operations, undo/redo, ownership, verification

HTTP bridge
  = communication between Python and Godot
```

The long-term goal is a safe, observable, undoable, logged development
assistant rather than a simple natural-language-to-function translator.

------------------------------------------------------------------------

# 2. Source of Truth Hierarchy

When documents disagree, use this order:

1.  actual source code,
2.  `docs/CURRENT_STATE.md`,
3.  `docs/TEST_HISTORY.md`,
4.  `docs/TOOL_PROTOCOL.md`,
5.  `docs/PROVIDER_ARCHITECTURE.md`,
6.  `docs/ROADMAP.md`,
7.  `AGENTS.md`,
8.  `.agentrules/*`.

Do not blindly trust old historical prose.

The current source archive was refreshed on 2026-09-04/05 and includes the latest Cline changes.

------------------------------------------------------------------------

# 3. Important Files

## Agent core

``` text
agent/godot_agent.py
agent/schemas.py
agent/boundary.py
agent/telemetry.py
```

## Providers

``` text
models/gemini_provider.py
models/groq_provider.py
models/openrouter_provider.py
models/ollama_provider.py
```

## Configuration

``` text
config/settings.py
```

## Scene tools

``` text
tools/scene_tools.py
```

## Godot plugin

``` text
addons/Execution_Agent/ai_agent_plugin.gd
addons/Execution_Agent/bridge/ai_agent_http.gd
addons/Execution_Agent/bridge/ai_agent_router.gd
addons/Execution_Agent/scene/ai_agent_scene_helpers.gd
addons/Execution_Agent/scene/ai_agent_node_tools.gd
addons/Execution_Agent/scene/ai_agent_property_tools.gd
addons/Execution_Agent/serialization/ai_agent_variant_serializer.gd
```

## Tests

``` text
tests/test_batch_boundary.py
tests/test_gemini_provider.py
tests/test_provider_adapters.py
tests/test_provider_contract.py
```

------------------------------------------------------------------------

# 4. Current Configuration

From `config/settings.py`:

``` text
MODEL_PROVIDER = "gemini"
MAX_BATCH_SIZE = 5
OLLAMA_MODEL = "qwen3-vl:4b"
GEMINI_MODEL = "gemini-3.1-flash-lite"
OPENROUTER_MODEL = "cohere/north-mini-code:free"
```

Groq currently uses:

``` text
openai/gpt-oss-120b
```

inside its provider module.

The agent loop currently has:

``` text
MAX_STEPS = 12
```

The agent now runs as a persistent `AgentSession` spanning multiple user
turns. `final_answer` ends the current turn; `exit_session` ends the
entire session; `/exit` is the host-level escape hatch. All three are
distinct and documented in `TOOL_PROTOCOL.md`.

------------------------------------------------------------------------

# 5. Current Decision Schema

`agent/schemas.py` defines:

### Inspection

``` text
get_scene_tree
find_nodes
get_node_properties
```

### Mutation

``` text
create_node
rename_node
delete_node
reparent_node
duplicate_node
set_properties
```

### Temporary/prototype

``` text
describe_current_scene
```

`list_nodes` was an obsolete prototype action and has been removed.
It is rejected by `AgentDecision` validation, and regression tests
(`test_list_nodes_is_not_in_agent_decision`,
`test_list_nodes_is_not_in_batchable_action`) keep it out.

### Control

``` text
batch
final_answer
exit_session
```

A batch is limited to 5 actions.

`final_answer` is not a batch item.

`exit_session` is not a batch item; it terminates the entire session
(see `TOOL_PROTOCOL.md` for `final_answer` vs. `exit_session` vs.
`/exit` semantics).

------------------------------------------------------------------------

# 6. Critical Safety Invariant: Interrupted Batch Boundary

Do not weaken this.

When a batch fails partway through:

``` text
completed actions remain completed
failed action remains failed
remaining mutations are skipped
```

Skipped mutations must not be automatically resumed merely because the
original user request still mentions them.

Prompt instructions alone were insufficient.

The authoritative enforcement is Python-side.

## Where

``` text
agent/boundary.py
agent/godot_agent.py
```

## Important functions

``` text
compute_action_fingerprint()
extract_mutation_target()
is_action_blocked()
check_decision_blocked()
```

## How it works

At the start of a user session:

``` text
blocked_skipped_actions = []
```

After an interrupted batch, skipped actions are recorded with:

-   fingerprint,
-   mutation target,
-   action,
-   batch index,
-   batch size.

Before execution of a later non-final decision, the proposed decision is
checked.

If a blocked mutation is proposed:

``` text
Python rejects it
↓
Godot tool is NOT called
```

For a new batch, one blocked item causes the whole proposed batch to be
rejected.

Read-only recovery operations such as `find_nodes` remain allowed.

------------------------------------------------------------------------

# 7. Why Two-Tier Enforcement Exists

The original exact-fingerprint design could be bypassed.

Example:

``` text
skipped:
rename PlayerBatchFailureCopy → ShouldBeSkipped

model later:
rename PlayerBatchFailureCopy → RenamedPlayer
```

Different `new_name` means different exact fingerprint.

That bypass was fixed by checking the mutation target too.

For `rename_node`:

``` text
mutation target = node_path
```

Therefore any later rename targeting the same node is blocked within
that session.

The same principle applies to:

-   duplicate source node,
-   delete target node,
-   reparent target node,
-   set-properties target node.

------------------------------------------------------------------------

# 8. Current Boundary Test Result

Current `tests/test_batch_boundary.py` contains 25 uniquely named test
functions.

Pytest collects:

``` text
25 tests
```

The latest recorded direct run before the name cleanup was:

``` text
24 passed
```

The current direct run result is:

``` text
25 passed
```

The duplicate name has now been cleaned up as an isolated maintenance
change. Re-run the focused command in an environment with pytest installed.

Do not mix that cleanup with provider refactoring.

------------------------------------------------------------------------

# 9. Current Manual Runtime Result

A manual Gemini runtime test established the desired behavior:

``` text
duplicate Player
→ rename nonexistent node
→ rename duplicate (skipped)
```

After interruption:

-   the skipped mutation was recorded,
-   the model attempted it,
-   Python blocked it,
-   the model attempted a same-target bypass with a different new name,
-   Python blocked that too,
-   the model eventually finalized.

This is a confirmed runtime safety behavior and should not regress.

------------------------------------------------------------------------

# 10. Godot Editor Safety

Godot mutation tools use:

``` text
EditorUndoRedoManager
```

Current create/duplicate paths include explicit ownership handling and
verification.

Important invariants:

-   scene-relative paths,
-   `.` means edited scene root,
-   mutations should be undoable,
-   created/duplicated nodes must have correct scene ownership,
-   important mutations should report verification.

Do not replace editor-native undo behavior with ad hoc snapshots unless
explicitly redesigning the architecture.

------------------------------------------------------------------------

# 11. Path Semantics

The agent operates on paths relative to the edited scene root.

Example:

``` text
.
CharacterBody2D/PersistentEnemy
```

Do not assume:

``` text
PersistentEnemy
```

is a complete path.

Typical recovery:

``` text
find_nodes
→ resolve full path
→ mutate
→ verify
```

A previous bug caused a reparent destination to be incorrectly injected
as a `find_nodes.parent_path` filter.

That was fixed.

Preserve this rule:

``` text
destination parent ≠ automatic search scope
```

unless explicitly requested.

------------------------------------------------------------------------

# 12. Provider State

Four provider adapters are currently present.

## Gemini

Primary fast cloud provider.

Current model:

``` text
gemini-3.1-flash-lite
```

Lazy initialization is implemented.

There is a historical AFC warning. Do not refactor merely to silence it.

## Groq

Adapter exists.

Current model:

``` text
openai/gpt-oss-120b
```

It has bounded retries and rate-limit-aware pacing.

End-to-end Godot validation is the next meaningful milestone.

## OpenRouter

Adapter exists.

Current model:

``` text
cohere/north-mini-code:free
```

It requests JSON-object output and relies on local Pydantic validation.

End-to-end validation is not yet established.

## Ollama

Local provider remains available.

Current model:

``` text
qwen3-vl:4b
```

------------------------------------------------------------------------

# 13. Current Known Reliability Issues

## Model argument omissions

Gemini has historically omitted required fields in first attempts.

The agent can recover through iterative observation, but this wastes
steps.

Investigate:

-   schema clarity,
-   validation feedback,
-   conservative normalization,
-   retry guidance.

Do not build a brittle English parser.

## Context compaction

The agent has compaction code, but its behavior needs focused tests.

Before modifying it, determine exactly which recent
messages/observations survive.

## Provider maturity

The adapters exist, but presence of a provider module is not the same as
end-to-end validation.

------------------------------------------------------------------------

# 14. Current Verification

Latest source inspection confirms:

-   all four provider modules exist,
-   hard batch boundary is wired into the agent loop,
-   mutation targets are recorded for skipped actions,
-   `MAX_BATCH_SIZE = 5`,
-   `MAX_STEPS = 12`,
-   Godot node mutations use editor undo/redo,
-   ownership verification exists on relevant create/duplicate paths.

Latest local Python checks:

``` text
24 batch-boundary tests passed
project Python modules compile successfully
```

The live Gemini provider test could not run in the
documentation-generation environment because `google.genai` was
unavailable there.

Do not interpret that environment failure as proof of a Gemini runtime
regression.

------------------------------------------------------------------------

# 15. What To Do First In A New Session

Before editing:

### Step 1

Read:

``` text
AGENT_HANDOFF.md
docs/CURRENT_STATE.md
docs/TEST_HISTORY.md
```

### Step 2

Inspect:

``` text
agent/godot_agent.py
agent/boundary.py
agent/schemas.py
config/settings.py
```

### Step 3

If provider work is requested, inspect:

``` text
models/gemini_provider.py
models/groq_provider.py
models/openrouter_provider.py
models/ollama_provider.py
```

### Step 4

Run the focused safety test:

``` text
python -m pytest tests/test_batch_boundary.py -q
```

Expected current result:

``` text
25 passed
```

Full suite:

``` text
64 passed
```

### Step 5

Only then make the smallest change needed for the requested task.

------------------------------------------------------------------------

# 16. Recommended Immediate Development Order

``` text
1. Preserve batch boundary (standing invariant, not a task)
2. Clean duplicate test name (DONE)
3. Add provider contract tests (DONE: test_provider_contract.py)
4. Observability v1 telemetry (DONE: agent/telemetry.py)
5. Validate Groq end-to-end (less priority, pending)
6. Validate OpenRouter end-to-end (less priority)
7. Validate Ollama through the same contract (less priority)
8. Improve model argument reliability
9. Improve runtime provider configuration
10. Expand Godot tools
11. Consider routing/fallback
```

Do not jump to autonomous routing or large editor automation yet.

------------------------------------------------------------------------

# 17. Debugging Rules For The Secondary AI

When a failure appears:

1.  reproduce it,
2.  identify whether it is model, provider, Python orchestration,
    bridge, or Godot behavior,
3.  inspect the actual current source,
4.  add a focused test if the behavior is important,
5.  fix the smallest responsible layer,
6.  rerun the relevant test,
7.  update `CURRENT_STATE.md` and `TEST_HISTORY.md` when the behavior is
    confirmed.

Prefer deterministic fixes over prompt tweaks when the invariant is
safety-critical.

If a model proposes something unsafe, do not try to make the prompt
persuasive enough. Put the invariant in executable code.

------------------------------------------------------------------------

# 18. Architectural Non-Negotiables

Do not silently remove:

-   local Pydantic validation,
-   Python-side batch-boundary enforcement,
-   Godot editor undo/redo,
-   ownership verification,
-   structured tool results,
-   logging,
-   bounded batch size,
-   bounded agent steps.

Do not let provider-specific SDK logic spread into the agent loop.

Do not treat historical documentation as stronger evidence than current
source.

------------------------------------------------------------------------

# 19. Completed Slices and Current Next Task

The provider contract has been formalized (`PROVIDER_CONTRACT_V1.md`),
provider-level unit tests exist and pass, and Observability v1
telemetry is implemented and tested. Groq live end-to-end validation
on the existing agent loop remains pending.

Next slices should stay isolated from batch-boundary changes.

The batch boundary is currently one of the strongest correctness
guarantees in the system. Leave it alone unless the task explicitly
concerns it.

------------------------------------------------------------------------

# 20. Observability v1 Telemetry

Implemented in `agent/telemetry.py` and instrumented in
`agent/godot_agent.py` and all four provider adapters.

- Provider adapters return `ProviderResult(text, usage)`; the
  agent-facing `ask_model()` still returns the model text as a string.
- `TokenUsage` values come only from provider usage metadata,
  normalized by `normalize_usage()` (Gemini, OpenAI-compatible, and
  Ollama field names). Missing metadata is never estimated or
  fabricated.
- `SessionObservability` records model calls, tool actions (including
  batch items, validation rejections, and boundary rejections),
  batches, and context compactions.
- `AgentSession.terminate()` aggregates a `SessionSummary` and logs it
  as `"Session summary: ..."` with `total_tokens_complete` and
  `usage_unavailable_count` flags.
- `safe_error_message()` truncates error text to 200 characters and
  redacts `GEMINI_API_KEY`, `GROQ_API_KEY`, and `OPENROUTER_API_KEY`
  values before recording.
- Deferred, not implemented: JSONL telemetry export, Godot-side UI,
  cost analysis. Do not assume they exist.
