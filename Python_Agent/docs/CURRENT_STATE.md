# Current Project State

## Purpose of This File

This document records the current, dynamic state of the Godot AI Agent project.

Update this file after meaningful implementation milestones, architectural changes, successful tests, major failures, or changes to the immediate development focus.

Do not treat this file as permanent architecture documentation.

For stable architecture, see:

* `AGENTS.md`
* `.agentrules/rules/01-DEVELOPMENT_RULES.md`
* `.agentrules/rules/02-PROJECT_ARCHITECTURE.md`

---

# Current Development Phase

The project currently has a functioning early agent foundation capable of performing iterative reasoning and several Godot Editor scene operations through the Python-to-Godot bridge.

The current priority is to stabilize and formalize the existing agent architecture before expanding aggressively into:

* Additional model providers.
* More advanced Godot operations.
* Large-scale editor automation.
* Complex project modification.
* Autonomous multi-stage development tasks.

The immediate architectural direction is:

1. Stabilize tool semantics.
2. Reduce unnecessary model retries.
3. Improve deterministic validation and constraint handling.
4. Establish a clean provider abstraction.
5. Add Groq alongside Gemini and Ollama.
6. Continue expanding Godot editor operations incrementally.

---

# Recent Implementation: Hardening Slice 1

A minimal hardening slice has been implemented to improve agent robustness without broad refactoring.

## Changes

### Session and Step Logging
- Added structured logging with session IDs
- Logs session start, each step number, and completion
- Output to console and agent.log file
- LogLevel, timestamps, and session ID included in all logs

### Graceful Failure Handling
- Added try-except around `ask_model()` call
  - Catches provider/model invocation failures
  - Logs error details with session context
  - Exits gracefully with user-friendly message
- Added try-except around `AgentDecision.model_validate_json()` call
  - Catches Pydantic ValidationError and other exceptions
  - Logs response sample (first 200 chars) and error
  - Exits gracefully with user-friendly message

### Deferred Gemini Initialization
- Moved API key validation and client initialization from module import to first ask_gemini() call
- Allows agent to start with Ollama provider even if GEMINI_API_KEY is missing
- Raises same ValueError at first use if key is absent

## Impact
- Agent no longer crashes on provider/model errors; logs and exits gracefully
- Agent can be imported and used with Ollama even if Gemini key is missing
- Sessions are tracked with unique IDs for better debugging
- All agent steps and errors are now logged to file for analysis
- Error messages are user-friendly instead of raw Python tracebacks

## Files Modified
- `agent/godot_agent.py` (logging setup, try-except boundaries)
- `models/gemini_provider.py` (deferred initialization)

## Backward Compatibility
- All existing successful execution paths preserved
- No changes to AgentDecision schema
- No changes to tool semantics or HTTP protocol
- Only adds logging and error handling; does not change core behavior

See `/memories/repo/HARDENING_SLICE_1_COMPLETED.md` for detailed implementation notes.

---

# Bug Fix: Interrupted Batch Execution Boundary (Hard Enforcement)

A targeted bug fix was implemented to prevent skipped batch actions from being automatically resumed by the model on subsequent reasoning steps.

## Problem

When a batch stopped early due to a failed action, the remaining actions were correctly marked as skipped in the batch result. However, the model would see the original user request (which still mentioned all actions) and incorrectly assume it should automatically execute the skipped actions in the next step.

Example: A batch of `[duplicate, rename(fails), rename(skipped)]` would result in the skipped rename being executed on the next reasoning step, because the model treated the original user request as still-pending work.

An initial fix injected a conversation message telling the model not to resume skipped actions. This proved insufficient: Gemini ignored the message and the Python orchestrator executed the proposed resume anyway.

## Fix: Hard Python-Side Enforcement

The enforcement now lives in Python orchestration logic, not in prompt wording.

### Architecture

- **`agent/boundary.py`** — Pure, side-effect-free module containing the
  boundary enforcement logic. Extracted from `godot_agent.py` so it can be
  tested without triggering the agent loop. Provides:
  - `compute_action_fingerprint(action)` — extracts the action type and
    its meaningful execution fields as a comparable tuple
  - `is_action_blocked(action, blocked_actions)` — checks a single action
    against the blocked list
  - `check_decision_blocked(decision, blocked_actions)` — checks a full
    decision (single action or batch) against the blocked list

