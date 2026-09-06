# Test History

## Purpose

This file records meaningful manual tests, validated behavior, discovered failures, regressions, and debugging observations for the Godot AI Agent.

It is intentionally a concise engineering record rather than a collection of complete terminal transcripts.

Use this file to answer questions such as:

- What has actually been tested?
- Which features are confirmed working?
- Which failures were caused by model behavior?
- Which failures were caused by agent logic?
- Which behaviors required deterministic repair?
- What regressions should future changes avoid?

When a feature is changed, relevant tests should be rerun and this file should be updated.

---

# Test Environment

## Agent Repository

The Python agent package currently lives under the Godot host project at:

`Agent_Host/Python_Agent/`

The primary agent entry point is:

`Python_Agent/agent/godot_agent.py`

The intended module invocation, with the working directory set to `Agent_Host/Python_Agent`, is:

`py -m agent.godot_agent`

## Godot Host Project

The Godot host project is the workspace root:

`Agent_Host/`

The Godot EditorPlugin currently lives under:

`Agent_Host/addons/Execution_Agent/`

The host project and the plugin are now colocated with the Python agent package, so editor mutations are tested directly against the `Agent_Host` Godot project.

---

# Confirmed Working Features

## 1. Scene Tree Inspection

### Test

User requested:

> describe current scene hierarchy in tree format

### Expected Behavior

The agent should:

1. Request the current scene tree.
2. Receive structured hierarchy data from Godot.
3. Interpret the hierarchy.
4. Produce a readable tree-format final answer.

### Result

Passed.

The agent successfully called `get_scene_tree`.

The returned scene data contained nested node dictionaries including:

- `name`
- `node_type`
- `path`
- `is_root`
- `children`

The agent then produced a readable hierarchy.

### Status

Confirmed working.

---

## 2. Node Creation Under a Known Parent Path

### Test

User requested creation of:

> Node2D named TestEnemy under CharacterBody2D

### Result

The model initially omitted required fields:

- `node_name`
- `node_type`

The first tool call failed.

The model observed the structured error:

> create_node requires parent_path, node_type, and node_name.

It then retried with complete parameters.

Creation succeeded.

### Important Observation

Iterative recovery works.

The agent can:

1. Attempt an incomplete action.
2. Observe structured tool failure.
3. Correct missing parameters.
4. Retry successfully.
5. Produce a final answer.

### Status

Confirmed working, but provider output quality still needs improvement because the first attempt was unnecessarily incomplete.

---

## 3. Sprite2D Creation

### Test

User requested creation of:

> Sprite2D named TestSprite under CharacterBody2D

### Result

The model initially omitted:

- `node_name`
- `node_type`

The first attempt failed.

A subsequent iteration supplied complete parameters.

Creation succeeded.

### Status

Confirmed working.

### Regression Risk

The agent architecture should continue to tolerate incomplete structured model decisions.

However, repeated predictable parameter omissions should eventually be reduced through:

- stronger decision validation,
- better prompts,
- provider abstraction,
- deterministic request extraction where appropriate.

---

## 4. Root-Level Node Creation

### Test

User requested:

> Create a Node2D node named RootTestNode at the root of the current scene.

### Result

The agent correctly used:

`parent_path = "."`

The node was created successfully.

### Status

Confirmed working.

### Important Semantic Convention

The current scene root is represented by:

`.`

Future tools and path normalization logic must preserve this convention consistently.

---

## 5. Nested Parent Discovery and Node Creation

### Initial Failure

User requested:

> Create a Node2D node named NestedTest under PersistentEnemy.

The model initially attempted:

`parent_path = "PersistentEnemy"`

Godot returned:

> Parent node not found: PersistentEnemy

This occurred because the actual path was:

`CharacterBody2D/PersistentEnemy`

### Recovery Test

The agent then searched for `PersistentEnemy` using `find_nodes`.

The search returned:

`CharacterBody2D/PersistentEnemy`

The agent then created:

`CharacterBody2D/PersistentEnemy/NestedTest`

successfully.

### Status

Confirmed working.

### Important Observation

Short node names are not necessarily valid node paths.

When an operation requires a path and only a name is known, the agent may need to:

1. Search for the node.
2. Inspect the returned path.
3. Use the exact path for the mutation.

---

## 6. Node Discovery

### Test

The agent searched for nodes such as:

- `TestEnemy`
- `PersistentEnemy`
- `FinalTestEnemy`

using `find_nodes`.

### Result

Exact searches successfully returned structured node data containing:

- node name,
- node type,
- node path,
- root status.

A representative result contained:

- `name`: `PersistentEnemy`
- `node_type`: `Node2D`
- `path`: `CharacterBody2D/PersistentEnemy`
- `is_root`: `false`

### Status

Confirmed working.

---

## 7. Rename Node Using Discovery

### Test

User requested:

> Rename TestEnemy to RenamedTestEnemy.

### Agent Behavior

The agent first searched for `TestEnemy`.

The search returned:

`CharacterBody2D/TestEnemy`

The agent then called `rename_node` with the exact path.

### Result

Passed.

### Status

Confirmed working.

---

## 8. Rename Node Using Explicit Path

### Test

User requested:

> Rename CharacterBody2D/RenamedTestEnemy to FinalTestEnemy.

### Result

The model directly called `rename_node` with:

- `node_path = CharacterBody2D/RenamedTestEnemy`
- `new_name = FinalTestEnemy`

The operation succeeded.

### Status

Confirmed working.

### Important Observation

When the user already provides an exact path, unnecessary discovery should generally be avoided.

---

## 9. Rename Nonexistent Node

### Test

User requested:

> Rename DoesNotExist to Whatever.

### Initial Failure

The model initially selected `rename_node` without supplying the required:

- `node_path`
- `new_name`

The tool correctly rejected the action.

### Recovery

The model then used `find_nodes` to search for `DoesNotExist`.

The result count was zero.

The agent produced a failure explanation instead of pretending the rename succeeded.

### Status

Confirmed working.

### Important Observation

Structured tool failures are valuable observations.

The agent should continue using failures to guide subsequent decisions rather than terminating immediately.

---

## 10. Create Node Under Nonexistent Parent

### Test

User requested:

> Create a Node2D named OrphanTest under DoesNotExist.

### Behavior

The model initially produced incomplete `create_node` decisions.

After multiple attempts, it eventually supplied:

- `node_name = OrphanTest`
- `node_type = Node2D`
- `parent_path = DoesNotExist`

Godot returned:

> Parent node not found: DoesNotExist

The agent then produced an appropriate final failure response.

### Status

Confirmed working from a safety perspective.

### Weakness Identified

The model wasted multiple steps repeating incomplete `create_node` calls before supplying the required fields.

Future architecture should reduce this through deterministic validation before tool execution.

---

## 11. Reparent Node

### Original Problem

User requested:

> Move FinalTestEnemy under PersistentEnemy.

The earlier constraint-repair logic incorrectly interpreted the destination parent `PersistentEnemy` as a search scope for unrelated `find_nodes` calls.

This caused repeated failures because the agent attempted searches constrained by:

`parent_path = PersistentEnemy`

before first resolving the actual path of that node.

The agent eventually recovered only after requesting the complete scene tree.

This behavior was identified as a significant logic bug.

---

### Fix

Constraint repair logic was changed so that a parent mentioned as the destination of an operation is not automatically injected as `find_nodes.parent_path` when the agent is searching for another node.

The repair system must distinguish between:

- an actual search scope,
- a node being searched for,
- an operation destination,
- an operation source.

---

### Retest

User again requested:

> Move FinalTestEnemy under PersistentEnemy.

The agent performed:

1. Whole-scene search for `FinalTestEnemy`.
2. Whole-scene search for `PersistentEnemy`.
3. Reparent operation using the exact paths.
4. Final confirmation.

### Result

Passed.

Example discovered paths included:

`CharacterBody2D/PersistentEnemy/FinalTestEnemy`

and:

`CharacterBody2D/PersistentEnemy`

The reparent operation completed successfully.

### Status

Confirmed working.

### Important Regression

Do not reintroduce automatic parent scope injection for `find_nodes` merely because the user's request contains a phrase such as:

> under ParentNode

The semantic meaning depends on the operation.

For example:

> Move A under B

means:

1. Find source node `A`.
2. Find destination node `B`.
3. Reparent `A` to `B`.

It does not mean:

> Search for A inside B

before the path of B is known.

---

## 12. Iterative Agent Reasoning

### Observation

Multiple tests have demonstrated that the agent can perform multi-step workflows involving:

- initial model decision,
- tool execution,
- observation,
- failure analysis,
- node discovery,
- retry,
- mutation,
- final response.

Examples include:

- nested node creation,
- node renaming through discovery,
- reparenting through source and destination discovery.

### Status

Confirmed working.

### Architectural Importance

The agent should remain iterative.

Do not redesign the system into a single-shot architecture such as:

`prompt -> one tool call -> final answer`

The intended architecture is an observation-driven loop.

---

## 13. Structured Decision Parsing

### Observation

The cloud model sometimes returns incomplete JSON decisions.

Examples include a valid action but missing required fields.

The Pydantic decision model successfully parses partial decisions where optional fields are absent.

Tool-level validation then provides structured failure feedback.

### Status

Working, but incomplete decisions remain a known provider behavior.

### Future Improvement Direction

The agent should increasingly distinguish between:

1. Syntactically valid model output.
2. Semantically complete action decisions.

A decision can be valid JSON and still be incomplete for a selected action.

Future deterministic validation should catch obvious missing action parameters before unnecessary bridge calls where practical.

---

## 14. Constraint Repair

### Confirmed Useful Behavior

Constraint repair can correct certain model omissions using explicit user constraints.

### Confirmed Dangerous Behavior

Constraint repair must not blindly inject user-provided node names into unrelated fields.

The reparent regression demonstrated that overly aggressive repair can actively damage correct model reasoning.

### Current Principle

Constraint repair must be:

- operation-aware,
- conservative,
- deterministic,
- explainable in logs.

If the semantic meaning of a user constraint is ambiguous, it should not be blindly copied into an action field.

---

# Current Confirmed Tool Coverage

The following operations have been manually exercised.

## Read Operations

- `get_scene_tree`
- `find_nodes`

## Mutation Operations

- `create_node`
- `rename_node`
- `reparent_node`

## Agent Control

- `final_answer`

All currently tested mutation operations reported `undoable = true` or otherwise confirmed undoable editor-native behavior.

---

# Known Issues

## 1. Gemini Automatic Function Calling Warning

Every tested run currently prints a warning similar to:

> Direct use of automatic function calling (AFC) in Models.generate_content is not recommended. Instead, use AFC through Chat.send_message.

The current agent architecture still functions despite this warning.

### Status

Known issue.

### Priority

Medium.

### Future Direction

When provider abstraction is implemented, evaluate whether the Gemini integration should:

- migrate to chat-based interaction,
- disable unused automatic function calling behavior,
- or otherwise restructure provider calls.

This should be done carefully because provider integration changes can affect the currently working iterative agent loop.

---

## 2. Incomplete Initial Tool Decisions

The cloud model frequently emits an action such as `create_node` without all required parameters.

This leads to avoidable failed steps.

### Status

Known behavior.

### Priority

High for efficiency, lower for correctness because recovery currently works.

### Future Direction

Introduce action-aware validation before dispatching tools where it improves reliability without hiding useful model reasoning.

---

## 3. No Mature Provider Abstraction Yet

The current architecture has been primarily tested with Gemini as the fast cloud reasoning provider.

Ollama remains relevant for local inference.

Groq API access is planned for additional cloud providers.

### Status

Not yet implemented as a mature abstraction layer.

### Priority

High.

---

## 4. Interrupted Batch Did Not Preserve Execution Boundary (HARD FIXED)

When a batch stopped early due to a failed action, the remaining actions were
correctly marked as skipped in the batch result JSON. However, no orchestration-level
boundary was communicated to the model. On the next reasoning step, the model would see
the original user request (which still mentioned all actions) and incorrectly assume it
should automatically execute the skipped actions.

### Example

Request: "Duplicate Player to PlayerBatchFailureCopy, rename DefinitelyDoesNotExist to
ShouldNotWork, rename PlayerBatchFailureCopy to ShouldBeSkipped."

1. duplicate_node succeeded
2. rename_node on DefinitelyDoesNotExist failed
3. rename_node on PlayerBatchFailureCopy was skipped

But the next reasoning step would execute the skipped rename because the original request
still mentioned it.

### First Fix Attempt (Insufficient)

A `user`-role boundary message was appended to the conversation instructing the model
NOT to resume skipped actions. This proved insufficient: Gemini ignored the message
and the Python orchestrator executed the proposed resume anyway.