- **`agent/godot_agent.py`** — The agent loop:
  1. Initializes `blocked_skipped_actions = []` per session
  2. After an interrupted batch, records each skipped sub-action's
     fingerprint into `blocked_skipped_actions`
  3. **Before every non-final decision is executed**, calls
     `check_decision_blocked()`. If the proposed action matches a blocked
     skipped action, Python refuses to execute it, logs the rejection, and
     returns a tool-result-shaped dict explaining why
  4. Also appends a conversation boundary message as additional model
     guidance (secondary to the hard enforcement)

### Two-Tier Enforcement

The enforcement uses two complementary checks:

**Tier 1 — Exact Fingerprint Match:**
Compares the action type and all execution fields. Blocks literal
resumption of the skipped action.

| Action | Fingerprint fields |
|--------|-------------------|
| `rename_node` | `node_path`, `new_name` |
| `duplicate_node` | `node_path`, `new_parent_path`, `new_name` |
| `create_node` | `parent_path`, `node_type`, `node_name` |
| `delete_node` | `node_path` |
| `reparent_node` | `node_path`, `new_parent_path` |
| `set_properties` | `node_path`, `properties_json` |

**Tier 2 — Mutation Target Match (bypass prevention):**
Compares the action type and the identity of the resource being mutated.
This blocks parameter-change bypasses where the model changes `new_name`
(or other non-target fields) to evade the exact fingerprint check while
still targeting the same skipped resource.

| Action | Target fields | Rationale |
|--------|--------------|-----------|
| `rename_node` | `node_path` | The node being renamed |
| `duplicate_node` | `node_path` | The source node |
| `create_node` | *(none)* | No pre-existing resource; Tier 1 suffices |
| `delete_node` | `node_path` | The node being deleted |
| `reparent_node` | `node_path` | The node being reparented |
| `set_properties` | `node_path` | The node being modified |

**Discovered bypass:** The initial exact-fingerprint-only enforcement was
evaded when the model changed `new_name` from `"ShouldBeSkipped"` to
`"RenamedPlayer"` — same `node_path`, different `new_name`. The mutation
target tier now blocks this: any `rename_node` on the same `node_path`
is blocked regardless of `new_name`.

Read-only/inspection actions (`find_nodes`, `get_scene_tree`, etc.) are
never blocked by either tier.

### Batch Handling

When the model proposes a new batch after an interrupted batch, every
item in the new batch is checked. If any item matches a blocked skipped
action, the entire batch is rejected before any item executes.

### State Lifetime

`blocked_skipped_actions` is initialized empty at the start of each
user request/session and never persists across sessions.

## Impact

- Skipped batch actions are hard-blocked from automatic resume by Python
- Successful batch actions remain completed (not rolled back)
- Stop-on-first-failure behavior preserved
- Undo/redo behavior preserved
- Recovery actions (find_nodes, get_scene_tree, etc.) remain allowed
- The model must make an explicit decision about how to handle the
  interruption

## Files Modified / Added

- `agent/boundary.py` (new — boundary enforcement logic)
- `agent/godot_agent.py` (imports from boundary.py, adds enforcement
  at the execution dispatch point, records skipped actions)
- `tests/test_batch_boundary.py` (new — 22 focused tests including bypass scenarios)

## Backward Compatibility

- Successful batches are unaffected (blocked list stays empty)
- Single-action execution paths unchanged
- No changes to AgentDecision schema or tool semantics
- No changes to validation behavior
- `boundary.py` is side-effect-free and safe to import independently

---

# Feature: Persistent Multi-Turn Sessions

The agent now runs as a persistent in-memory `AgentSession` (`agent/godot_agent.py`:
`class AgentSession`) that spans multiple user turns.

## Architecture

- Each user request is one turn within a persistent session.
- Session-scoped state is retained across turns:
  - `conversation`: the full model conversation
  - `execution_result_records`: compaction bookkeeping
  - `blocked_skipped_actions`: batch boundary state
- `MAX_STEPS` (currently 12) resets per turn, not per session.
- `final_answer` completes the current turn; the session remains alive and
  prompts for the next user turn.
- `begin_next_turn()` prompts for the next request and handles `/exit`,
  EOF, and empty input.

## Termination Paths

| Path | Trigger | Effect |
|------|---------|--------|
| `final_answer` | Model decision | Current turn ends; session stays alive |
| `exit_session` | Model decision | Entire session closes; no further turns |
| `/exit` | Human CLI input | Host-level escape hatch |

Persistence is **in-memory only**. No disk persistence is implemented.

---

# Feature: Agent-Controlled Session Termination

A new `exit_session` action allows the model to intentionally terminate
the persistent `AgentSession` without human CLI intervention.

## Session and Turn Model