### Final Fix: Hard Python-Side Enforcement

Moved enforcement from prompt wording to Python orchestration logic:

- `agent/boundary.py` — pure module with `compute_action_fingerprint`,
  `extract_mutation_target`, `is_action_blocked`, `check_decision_blocked`
- `agent/godot_agent.py` — before every non-final decision executes,
  `check_decision_blocked()` is called. If the proposed action matches a blocked
  skipped action, Python refuses to execute it, logs the rejection, and returns a
  tool-result-shaped dict explaining why
- Skipped sub-actions are recorded with both their exact fingerprint AND their
  mutation target at batch interruption time
- New batches are also checked item-by-item; any blocked item rejects the whole batch

### Discovered Bypass (Parameter-Change Evasion)

The initial exact-fingerprint enforcement was evaded when the model changed
`new_name` from `"ShouldBeSkipped"` to `"RenamedPlayer"` — same `node_path`,
different `new_name`. The fingerprint no longer matched, so Python executed it.

**Fix:** Added `extract_mutation_target()` and a second enforcement tier that
blocks any mutation targeting the same resource, regardless of non-target
parameter changes. For `rename_node`, the protected target is `node_path` only;
`new_name` is the desired resulting state and must not bypass protection.

### Tests

`tests/test_batch_boundary.py` — 25 uniquely named focused tests covering:
- Direct resume is blocked (rename, duplicate, create, delete, reparent, set_properties)
- **Parameter-change bypass is blocked** (same target, different new_name/properties/parent)
- Different target nodes are NOT blocked
- `find_nodes` and other inspection actions are never blocked
- Batches containing blocked items are rejected before any item executes
- Batches without blocked items are allowed
- Recovery actions remain allowed after a failure
- The demonstrated bypass scenario is explicitly blocked

### Status

Fixed (hard enforcement with bypass prevention).

### Priority

High (correctness).

## Session Persistence Tests

On 2026-09-05, focused tests were added to validate the persistent
`AgentSession` lifecycle. The full suite reached 56 tests at this
milestone (55 previously plus the generator termination regression
test); it has since grown to 64 with provider-contract and
Observability v1 telemetry tests.

### Tests Added

| Test | Purpose |
|------|---------|
| `test_agent_session_keeps_state_across_user_turns` | Verifies conversation, execution history, and blocked-action state persist across user turns |
| `test_agent_session_termination_preserves_state` | Verifies termination preserves accumulated session state |
| `test_terminated_session_does_not_begin_another_turn` | Verifies `iter_steps()` raises `StopIteration` after close |
| `test_exit_command_terminates_without_prompting_again` | Verifies `/exit` terminates without prompting |
| `test_context_compaction_uses_existing_implementation` | Verifies compaction summarizes older results while preserving recent ones |

### Status

Confirmed working (full suite now 64 tests passing).

---

## Session Termination Feature Tests

### Exit Session Schema and Behavior

| Test | Purpose |
|------|---------|
| `test_exit_session_action_validates` | `ExitSessionAction` validates successfully |
| `test_exit_session_requires_exit_summary` | `exit_summary` is required |
| `test_exit_session_is_valid_agent_decision` | Accepted as valid `AgentDecision` |
| `test_exit_session_closes_session` | Closes an active `AgentSession` |
| `test_exit_session_does_not_begin_another_turn` | Does not prompt for another turn |
| `test_final_answer_leaves_session_open` | `final_answer` completes only the current turn |
| `test_exit_command_still_terminates` | `/exit` still terminates the session |
| `test_exit_session_preserves_session_state` | Termination preserves accumulated state |
| `test_exit_session_excluded_from_batch` | `exit_session` cannot appear inside a batch |

### Status

Confirmed working.

---

## Generator Termination Regression

### Bug

After `exit_session` was processed and `session.terminate()` set
`session.closed = True`, the `iter_steps()` generator did not immediately
stop. It yielded another step because the inner loop only checked
`self.turn_completed`, not `self.closed`.

### Fix

`iter_steps()` now checks `self.closed` after each `yield` and returns
immediately when the session is closed.

### Regression Test

`test_iter_steps_terminates_after_close` advances the generator once,
calls `session.terminate()` while suspended at the yield, and asserts
`StopIteration` on the next advance. This prevents unnecessary model/API
calls after session termination.

### Status