The Python agent runs a persistent `AgentSession` (`agent/godot_agent.py`:
`class AgentSession`). Each user request is one turn within that session.
Session-scoped state (conversation, execution history, batch boundary
state) is retained across turns.

Three distinct termination paths exist:

| Path | Trigger | Effect |
|------|---------|--------|
| `final_answer` | Model decision | Current turn ends. Session stays alive and prompts for next turn. |
| `exit_session` | Model decision | Entire session closes. No further turns are prompted. |
| `/exit` | Human CLI input | Host-level escape hatch. Session closes immediately. |

## Implementation

- `agent/schemas.py`: New `ExitSessionAction` added to the top-level
  `AgentDecision` union. Intentionally excluded from `BatchableAction`.
- `agent/godot_agent.py`: New `ACTION_REQUIREMENTS` entry
  (`"exit_session": ("exit_summary",)`). Decision dispatch handles
  `exit_session` before tool/batch dispatch: prints the summary, logs
  `"Agent session {id} terminated by model decision. Summary: {summary}"`,
  calls `session.terminate()`, and continues the loop.
- System prompt updated to document the action and the turn-vs-session
  distinction.

## Backward Compatibility

- `final_answer` behavior is unchanged.
- `/exit` behavior is unchanged.
- `exit_session` is a new top-level decision; it is not batchable and
  does not pass through batch boundary enforcement.
- All existing tests continue to pass.

---

# Bug Fix: Session Termination Loop

A generator control-flow bug was fixed in `AgentSession.iter_steps()`.

## Problem

When `exit_session` was processed, `session.terminate()` correctly set
`session.closed = True`. However, `iter_steps()` was suspended at its
`yield step`. After resumption, the inner step loop did not immediately
re-check `self.closed`. It only checked `self.turn_completed`, which was
`False` for termination. The inner loop continued and yielded another
step, causing the agent to call the model again despite the session being
closed.

## Fix

`iter_steps()` now checks `self.closed` immediately after the yielded
step resumes:

```python
yield step

if self.closed:
    return

if self.turn_completed:
    break
```

The generator returns immediately when the session has been closed,
raising `StopIteration` on the next advance. No subsequent model call or
user prompt occurs.

## Regression Test

`tests/test_provider_contract.py` includes
`test_iter_steps_terminates_after_close`, which advances the generator
once, calls `session.terminate()` while suspended, and asserts that the
next advance raises `StopIteration`.

---

# Current System Components

## Python Agent

The Python agent currently provides:

* Natural-language user request handling.
* An iterative agent loop.
* Structured model decisions.
* Tool execution.
* Tool result observation.
* Multi-step recovery after failures.
* Final-answer generation.

The primary current agent entry point is:

```text
agent/godot_agent.py
```

The actual repository should always be inspected before assuming surrounding implementation details.

---

## Current Model Provider Situation

### Gemini

Gemini is currently the primary fast cloud model used by the agent.

The current Gemini integration is functional enough to drive iterative scene operations.

A warning currently appears during execution regarding direct use of automatic function calling with `Models.generate_content`.

This warning has been observed during testing and should eventually be addressed as part of provider-layer cleanup.

Do not casually change working provider behavior merely to silence the warning.

First understand the existing provider integration and determine whether the warning affects correctness, reliability, or only recommended SDK usage.

---

### Ollama

Ollama remains available for local inference experimentation.

The architecture should continue to preserve the ability to use local models.

The agent should not become tightly coupled to cloud-only providers.

---

### Groq

A Groq provider adapter is present in the main provider dispatcher and is the
secondary active parity target for the current Gemini-Groq contract phase.

The adapter currently uses JSON-object mode rather than sending the Pydantic
decision schema, translates internal tool results into user messages, and
relies on Groq SDK retries plus rate-limit header pacing. Local Pydantic
validation remains authoritative.

Potentially relevant available Groq models previously identified include:

* `openai/gpt-oss-120b`
* `openai/gpt-oss-20b`
* `qwen/qwen3.6-27b`
* `qwen/qwen3.8-27b`
* `groq/compound`
* `groq/compound-mini`

The exact currently available Groq model list and pricing/free-tier status should not be assumed from this document.

Verify provider availability when implementation work begins.

The provider contract audit is recorded in `PROVIDER_CONTRACT_V1.md`.

OpenRouter and Ollama remain best-effort/last-resort providers and are not
active parity targets in this phase.

---

# Current Godot Editor Capabilities

The currently demonstrated Godot tool capabilities include:

## Scene Inspection

The agent can retrieve the current scene hierarchy using:

```text
get_scene_tree
```

The tool returns structured tree data containing node information such as:

* Node name.
* Node type.
* Node path.
* Root status.
* Children.

The model has successfully converted this information into a human-readable tree representation.

---

## Node Discovery

The agent can search for nodes using:

```text
find_nodes
```

Demonstrated capabilities include:

* Exact name matching.
* Searching the whole scene.
* Returning node paths.
* Returning multiple matching nodes where applicable.
* Using discovered paths in later operations.

A successful example involved resolving:

```text
PersistentEnemy
```

to:

```text
CharacterBody2D/PersistentEnemy
```

before performing a later operation.

---

## Node Creation

The agent can create nodes using:

```text
create_node
```

Successful demonstrated cases include:

* Creating a `Node2D` under another node.
* Creating a `Sprite2D` under another node.
* Creating a node at the root of the current scene.
* Creating a nested node after resolving an initially incomplete parent path.

Demonstrated successful examples include:

```text
CharacterBody2D/TestEnemy
CharacterBody2D/TestSprite
./RootTestNode
CharacterBody2D/PersistentEnemy/NestedTest
```

Creation operations currently report structured success and indicate when the operation is undoable.

---

## Node Renaming

The agent can rename nodes using:

```text
rename_node
```

Successful behavior has been demonstrated for:

* Finding a node by name.
* Obtaining its full path.
* Renaming it.
* Renaming a node directly when the full path is already known.

A demonstrated sequence included:

```text
TestEnemy
    ↓
RenamedTestEnemy
    ↓
FinalTestEnemy
```

Failure behavior was also tested for a nonexistent node.

The agent eventually performed a `find_nodes` operation and correctly reported that the requested node could not be found.

---

## Node Reparenting

The agent can move nodes using:

```text
reparent_node
```

A successful operation moved:

```text
FinalTestEnemy
```

under:

```text
PersistentEnemy
```

The successful operation used resolved full paths.

The resulting demonstrated path was:

```text
CharacterBody2D/PersistentEnemy/FinalTestEnemy
```

The operation reported itself as undoable.

---

# Important Agent Behavior Observed During Testing

## Iterative Recovery Works

The agent has demonstrated the ability to recover from failed operations.

For example:

1. The model attempted node creation without all required parameters.
2. The tool returned a structured error.
3. The model observed the error.
4. The model retried with the missing parameters.
5. The node was successfully created.

This behavior has been observed repeatedly.

The iterative loop is therefore functioning as a real observation-action loop rather than a single-shot request system.

---

## Full Paths Are Important

A recurring issue is that users naturally refer to nodes by short names, while editor operations may require full paths.

For example:

```text
PersistentEnemy
```

was not directly usable as a parent path because its actual path was:

```text
CharacterBody2D/PersistentEnemy
```

The successful recovery pattern was:

```text
User provides node name
        ↓
Operation fails or path is unknown
        ↓
find_nodes
        ↓
Full path discovered
        ↓
Operation retried using full path
```

This pattern is important for future deterministic planning and validation.

---

# Recent Constraint Repair Fix

A significant issue was discovered during reparenting tests.

The user requested:

```text
Move FinalTestEnemy under PersistentEnemy.
```

The model correctly attempted to find:

```text
FinalTestEnemy
```

but the deterministic constraint-repair logic incorrectly interpreted the destination parent:

```text
PersistentEnemy
```

as an automatic `find_nodes.parent_path` search scope.

This produced repeated failures such as:

```text
Parent node not found: PersistentEnemy
```

even when the model explicitly requested a whole-scene search.

The constraint-repair logic was corrected so that a parent mentioned as:

* A destination.
* A reparent target.
* An operation target.

is not automatically injected as the `parent_path` filter for an unrelated `find_nodes` operation.

After the fix, the tested behavior became:

1. Find `FinalTestEnemy` globally.
2. Find `PersistentEnemy` globally.
3. Use both resolved full paths.
4. Perform `reparent_node`.

This succeeded.

The corrected behavior should be preserved.

---

# Current Known Model Behavior Issue

The Gemini model frequently omits required parameters during its first attempt at certain operations.

For example, during node creation, it may initially produce:

```text
action=create_node
parent_path=...
```

without also providing:

```text
node_type
node_name
```

The tool correctly rejects this with a structured validation error.

The model usually recovers on a later step.

This currently works because iterative recovery exists, but it creates unnecessary steps.

Example observed behavior:

```text
Step 1
create_node with missing required arguments
        ↓
Tool validation error
        ↓
Step 2
create_node with complete arguments
        ↓
Success
```

This is inefficient.