Confirmed working. Full suite: 64 tests passing.

---

## Known Issue: Empty Input

Empty input at the `begin_next_turn()` prompt currently terminates the
session silently (no log message). This is inconsistent with `/exit`, which
logs `"Agent session terminated by user."`. This is a known documentation
gap and potential behavior issue. **Not fixed in this milestone.**

---

## Provider Contract Audit

On 2026-09-05, the current Gemini and Groq adapters were traced through the
agent loop. The result is documented in `PROVIDER_CONTRACT_V1.md`. No provider
behavior was changed. The duplicate batch-boundary test name was renamed so
pytest can collect all 25 defined tests; the focused command still requires a
pytest installation in the active Python environment.

### Regression Risk

- Successful batches must remain unaffected (blocked list stays empty).
- The model must still be able to choose an explicit recovery action (inspect, retry,
  ask user, or finalize) - the boundary blocks automatic resumption, not explicit recovery.
- Mutations targeting different nodes must never be falsely blocked.
- Read-only actions must never be blocked.

---

## Observability v1 Telemetry Tests

Observability v1 telemetry (`agent/telemetry.py`) was added and wired
into the agent loop and all four provider adapters. No tool semantics,
`AgentDecision` schemas, or batch-boundary behavior were changed. The
adapters now return a `ProviderResult(text, usage)` envelope;
`ask_model()` still returns the model text as a string.

### Tests Added / Updated

| Test | Purpose |
|------|---------|
| `test_model_usage_available_is_recorded` | Provider usage metadata is normalized (`TokenUsage`) and recorded on the model-call telemetry entry |
| `test_model_usage_unavailable_is_not_fabricated` | When no usage metadata exists, usage stays unavailable and is not invented |
| `test_model_failure_records_duration_and_error` | A failed model call records duration and a safe (secret-redacted) error message |
| `test_batch_telemetry_preserves_batch_boundary` | Batch telemetry records stopped-early state without weakening boundary enforcement |
| `test_session_summary_aggregates_known_and_unknown_usage` | Session summary sums known token counts, flags incomplete totals (`total_tokens_complete`, `usage_unavailable_count`), and counts actions/batches/compactions |

Adapter tests were updated to assert the `ProviderResult` envelope:
`tests/test_gemini_provider.py` (including
`test_ask_gemini_normalizes_usage_metadata`) and
`tests/test_provider_adapters.py`.

### Status

Confirmed working. Full suite: 64 passed (25 batch-boundary,
31 provider-contract, 6 provider-adapter, 2 Gemini provider).

Only mocked provider responses were used; no live provider usage
metadata was validated in this milestone.

### Regression Risk

- Telemetry recording must stay side-effect-free: a telemetry failure
  must not change tool execution or boundary decisions.
- Missing usage metadata must never be replaced with estimated values.
- `safe_error_message()` must keep truncating and redacting API keys.

---

# Testing Principles Going Forward

Every new Godot operation should be tested in at least the following categories where applicable.

## Happy Path

The operation succeeds using a straightforward request.

## Discovery Path

The operation succeeds when the agent must first discover a node's full path.

## Explicit Path Path

The operation succeeds when the user provides the exact path.

## Missing Target

The requested node does not exist.

## Missing Parent

The requested parent does not exist.

## Ambiguous Target

More than one node may match the requested name.

## Nested Hierarchy

The operation works at multiple hierarchy depths.

## Recovery

The model or tool initially fails, then the agent correctly observes and recovers.

## Undoability

The resulting editor operation remains undoable where Godot supports it.

---

# Test Record Format

Future entries should generally use this structure:

## Feature Name

### Test

Short user request or scenario.

### Expected Behavior

What the agent should do.

### Result

Passed, failed, or partially passed.

### Observations

Important technical behavior.

### Regression Risk

Behavior future changes must preserve.

### Status

Confirmed working, known issue, or needs retest.

Avoid storing unnecessarily large raw terminal transcripts unless exact output is required to diagnose a specific bug.

---

# Maintenance Rule

Update this file after:

- implementing a new tool,
- discovering a reproducible bug,
- fixing a regression,
- completing a significant manual test,
- changing tool semantics,
- changing constraint-repair behavior,
- changing provider behavior that affects agent decisions.

Do not update this file merely because source code changed.

The purpose of this file is to record observed behavior, not act as a source-code changelog.