Future improvements should investigate deterministic validation and request normalization before tool execution.

However, do not remove model flexibility or introduce broad hard-coded natural-language parsing without first inspecting the current decision architecture.

The goal is to reduce unnecessary retries while preserving generality.

---

# Current Known Provider Warning

During Gemini-driven agent execution, the following warning has repeatedly appeared:

```text
Direct use of automatic function calling (AFC) in Models.generate_content is not recommended. Instead, we recommend to use AFC in Chat.send_message. Similarly, direct use of AFC in Models.generate_content_stream is not recommended. Instead, we recommend to use AFC in Chat.send_message_stream.
```

The agent continues functioning despite this warning.

The warning should be investigated during provider abstraction work.

Do not assume that switching APIs is automatically safe.

First inspect:

* Current Gemini SDK usage.
* Current response structure.
* Current structured decision parsing.
* Any tool/function configuration.
* Compatibility with the existing agent loop.

---

# Current Testing Status

The following broad areas have been successfully demonstrated:

* Scene hierarchy retrieval.
* Human-readable scene hierarchy reporting.
* Global node discovery.
* Node creation under a known full parent path.
* Root-level node creation.
* Nested node creation after path discovery.
* Handling of nonexistent parent nodes.
* Node renaming through path discovery.
* Node renaming through a direct path.
* Handling of nonexistent nodes during rename requests.
* Node reparenting.
* Multi-step iterative recovery.
* Recovery from incomplete model-generated tool arguments.
* Recovery from short node names requiring full path discovery.
* Corrected handling of reparent destinations during node discovery.

Detailed test logs belong in:

```text
docs/TEST_HISTORY.md
```

---

# Immediate Development Priorities

## Priority 1: Inspect and Stabilize Current Agent Architecture

Before adding large new features, inspect the current implementation and identify:

* How decisions are defined.
* Where validation occurs.
* Where constraint repair occurs.
* How tool results are added to agent context.
* How repeated failures are handled.
* How maximum step limits are enforced.
* Whether there are obvious opportunities to prevent redundant retries.

Do not rewrite the agent loop without evidence from the current implementation.

---

## Priority 2: Provider Abstraction

Create or refine a clean provider abstraction so that the core agent loop does not depend directly on Gemini-specific implementation details.

The abstraction should be introduced incrementally.

Initial targets:

```text
Gemini
Groq
Ollama
```

The provider layer should eventually support:

* Consistent request interfaces.
* Consistent response extraction.
* Provider-specific SDK isolation.
* Model selection.
* Provider configuration.
* Future fallback or routing behavior.

Do not implement complex autonomous routing until multiple providers are actually functioning through a stable abstraction.

---

## Priority 3: Groq Integration

After the provider abstraction is sufficiently clear, integrate Groq.

The initial integration should focus on:

* Reliable API configuration.
* A provider implementation.
* A selectable model.
* Compatibility with the current structured decision workflow.
* Basic testing against existing Godot tools.

The first Groq milestone is not sophisticated routing.

The first milestone is:

```text
The existing agent can successfully execute the same structured Godot operations using a Groq provider.
```

---

## Priority 4: Improve Tool Argument Reliability

Investigate ways to reduce repeated model failures caused by missing required parameters.

Potential approaches may include:

* Stronger structured schemas.
* Action-specific validation.
* Deterministic normalization.
* Better tool descriptions.
* Action-specific decision requirements.
* Retry guidance based on exact validation errors.

The implementation must remain general enough for future tool expansion.

Avoid building a collection of brittle special cases for individual English phrases.

---

# Immediate Next Task for an Implementation Agent

Before making significant changes, inspect the current implementation of:

```text
agent/godot_agent.py
```

and any related provider or configuration files currently present in the repository.

The first inspection should determine:

1. The current maximum step configuration.
2. How structured decisions are represented.
3. How Gemini is called.
4. How tool calls are dispatched.
5. Where validation occurs.
6. Where constraint repair occurs.
7. How previous observations are passed back to the model.
8. Whether provider abstraction already partially exists.
9. Which files must change to add Groq cleanly.

Do not begin a large refactor before producing this understanding.

---

# State Update Rules

Update this file when:

* A major tool becomes functional.
* A major tool contract changes.
* A provider is successfully integrated.
* A significant bug is discovered or fixed.
* The immediate development priorities materially change.
* The current architecture changes in a way relevant to implementation.

Do not update this file merely because small formatting or internal refactoring occurred.

Keep it concise enough to remain useful as session context.

The detailed history belongs in `TEST_HISTORY.md`.
