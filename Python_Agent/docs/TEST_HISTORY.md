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

## Gemini 400 Regression After Tool Expansion

### Failure

After the advanced inspection tools were added, Gemini 3.1 Flash Lite
returned `400 INVALID_ARGUMENT` before the first agent action. Progressive
live schema isolation showed that removing `CountNodesAction` from the
schema restored success; removing the other new actions did not.

### Cause and Fix

The failure was specific to the nested `batch.actions` union. Once the
Gemini adapter removed Pydantic's `oneOf` discriminator metadata,
`CountNodesAction` and `FindNodesAction` presented overlapping filter
branches. The Gemini adapter now removes only the `count_nodes` branch from
that provider-only nested union. `count_nodes` remains a valid standalone
and Python-batch action, and no Godot tool semantics changed.

### Verification

- Full Python suite: 182 passed.
- Gemini provider adapter tests: 7 passed.
- Live `display project settings`: recovered after two structured tool
  failures and returned the expected 36 `application` settings.
- Live `what tools do you have?`: completed with HTTP 200 and a final answer.
- Editor diagnostics and `git diff --check`: passed.

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

## 15. get_node_property Action

### Test

Automated suite added to `tests/test_provider_contract.py` and
`tests/test_registry.py`, plus a Godot headless harness exercising
`AIAgentPropertyTools.get_node_property_from_request`.

Coverage:

- Valid decision parses and passes `validate_agent_action`.
- Blank/whitespace-only `node_path` and `property_name` are rejected
  client-side (`"requires non-empty field(s): <field>"`).
- The action is dispatchable from the registry and is read-only /
  batchable (no boundary blocking).
- Bridge success returns the resolved node name, node type, property
  type, `editable` flag, and serialized value.
- Bridge failure (node not found, property not found) is returned
  unchanged (no exception wrapping, no partial execution).

### Result

- Python: 103 passed (8 new tests).
- Godot 4.7.2 headless: 8/8 harness cases passed.

### Status

Confirmed working.

---

# Current Confirmed Tool Coverage

The following operations have been manually exercised.

## Read Operations

- `get_scene_tree`
- `find_nodes`
- `get_node_properties`
- `get_node_property`
- `validate_node_type`
- `describe_current_scene`

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

## Premature `exit_session` Guard

### Bug

Live stress test: user requested `delete omnitrix and end session`;
Gemini returned only `exit_session` with
`"Deleted 'Omnitrix' node and terminating the session as requested."`
— no `delete_node` executed, but the session terminated anyway,
treating the `exit_summary` text as evidence of performed work.

### Fix

Deterministic Python-side guard: `exit_session` is honored only after
at least one tool action has executed in the current turn
(`exit_session_is_allowed()` in `agent/godot_agent.py`). Otherwise the
session is not terminated; the decision is rejected with a
tool-result-shaped observation
(`build_premature_exit_session_result()`) and the model must perform
the requested work first. `/exit` is unchanged.

### Tests

| Test | Purpose |
|------|---------|
| `test_exit_session_cannot_substitute_for_unexecuted_mutation` | Bare `exit_session` claiming a deletion is rejected, never dispatches `delete_node`, session stays open |
| `test_valid_delete_node_then_exit_session_still_works` | Real `delete_node` followed by `exit_session` still terminates normally |
| `test_prompt_requires_work_before_exit_session` | System prompt requires requested work before `exit_session` and forbids claiming unexecuted actions |

### Status

Confirmed working. Full suite: 95 passed.

### Limitation

The guard proves "at least one tool action executed this turn", not
"all requested work is complete". Detecting full request completion
would require a natural-language intent parser, intentionally out of
scope; the prompt additionally instructs the model to execute all
requested actions before `exit_session`.

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

## Tool Expansion V2: validate_node_type

Added the first V2 tool: read-only `validate_node_type`, validated
end-to-end through the action registry.

### Tests

- Python suite: 90 passed (5 new: registry dispatch reaches
  `tools/scene_tools.validate_node_type`, read-only boundary
  non-interference with a live blocked-rename entry, decision
  validation, blank `node_type` rejection, batchable membership).
- Godot headless (4.7.2): 8/8 cases passed against the real
  `ClassDB` (valid type, abstract base `CanvasItem`, non-Node
  `Resource`, unknown class, whitespace-only, missing key,
  `Node` itself, whitespace trimming).

### Status

Confirmed working. Python-side verification used a mocked bridge;
Godot-side verification used the real ClassDB headlessly. No live
end-to-end run against a running editor bridge was performed.

### Regression Risk

- `validate_node_type` must remain read-only: it must never be
  added to `boundary._MUTATION_TARGET_KEYS` and must never modify
  scene state.
- The `valid` answer must come from `ClassDB` only, never from a
  hardcoded type list.

---

## Advanced Tool: list_available_node_types

### Implementation

Added bounded ClassDB discovery for native, instantiable `Node` classes.
The action accepts optional `inherits_from`, case-insensitive
`name_contains`, and `limit` filters. Results are sorted class names
only, with `total_matches` and `truncated`; unfiltered requests default
to 50 names and never exceed 100. Invalid supplied filters return
structured failures, while no matches return a successful empty list.

The tool is read-only and batchable through the existing action registry.
It does not alter scene state, undo/redo behavior, telemetry, or
interrupted-batch mutation protection. `validate_node_type` remains the
exact confirmation step for a candidate returned by this discovery tool.

### Tests

- Python contract and registry tests cover optional-filter validation,
  maximum limit validation, batch membership, read-only boundary status,
  dispatch arguments, combined-filter result passthrough, no-match, and
  invalid-filter structured failure.
- Godot 4.7.2 headless harness calls the real handler and ClassDB:
  `Node2D` descendants include `Node2D` and `CharacterBody2D`;
  case-insensitive `CharacterBody2D` filtering succeeds; combined
  `Node2D` + `body` filtering succeeds; a nonexistent name returns zero
  matches; invalid base, invalid limit, and blank filter return failures.
  It also validates returned `CharacterBody2D` through the unchanged
  `validate_node_type` handler.

### Result

Godot's existing running bridge had not reloaded its router script and
therefore returned `Unknown endpoint` for the new route, so it was not
restarted. The isolated real Godot 4.7.2 headless harness passed against
the updated handler and actual ClassDB instead. The full Python suite
passed: 114 tests.

### Limitation

The tool intentionally lists native ClassDB candidates only; it does not
list project script classes or expose arbitrary class metadata.

---

## get_node_property: Node.name Regression

### Reproduction and root cause

The live editor bridge reproduced the request `Get the name property of
Player. Do not modify anything.`: `Player.position` succeeded, but
`Player.name` returned `Property not found: name on node Player.` The
same live inspection confirmed that `name` is absent from
`get_node_properties`.

The action schema, registry dispatch, Python wrapper, HTTP route, and
serializer were not the failing layer. Godot exposes `Node.name` as a
scene-tree-visible special attribute but does not include
`PROPERTY_USAGE_EDITOR` in its property-list metadata. The existing
single-property lookup accepted only property-list entries with that
flag, so it rejected `name` before reading or serializing it.

### Fix

`get_node_property` now has one explicit read-only exception for
`Node.name`. It returns the actual `target_node.name` as `StringName`
with `editable: false`; changes remain exclusive to the dedicated,
undoable `rename_node` action. Property-list filtering and
`get_node_properties` behavior are otherwise unchanged.

### Regression coverage

- Python registry/dispatch tests cover both `position` and `name`.
- Python contract tests cover successful `position` and `name` reads,
  plus unchanged structured failures for a missing node and unsupported
  property.
- Existing `validate_node_type` validation and dispatch coverage remains
  part of the full suite.

### Result

- Focused Python tests: 73 passed.
- Full Python suite: 106 passed.
- Live Godot 4.7.2 editor bridge: `Player.name` returned `"Player"` as
  a read-only `StringName`; `Player.position` still returned `Vector2`;
  missing-node and unsupported-property requests returned their existing
  structured failures. `validate_node_type(Node2D)` remained valid.

### Remaining limitation

`get_node_properties` intentionally continues to omit `name`, so a full
property-list read is not a substitute for an explicit `name` read.

---

## Feature: `list_node_signals`

### Test

Automated suite added to `tests/test_provider_contract.py` and
`tests/test_registry.py`, plus a permanent Godot 4.7.2 headless harness
(`addons/Execution_Agent/tests/list_node_signals_harness.gd`) exercising
`AIAgentNodeTools.list_node_signals_from_request` against real
`Node.get_signal_list()` reflection data.

Coverage:

- Valid decision parses, validates, and dispatches to
  `tools/scene_tools.list_node_signals` with the exact `node_path`.
- Blank `node_path` is rejected by required-field validation.
- Bridge success and missing-node structured failures pass through
  unchanged; batchable membership; read-only boundary status (never in
  `_MUTATION_TARGET_KEYS` / `_BATCH_ACTION_EQUIVALENCE_KEYS`).
- Headless harness, real nodes (`Root` → `Player` (Area2D) → `Plain`
  (Node)): an Area2D returns its actual signals including
  `area_entered` with a real `Object` argument; Node built-ins
  (`tree_entered`, `renamed`) confirm inherited signals are preserved;
  a plain Node with only built-in signals succeeds; a nonexistent node
  returns `Node not found: ...`; blank and missing `node_path` return
  structured errors; two calls are identical and names are sorted;
  the result serializes to JSON.
- Custom-signal regression: a real scripted fixture node
  (`list_node_signals_custom_signal_fixture.gd`, declaring
  `signal health_changed(new_health: int)`) is added to the harness
  tree; the harness proves `health_changed` is discovered through the
  same real `Node.get_signal_list()` path with correct argument
  metadata, alongside inherited built-ins, and remains JSON-serializable.

### Result

- Focused Python tests: 97 passed.
- Full Python suite: 138 passed.
- Godot 4.7.2 headless harness: all cases passed.

### Status

Confirmed working. No live end-to-end run against a running editor
bridge was performed; the running editor instance was deliberately not
restarted. The route must exist in the editor's loaded router, so a
live test requires an editor reload of the plugin first.

---

## Feature: `list_node_groups`

### Test

Automated suite added to `tests/test_provider_contract.py` and
`tests/test_registry.py`, plus a permanent Godot 4.7.2 headless harness
(`addons/Execution_Agent/tests/list_node_groups_harness.gd`) exercising
`AIAgentNodeTools.list_node_groups_from_request` against real node
group state.

Coverage:

- Valid decision parses, validates, and dispatches to
  `tools/scene_tools.list_node_groups` with the exact `node_path`.
- Blank `node_path` is rejected by required-field validation.
- Bridge success and missing-node structured failures pass through
  unchanged; batchable membership; read-only boundary status (never in
  `_MUTATION_TARGET_KEYS` / `_BATCH_ACTION_EQUIVALENCE_KEYS`).
- Headless harness, real nodes with real `add_to_group()` assignments
  (assigned deliberately in non-alphabetical order): a node with no
  groups returns a successful empty result; a node with one group
  returns exactly that group; a node with three groups returns exactly
  `["characters", "enemies", "hostile"]` sorted regardless of
  assignment order; `is_in_group()` on the real nodes agrees with the
  reported membership; two `Area2D` nodes with different groups prove
  membership is instance state, not class metadata; a nonexistent node
  returns `Node not found: ...`; blank and missing `node_path` return
  structured errors; repeated calls are byte-equivalent; the result
  serializes to JSON.

### Result

- Focused Python tests: 105 passed.
- Full Python suite: 146 passed.
- Godot 4.7.2 headless harness: all cases passed.
- The frozen `list_node_signals` harness was re-run and still passes.

### Status

Confirmed working. No live end-to-end run against a running editor
bridge was performed; the running editor instance was deliberately not
restarted. The route must exist in the editor's loaded router, so a
live test requires an editor reload of the plugin first (same
stale-router limitation documented for `list_available_node_types` and
`list_node_signals`).

---

## Feature: `count_nodes`

### Test

Automated suite added to `tests/test_provider_contract.py` and
`tests/test_registry.py`, plus a permanent Godot 4.7.2 headless harness
(`addons/Execution_Agent/tests/count_nodes_harness.gd`) exercising
`AIAgentNodeTools.count_nodes_from_request` against a real,
deterministic node hierarchy.

Coverage:

- Schema accepts a minimal request, the full shared filter shape, and
  rejects unsupported `name_match` values (Pydantic Literal).
- Registry membership, non-mutation classification, dispatch with
  shared filters, bridge success/missing-parent failure passthrough,
  and batchable membership.
- Headless harness over a fixed hierarchy (`Level` with
  `SpawnPoint`/`SpawnPoint2`/`TriggerArea`, `Enemies` with
  `EnemyA`/`EnemyB`/`EnemyC`): no-filter count cross-checked against an
  independent manual traversal of the same tree; exact, contains,
  starts-with, and ends-with name filters; type filter; parent-path
  subtree counting (including the parent itself, matching `find_nodes`
  semantics); combined filters; zero matches as `count: 0`;
  nonexistent parent returning the existing
  `Parent node not found: ...` failure; `"."` root handling; multiple
  same-type nodes; invalid `name_match` mode sharing the `find_nodes`
  error; byte-equivalent repeat calls; JSON serializability; and the
  guarantee that no node list is returned.

### Result

- Focused Python tests: 113 passed.
- Full Python suite: 156 passed.
- Godot 4.7.2 headless harness: all cases passed.
- All pre-existing harnesses (`get_node_class_info`,
  `list_available_node_types`, `list_node_signals`, `list_node_groups`)
  re-run after the shared-filter refactor: all pass, confirming
  `find_nodes` behavior is unchanged.

### Status

Confirmed working. No live end-to-end run against a running editor
bridge was performed; the running editor instance was deliberately not
restarted (known stale-router limitation, same as previous tools).

---

## Feature: `find_nodes_by_script`

### Test

Automated suite added to `tests/test_provider_contract.py` and
`tests/test_registry.py`, plus a permanent Godot 4.7.2 headless harness
(`addons/Execution_Agent/tests/find_nodes_by_script_harness.gd`)
exercising `AIAgentNodeTools.find_nodes_by_script_from_request`
against real scripted nodes.

Coverage:

- Schema accepts a valid request; blank `script_path` is rejected by
  required-field validation; registry membership, read-only
  classification, dispatch, success/zero-match passthrough, and
  batchable membership.
- Headless harness with real `set_script()` attachments
  (`PlayerA` Area2D + `PlayerB` Node2D sharing one fixture script,
  `Enemy` Node with a second fixture script, `Plain` Node with no
  script): the shared script returns exactly its two nodes with real
  paths/names/types; the other script returns only its own node;
  unscripted nodes never appear; a nonexistent script returns
  `count: 0` (success, not error); prefix-less requests normalize to
  the same canonical path and identical result; blank and missing
  `script_path` return structured errors; repeated calls are
  byte-equivalent; JSON serialization succeeds. Expected matches were
  cross-checked by calling `get_script()` directly on the harness
  nodes.

### Result

- Focused Python tests: 121 passed.
- Full Python suite: 164 passed.
- Godot 4.7.2 headless harness: all cases passed.
- All pre-existing harnesses (`count_nodes`, `list_node_groups`,
  `list_node_signals`, `list_available_node_types`,
  `get_node_class_info`) re-run after the `collect_matching_nodes`
  extension: all pass, confirming `find_nodes` traversal behavior is
  unchanged.

### Status

Confirmed working. No live end-to-end run against a running editor
bridge was performed for this tool.


## Feature: `get_project_settings`

### Test

Automated suite added to `tests/test_provider_contract.py` and
`tests/test_registry.py`, plus a permanent Godot 4.7.2 headless harness
(`addons/Execution_Agent/tests/get_project_settings_harness.gd`)
exercising `AIAgentNodeTools.get_project_settings_from_request` against
the live `ProjectSettings` runtime state.

Coverage:

- Schema accepts a valid request; registry membership, read-only
  classification, dispatch, success/zero-match passthrough, and
  batchable membership. A request with neither `setting_names` nor
  `prefix` is rejected at runtime.
- Headless harness covering exact single/multiple setting lookups,
  missing-key reporting (`missing`, not failure), multi-setting names,
  prefix enumeration with deterministic lexicographic ordering,
  prefix-bound/`truncated` metadata, sensitive-token redaction (name in
  `redacted`, value never exposed), and JSON serialization. Results were
  cross-checked against direct `ProjectSettings.get_setting()` calls.

### Result

- Focused Python tests: 140 passed.
- Full Python suite: 181 passed.
- Godot 4.7.2 headless harness: all cases passed.
- Pre-existing `count_nodes` harness re-run after the shared
  `ai_agent_node_tools.gd` edits: passes, confirming no regression in the
  shared file.

### Status

Confirmed working. No live end-to-end run against a running editor bridge
was performed for this tool (the running editor predates the
`/get_project_settings` route).

---


---

## Inspection Tools Milestone Completion

### Final additions

The inspection surface now contains all 17 planned read-only tools. The
final additions are:

- `list_autoloads`: deterministic autoload names and resource targets from
  live `ProjectSettings`, without parsing `project.godot`.
- `get_editor_state`: edited-scene identity, open scenes, selected nodes,
  and playing-scene state from the injected `EditorInterface`.
- `list_scenes_in_project`: sorted `PackedScene` paths from the injected
  editor resource filesystem; it reports an explicit not-ready failure while
  the editor filesystem is scanning or importing.
- `get_undo_history_summary`: read-only undo/redo availability and action
  labels for global and edited-scene histories from the injected
  `EditorUndoRedoManager`.

### Validation

- Focused Python contract and registry tests: 152 passed.
- Full Python suite: 194 passed.
- Godot 4.7.2 headless `list_autoloads` harness: passed with real in-memory
  `ProjectSettings` autoload entries and JSON serialization.
- Godot 4.7.2 headless editor-state, scene-list, and undo-summary harnesses:
  passed their explicit editor-unavailable contracts. These harnesses cannot
  own the plugin's `EditorInterface` or `EditorUndoRedoManager` in a normal
  `SceneTree` process.
- Godot 4.7.2 headless editor initialization: plugin scripts compiled.
- Live bridge smoke tests: not completed because another Godot process was
  already listening on port 8081 and the existing bridge timed out. No
  process was terminated.

The earlier Gemini schema regression fix remains provider-only: the
`CountNodesAction` branch is excluded only from Gemini's nested batch union;
the public schema and tool semantics are unchanged. Screenshot support and
mutation tools remain deferred.

---

## Feature: `find_nodes_by_group`

### Test

Automated suite added to `tests/test_provider_contract.py` and
`tests/test_registry.py`, plus a permanent Godot 4.7.2 headless harness
(`addons/Execution_Agent/tests/find_nodes_by_group_harness.gd`)
exercising `AIAgentNodeTools.find_nodes_by_group_from_request` against
real group state.

Coverage:

- Schema accepts a valid request; blank `group_name` is rejected by
  required-field validation; registry membership, read-only
  classification, dispatch, success/zero-match passthrough, and
  batchable membership.
- Headless harness with real `add_to_group()` assignments
  (`EnemyA` + `EnemyB` in `enemies`; `EnemyB` + `Boss` in `hostile`;
  `Boss` also in `bosses`; `Civilian` ungrouped): the `enemies` query
  returns exactly `EnemyA`/`EnemyB` with real paths/names/types in
  traversal order; `hostile` returns `EnemyB`/`Boss`; `bosses` returns
  `Boss` (multi-group nodes appear for each of their groups);
  ungrouped nodes and the scene root never appear; a nonexistent group
  returns `count: 0` (success, not error); case differences
  (`Enemies`) and partial names (`enemy`) do not match; blank and
  missing `group_name` return structured errors; repeated calls are
  byte-equivalent; JSON serialization succeeds. Expected matches were
  cross-checked with direct `is_in_group()` calls on the fixture
  nodes.

### Result

- Focused Python tests: 131 passed.
- Full Python suite: 172 passed.
- Godot 4.7.2 headless harness: all cases passed.
- All pre-existing harnesses (`count_nodes`, `find_nodes_by_script`,
  `list_node_groups`, `list_node_signals`,
  `list_available_node_types`, `get_node_class_info`) re-run after the
  `collect_matching_nodes` extension: all pass, confirming
  `find_nodes`, `find_nodes_by_script`, and `list_node_groups`
  behavior are unchanged.

### Status

Confirmed working. No live end-to-end run against a running editor
bridge was performed for this tool.

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

---

# Mutation Architecture Contract Tests (2026-09-08)

## Scope

Minimal mutation architecture pass. Added `agent/mutation.py`
(classification, structured result contract, verification status,
`MutationRecord`), mutation telemetry (`MutationTelemetry`,
`record_mutation()`, mutation counts in `SessionSummary`), and a
single recording hook in `execute_single_action()`. No Godot-side
changes were required: the bridge already performs all mutations as
undoable editor-native `EditorUndoRedoManager` actions and reports
`undoable` and `verified_*` fields. No new mutation tools were
added; batch semantics, batch limits, session control, inspection
tools, and existing undo behavior were preserved unchanged.

## Test File

`tests/test_mutation_contract.py` - 23 tests, all passing.

| Test | Verifies |
| --- | --- |
| `test_registry_mutation_flags_match_canonical_set` | Registry `is_mutation` flags match the six known mutations |
| `test_registry_mutations_covered_by_boundary_metadata` | Registry mutations equal `boundary.py` target/equivalence metadata |
| `test_is_mutation_action_delegates_to_registry` | Classification delegates to the registry; unknown actions are not mutations |
| `test_valid_contract_result_passes` | A dict with boolean `success` satisfies the contract |
| `test_contract_violations_are_rejected` | Non-dict, missing, or non-boolean `success` results violate the contract |
| `test_verification_failed_on_unsuccessful_result` | Failure results are verification `failed` |
| `test_verification_unverified_without_claims` | Success without `verified_*` claims is `unverified` |
| `test_verification_verified_when_all_claims_true` | Success with all claims true is `verified` |
| `test_verification_failed_when_any_claim_false` | A false `verified_*` claim downgrades to `failed` even on reported success |
| `test_name_collision_detected_is_not_a_verification_claim` | `name_collision_detected` is informational only |
| `test_record_from_successful_verified_mutation` | Record carries action, target, verification, undoability, turn/step |
| `test_record_from_unverified_mutation` | Success without claims records `unverified`, `undoable` None |
| `test_record_from_failed_mutation_carries_error` | Failure records carry the bridge error and reported undoability |
| `test_record_from_failed_mutation_uses_validation_error_fallback` | `validation_error` is used when `error` is absent |
| `test_contract_violation_never_records_success` | Contract violations force failure status, never success |
| `test_record_is_frozen` | `MutationRecord` is immutable |
| `test_record_mutation_appends_mutation_telemetry` | Telemetry carries the record forward with session/model-call ids |
| `test_summary_counts_mutations` | Session summary reports mutation/success/failed/unverified counts |
| `test_mutation_recorded_in_addition_to_tool_action_telemetry` | Mutations add telemetry without removing `ToolActionTelemetry` |
| `test_non_mutation_action_records_no_mutation_telemetry` | Inspection actions produce no mutation records |

## Status

Confirmed working. Python-side only; full suite: 218 passed
(195 pre-existing + 23 new). No Godot headless run was required
because no `.gd` file changed.

---

# move_child Mutation Tool (2026-09-08)

## Scope

First real mutation tool built on the mutation architecture:
`move_child` moves an existing child within its parent to a
requested sibling index as one undoable, editor-native
`EditorUndoRedoManager` action. No changes were made to the
mutation architecture itself or to the six pre-existing mutation
tools. Batch limits, stop-on-first-failure, interrupted-batch
blocking, and session control are unchanged.

## Implementation

- Python: `MoveChildAction` schema (pydantic, `new_index >= 0`),
  registry entry (`required_fields=("node_path",)`,
  `is_mutation=True`), boundary metadata (fingerprint
  `node_path` + `new_index`, target `node_path`),
  `scene_tools.move_child()` -> `POST /move_child`.
- Godot: `AIAgentNodeTools.move_child_from_request()` routed at
  `/move_child`; validation (presence/types, node exists, has
  parent, not scene root, index in range), deterministic no-op
  (`moved: false`, no undo history, order still verified),
  single undoable action, post-move verification reading the
  real index and sibling order back from the scene
  (`verified_index`, `verified_order`), explicit unavailable
  error when the editor undo manager is absent.

## Python tests

Added cases to `tests/test_registry.py` (registration,
required-fields pin, dispatch, batch path with mutation
telemetry), `tests/test_mutation_contract.py` (canonical
mutation set, verified/failed record mapping), and
`tests/test_batch_boundary.py` (fingerprint match, different-index
bypass BLOCKED, different node not blocked). Full suite:
225 passed.

## Godot headless harness

`addons/Execution_Agent/tests/move_child_harness.gd`
(Godot 4.7.2 headless): passed.

- missing fields, non-integer and fractional indices rejected
- missing node and scene root rejected
- negative and past-the-end indices rejected with structured
  out-of-range error
- no-op (already-at-index) success with `moved: false`, unchanged
  order, `verified_index`/`verified_order` true
- explicit unavailable error when the editor undo manager is
  absent
- undo/redo cases are automatically exercised when the runtime
  binary permits instantiating `EditorUndoRedoManager`; in a
  plain headless `SceneTree` process it does not, so they are
  skipped there (documented environment limitation)

## Live bridge test (running headless editor with plugin)

All against the real `game_scene` via `POST /move_child`:

| Case | Result |
| --- | --- |
| Move `Player/RightArm` (index 2) to index 0 | success, `old_index: 2 -> 0`, real sibling order `[RightArm, Sprite2D, LeftArm, LeftLeg, RightLeg, SessionLifecycleTest]`, `verified_index: true`, `verified_order: true`, `undoable: true` |
| Same move repeated (no-op) | success, `moved: false`, order unchanged and verified, `undoable: false` |
| `new_index: 99` | structured out-of-range failure naming the valid range 0-5 |
| `node_path: "Ghost"` | `Node not found: Ghost` |

The editor undo history was not sampled through
`get_undo_history_summary` in this session (the endpoint returned
an empty payload in the headless editor environment, a pre-existing
inspection quirk unrelated to `move_child`); undoability is
confirmed by the committed `EditorUndoRedoManager` action and the
`undoable: true` result. The edited scene was not saved, so the
live moves left no disk changes.

## Status

Confirmed working. Python: 225 passed. Godot headless harness:
passed. Live bridge: all four cases matched the documented
contract. Undo/redo through the editor's undo system was not
directly exercised at runtime (headless limitation above); it is
guaranteed structurally by the single `EditorUndoRedoManager`
action with explicit do/undo methods.



# add_to_group / remove_from_group Mutation Tools (2026-09-08)

## Scope

Group membership mutations built on the same mutation architecture:
`add_to_group` adds an existing node to a persistent group, and
`remove_from_group` removes one. Each is one undoable, editor-native
`EditorUndoRedoManager` action. No changes were made to the mutation
architecture itself or to the pre-existing mutation tools. Batch
limits, stop-on-first-failure, interrupted-batch blocking, and
session control are unchanged.

## Implementation

- Python: `AddToGroupAction` and `RemoveFromGroupAction` schemas
  (pydantic; `action`, `node_path`, `group_name`), registry entries
  (`required_fields=("node_path", "group_name")`,
  `is_mutation=True`), boundary metadata (fingerprint
  `node_path` + `group_name`, target `node_path`),
  `scene_tools.add_to_group()` / `remove_from_group()` -> `POST
  /add_to_group` / `POST /remove_from_group`.
- Godot: `AIAgentNodeTools.add_to_group_from_request()` /
  `remove_from_group_from_request()` routed at the new endpoints;
  validation (presence/types, node exists, non-empty group name),
  deterministic idempotent cases (`changed: false`, no undo history,
  membership still verified), single undoable action, post-mutation
  verification reading real membership back via `is_in_group`
  (`verified_membership`), explicit unavailable error when the
  editor undo manager is absent.

## Python tests

Added cases to `tests/test_registry.py` (registration,
required-fields pin, dispatch, batch path with mutation
telemetry), `tests/test_mutation_contract.py` (canonical
mutation set, verified/idempotent/failed record mapping), and
`tests/test_batch_boundary.py` (fingerprint match, different-group
bypass BLOCKED, different node not blocked, mutation-target
extraction). Full suite: 235 passed.

## Godot headless harness

`addons/Execution_Agent/tests/add_remove_group_harness.gd`
(Godot 4.7.2 headless): passed.

- missing fields (group_name, node_path) rejected
- non-string and empty/whitespace group names rejected
- missing node rejected (both add and remove)
- explicit unavailable error when the editor undo manager is absent
- undo/redo cases are automatically exercised when the runtime
  binary permits instantiating `EditorUndoRedoManager`; in a plain
  headless `SceneTree` process it does not, so they are skipped
  there (documented environment limitation)

## Live bridge test (running headless editor with plugin)

All against the real `game_scene` via `POST /add_to_group` and
`POST /remove_from_group`:

| Case | Result |
| --- | --- |
| Add `Player/Sprite2D` to `test_group` | success, `changed: true`, `was_member: false`, `is_member: true`, `verified_membership: true`, `undoable: true` |
| Add `Player/Sprite2D` to `test_group` again (idempotent) | success, `changed: false`, `was_member: true`, `is_member: true`, `verified_membership: true`, `undoable: false` |
| Remove `Player/Sprite2D` from `test_group` | success, `changed: true`, `was_member: true`, `is_member: false`, `verified_membership: true`, `undoable: true` |
| Remove `Player/Sprite2D` from `test_group` again (idempotent) | success, `changed: false`, `was_member: false`, `is_member: false`, `verified_membership: true`, `undoable: false` |
| `node_path: "GhostNode"` | `Node not found: GhostNode` |
| `group_name: "   "` (whitespace) | `add_to_group requires a non-empty group_name.` |

The edited scene was not saved, so the live moves left no disk
changes.

## Status

Confirmed working. Python: 236 passed (235 + 1 new gemini regression test).
Godot headless harness: passed. Live bridge: all six cases matched the
documented contract. Undo/redo through the editor's undo system was not
directly exercised at runtime (headless limitation above); it is
guaranteed structurally by the single `EditorUndoRedoManager` action with
explicit do/undo methods.

> **Correction (superseded):** The narrative below is the historical record of the
> initial hypothesis. It is superseded. The confirmed root cause of the Gemini
> `400 INVALID_ARGUMENT` is provider-incompatible JSON-schema constraint keywords;
> `make_gemini_schema_compatible()` permanently fixes it by recursively removing
> `discriminator`, `minimum`, `maximum`, `minItems`, `maxItems` (and converting
> `oneOf` to `anyOf`). The `result_mode` enum injection for `CountNodesAction` /
> `MoveChildAction` is a separate structural-uniqueness workaround, not the 400 fix.
> The earlier live probe used `gemini-2.5-flash-preview-09-2025`; the current default
> model is `gemini-3.1-flash-lite`. The temporary `tmp_gemini_regression_probe.py`
> was removed. See the appended "Gemini structured-output 400 regression root cause"
> entry at the end of this file for the current, authoritative state.

## Gemini Schema Compatibility Fix for move_child (2026-09-09)

### Problem

When `MoveChildAction` was added to the `AgentDecision` union, Gemini
started rejecting the full schema request with `400 INVALID_ARGUMENT`. A
prior agent diagnosed this as structural overlap and added
`MoveChildAction` to both `GEMINI_NESTED_BATCH_EXCLUDED_ACTIONS` and
`GEMINI_TOP_LEVEL_EXCLUDED_ACTIONS` in `models/gemini_provider.py`. That
removal was the wrong fix: it stripped `MoveChildAction` entirely from
Gemini's generated schema, so the system prompt could still describe
`move_child` as a tool while Gemini's structured-output schema made it
impossible for the model to select. The practical symptom was that the
agent repeatedly chose `set_properties` or `rename_node` even when its own
reasoning identified `move_child` as the correct action.

### Investigation

Live A/B isolation was decisive: removing `MoveChildAction` from the Gemini
schema restored request acceptance, while removing the structurally-
overlapping group actions did not. Unlike `AddToGroupAction` /
`RemoveFromGroupAction`, which overlap each other, `MoveChildAction` was
the single action causing Gemini's union validator to reject the schema —
mirroring the earlier `CountNodesAction` failure pattern.

### Fix

Followed the proven `CountNodesAction` path: add a Gemini-only `result_mode`
enum injection in `make_gemini_schema_compatible()` so `MoveChildAction`
becomes structurally unique in the union, and remove it from both exclusion
sets so it flows into the top-level and nested-batch schemas. The public
Pydantic schema was intentionally left untouched (no `result_mode` field on
`MoveChildAction`); the Gemini transform injects `result_mode:
Literal["move_child"]` only in the converted schema Gemini sees. This keeps
`MoveChildAction` valid for Pydantic round-trip while making it
distinguishable from other union branches for Gemini.

### New test

Added `test_gemini_schema_injects_result_mode_for_move_child_so_it_is_no_longer_excluded()`
in `tests/test_provider_adapters.py`. The test asserts:

- `MoveChildAction` is present in both the top-level `AgentDecision` union
  and the nested `batch.actions` union in Gemini's generated schema (via
  `#/$defs/MoveChildAction` refs, not titles — batch items use refs).
- `MoveChildAction` is NOT in either exclusion set.
- `AddToGroupAction` and `RemoveFromGroupAction` remain excluded from the
  nested batch union only (unchanged behavior preserved).
- `result_mode` appears in the Gemini-transformed `MoveChildAction`
  properties (enum `["move_child"]`), matching the `CountNodesAction`
  pattern.

### Result

- `MoveChildAction` is now present in both the top-level `AgentDecision`
  union and the nested `batch.actions` union in the Gemini-generated schema.
- `AddToGroupAction` and `RemoveFromGroupAction` remain excluded from the
  nested batch union only (unchanged); they are still valid standalone
  actions and in the public Pydantic schema.
- `result_mode` appears in Gemini's view of `MoveChildAction`
  properties/required, matching the `CountNodesAction` pattern.
- No Godot code, mutation execution, registry semantics, batch behavior, or
  other providers were changed.
- All 8 provider adapter tests pass; full suite 236 passed.

### Live validation

A live Gemini schema probe was performed via the temporary
`tmp_gemini_regression_probe.py` script using the live Gemini API
(`models/gemini-2.5-flash-preview-09-2025`). Before the fix, a raw
`AgentDecision` schema produced `400 INVALID_ARGUMENT`. After the fix, the
same schema with the `result_mode` injection and exclusions removed was
accepted (`200 OK`). This confirms the fix resolves the structural Gemini
incompatibility without changing public schemas or tool semantics.

The probe was removed after validation. No `GEMINI_API_KEY` is committed to
the repo.

## Gemini structured-output 400 regression root cause (2026-09-09)

Authoritative, current state that supersedes the historical `result_mode` narrative above.

- Root cause: Gemini rejected the full `AgentDecision` schema with `400
  INVALID_ARGUMENT` because it cannot accept provider-incompatible JSON-schema
  constraint keywords that Pydantic emits. The confirmed set is:
  `discriminator`, `minimum`, `maximum`, `minItems`, `maxItems`.
- Fix: `make_gemini_schema_compatible()` (provider-only) recursively normalizes the
  schema — converts `oneOf` to `anyOf`, removes `discriminator`, and removes
  `minimum`, `maximum`, `minItems`, `maxItems`. Public Pydantic schemas, registry,
  bridge, and tool behavior are unchanged.
- The `result_mode` enum injection for `CountNodesAction` / `MoveChildAction` is a
  separate structural-uniqueness workaround that remains in the provider; it is not
  the 400 fix.
- Regression coverage retained: six permanent tests in `tests/test_gemini_provider.py`
  assert recursive removal of the five keywords, including on the real
  `AgentDecision` schema. `tests/test_provider_adapters.py` covers the normalized
  `oneOf` to `anyOf` / `discriminator`-removal shape.

### Results (2026-09-09)

- Provider suite (`tests/test_gemini_provider.py`, `tests/test_provider_adapters.py`,
  `tests/test_provider_contract.py`): 121 passed.
- Full Python suite (`pytest -q`): 242 passed.
- Live end-to-end validation with `gemini-3.1-flash-lite` passed all five scenarios
  (greeting, scene-tree inspection, live `move_child` with verified sibling order and
  undoability, a bounded batch of size <= 5, and a constrained `list_available_node_types`
  with a limit), with zero `400`s.
- The temporary probe `tmp_gemini_regression_probe.py` is removed. No `GEMINI_API_KEY`
  is committed.



# connect_signal / disconnect_signal / list_node_connections Tools (2026-09-09)

## Scope

Three signal-connection tools implemented end-to-end as one batch,
following the add/remove-from-group architecture exactly:

* `list_node_connections` (read-only, batchable): live incoming and
  outgoing connections of one node, sourced from
  `Node.get_incoming_connections()` and
  `Node.get_signal_connection_list()` with per-connection flags
  (`deferred`, `persistent`, `one_shot`), sorted deterministically.
* `connect_signal` (mutation): emitter `node_path` + `signal_name` ->
  `target_path` + `method_name`; optional boolean `deferred`.
  Validates presence/types, node existence, `has_signal`,
  `has_method`, and boolean `deferred` before acting. Idempotent
  no-op when the exact pair is already connected. Persistent
  (plus optional deferred) single undoable `EditorUndoRedoManager`
  action; `verified_connection` read back via `is_connected`.
* `disconnect_signal` (mutation): inverse; undo restores the original
  connection flags captured before removal. Idempotent no-op when
  not connected (requires no undo manager, since nothing changes);
  `verified_connection` read back.

Python wiring: `schemas.py` (`ListConnectionsAction`,
`ConnectSignalAction`, `DisconnectSignalAction`), registry entries
(`is_mutation` true for the two mutations), boundary metadata
(fingerprint includes `deferred` for `connect_signal`; mutation
target is the full connection identity
`node_path`+`signal_name`+`target_path`+`method_name`), three
`scene_tools.py` client functions, and three new system-prompt
catalog entries (items 14-16; subsequent items renumbered).

Godot wiring: `POST /list_node_connections`, `POST /connect_signal`,
`POST /disconnect_signal` in `ai_agent_router.gd`;
`_validate_signal_mutation_request`, `_resolve_connection_nodes`,
and the three `*_from_request` handlers in `ai_agent_node_tools.gd`.

## Rule 12 handling

`ConnectSignalAction` and `DisconnectSignalAction` are structurally
identical (same required fields; connect adds optional `deferred`),
so both were added to `GEMINI_NESTED_BATCH_EXCLUDED_ACTIONS` — the
established two-tier pattern (nested-batch exclusion first, top-level
escalation as needed). Both remain valid top-level actions.
`ListConnectionsAction` required no exclusion (same shape as the
existing `{node_path}`-only branches that live-validate cleanly).
No `result_mode` injection was needed.

## Python tests

Added: `test_registry.py` (registration, required-fields pin, three
dispatch cases including deferred, read-only boundary absence for
`list_node_connections`, connect/disconnect batch telemetry test),
`test_batch_boundary.py` (fingerprint match, deferred-change bypass
BLOCKED, different-method/signal not blocked because the target is
the full connection identity, target extraction),
`test_mutation_contract.py` (canonical mutation set extended;
verified/idempotent/failed record mapping for the new pair),
`test_provider_adapters.py` (regression guard: signal pair excluded
from the nested batch union, present top-level;
`ListConnectionsAction` present in the nested batch union).

Full suite: **258 passed**.

## Godot headless harness

`addons/Execution_Agent/tests/connect_disconnect_signal_harness.gd`
(Godot 4.7.2 headless): passed (exit 0).

- missing/non-string/empty `signal_name`/`target_path`/`method_name`
  and missing `node_path` rejected
- missing emitter node, missing target node rejected
- nonexistent signal rejected ("has no signal named ... Use
  list_node_signals ...")
- nonexistent method rejected
- non-boolean `deferred` rejected
- explicit unavailable errors for connect (new connection) and
  disconnect (existing connection, pre-wired via the raw Node API)
  when the editor undo manager is absent
- idempotent disconnect of a non-connected pair succeeds without the
  undo manager (no change, no undo history)
- read-only listing works without the undo manager
- undo/redo cases are automatically exercised when the runtime binary
  permits instantiating `EditorUndoRedoManager`; in a plain headless
  `SceneTree` process it does not, so they are skipped there
  (documented environment limitation, same as the group harness)

## Live bridge test (headless editor with plugin, isolated instance)

The user's running editor keeps the previously loaded plugin build,
so validation ran against a throwaway copy of the project (bridge
port 8082, copy deleted afterwards) hosting the updated scripts with
`game_scene.tscn` open. All against the real bridge:

| Case | Result |
| --- | --- |
| `list_node_connections` on `Player/Sprite2D` (clean) | success, 0 in / 0 out, `internal_connections_omitted: 5` |
| Connect `Sprite2D.tree_entered` -> `LeftArm.queue_free` | success, `changed: true`, `verified_connection: true`, `undoable: true` |
| Same connect repeated | success, `changed: false`, `was_connected: true`, `undoable: false` |
| Deferred connect `Sprite2D.tree_exited` -> `RightArm.queue_free` | success, `deferred: true`, `verified_connection: true`, `undoable: true` |
| Listing `Sprite2D` after connects | 2 outgoing, both `persistent: true`, the deferred one flagged; sorted |
| Listing `LeftArm` (incoming side) | 1 incoming with `source: Player/Sprite2D` |
| Disconnect the `tree_entered` pair | success, `changed: true`, `verified_connection: true`, `undoable: true` |
| Same disconnect repeated | success, `changed: false`, `undoable: false` |
| `signal_name: "made_up_signal"` | structured failure pointing to `list_node_signals` |
| `method_name: "made_up_method"` | structured failure |
| `node_path: "Ghost"` | `Node not found: Ghost` |
| `signal_name: "   "` | `requires a non-empty signal_name` |
| `deferred: "yes"` | `deferred must be a boolean` |
| Final listing | clean state restored |

### Findings from live validation

1. **Editor-internal connection noise**: every scene node carries
   non-persistent editor hooks (e.g. `SceneTreeEditor` methods on
   `script_changed`, `visibility_changed`, ...) whose peers are
   outside the edited scene. These were unfiltered at first and
   polluted listings (5 phantom connections on a fresh node).
   Fixed: connections with out-of-scene peers are omitted from the
   entries and reported as `internal_connections_omitted`,
   consistent with the bridge's scene-relative path contract.
2. **`get_incoming_connections()` key rename**: Godot 4.7 names the
   receiving callable `callable` in incoming-connection dictionaries
   (matching `get_signal_connection_list()`); the first
   implementation read `method` and incoming listings came back
   empty. Fixed by accepting either key. Note: the headless harness
   could not catch this because its incoming-side cases live in the
   undo-capable block, which is skipped in a plain headless
   `SceneTree` process — the live bridge run caught it.

The edited scene was not saved; the validation instance was
destroyed afterwards, leaving no disk changes to the real project.

## Live Gemini schema smoke test (Rule 12)

Provider: live `gemini-3.1-flash-lite` with the real
`AgentDecisionResponse` schema after
`make_gemini_schema_compatible()`. Three scenarios, zero 400s:

| Scenario | Result |
| --- | --- |
| "Connect tree_entered on Player/Sprite2D to queue_free on Player/LeftArm" | `connect_signal` decision, all fields correct, `deferred: null` |
| "Show all live signal connections of Player/Sprite2D" | `list_node_connections` decision, `node_path` correct |
| Two renames without inspection | `batch` of two `rename_node` items (excluded actions correctly not produced inside batch items) |

All decisions validated host-side through the Pydantic
discriminated union. Token usage normalized and reported. The smoke
script was run from a temporary stdin script and not committed.

## Status

Confirmed working. Python: 258 passed. Godot headless harness:
passed. Live bridge: all 14 cases matched the documented contract.
Live Gemini schema smoke test: passed (zero 400s). Runtime
undo/redo was not directly exercised in a live editor (same
documented headless limitation as the group tools); it is
guaranteed structurally by the single `EditorUndoRedoManager`
action with explicit do/undo methods, including flag-preserving
undo for `disconnect_signal`.

# create_script / attach_script / detach_script / get_script_content / list_script_diagnostics Tools (2026-09-09)

## Scope

Script tools Phase A: five tools implemented end-to-end as one
batch. Godot side lives in a NEW `ai_agent_script_tools.gd`
(`AIAgentScriptTools`, fourth tool domain alongside node, property,
and editor tools), wired through the router and instantiated by the
plugin.

* `create_script` (mutation): writes a new `.gd` file with the
  full content provided by the model. Strict path discipline
  (res:// auto-prefix, .gd required, no `..`, no backslashes,
  non-empty file name), deterministic refusal on existing files,
  missing parent directories created. Parse gate BEFORE writing:
  a fresh `GDScript` parse must succeed or nothing is written.
  First mutation whose real change is NOT undoable
  (`undoable: false`); verified by reading the file back
  (`verified_write`).
* `attach_script` (mutation): loads the script, sets it on the
  node as one undoable `EditorUndoRedoManager` property action
  (undo restores the previous attachment). Idempotent no-op when
  the same script is attached; deterministic refusal when a
  different script is attached. `verified_attachment` read back
  via `get_script()` + `resource_path`.
* `detach_script` (mutation): inverse; undo restores the previous
  script. Idempotent no-op when no script is attached (works
  without the undo manager, since nothing changes).
* `get_script_content` (read): full source from disk.
* `list_script_diagnostics` (read): fresh parse of the current
  file content; reports `parse_ok` plus the Godot error string.
  Works headless AND live (an improvement over the originally
  planned live-editor-only diagnostics).

Python wiring: 5 schemas, 5 registry entries (3 mutations), 3
boundary registrations (create_script target = script_path; attach/
detach target = node_path), 5 scene_tools client functions, 5 new
system-prompt catalog entries (items 17-21; subsequent items
renumbered to 38 total).

## Rule 12 handling

No nested-batch exclusions added. Structural analysis: the only
identical required sets are against tolerated, live-validated
precedents (`detach_script` {node_path} vs `delete_node`;
`get_script_content`/`list_script_diagnostics` {script_path} vs
`find_nodes_by_script`). The analysis was confirmed by the live
Gemini smoke test; the two-tier exclusion pattern remains the
documented fallback. New in this batch: GDScript content travels
as an escaped multi-line JSON string inside the AgentDecision -
covered explicitly by a live round-trip scenario.

## Python tests

Added: `test_registry.py` (registration, required-fields pin, 5
dispatch cases, read-only boundary absence for the two inspectors,
script batch telemetry test asserting the first undoable: false
verified mutation record), `test_batch_boundary.py`
(create_script: different-content bypass BLOCKED because the
target is the file; attach_script: different-script bypass BLOCKED
because the target is the node's attachment; target extraction),
`test_mutation_contract.py` (canonical mutation set extended to
14; create_script verified-but-not-undoable record; failed write
verification; attach verified; detach idempotent verified),
`test_provider_adapters.py` (Rule 12 analysis record test: all 5
script actions present top-level and in the nested batch union,
no exclusions).

Full suite: **280 passed**.

## Godot headless harness

`addons/Execution_Agent/tests/script_tools_harness.gd`
(Godot 4.7.2 headless): passed (exit 0), self-cleaning (scratch
files removed at start and on every exit path; verified no
residue).

- create_script: missing/non-string/empty content, missing .gd,
  traversal, backslash, empty file name all rejected
- parse gate: broken content rejected, NOTHING written to disk
- existing-file refusal
- get_script_content / diagnostics: missing script rejected
- attach_script: validation failures; valid request without the
  undo manager reports the explicit unavailable error
- detach_script: idempotent no-op works without the undo manager;
  removing a pre-attached script (set via the raw Node API)
  reports the unavailable error without it
- undo-capable phase (when `EditorUndoRedoManager` is
  instantiable): create/read/diagnostics roundtrip, attach,
  idempotent attach, different-script refusal, detach, idempotent
  detach, undo/redo restoring the attachment; in a plain headless
  `SceneTree` process this phase is skipped (documented
  environment limitation)
- Expected stderr noise: the parse gate's rejection of
  deliberately-broken content makes Godot print its own
  `SCRIPT ERROR: Parse Error` line; the tool handles it
  structurally and the harness asserts the structured failure.

## Live bridge test (headless editor with plugin, isolated instance)

Throwaway project copy (bridge port 8082), destroyed afterwards;
`game_scene.tscn` open. All 18 cases matched the documented
contract:

| Case | Result |
| --- | --- |
| `create_script` valid multi-line content into new `scripts/` dir | success, dir auto-created, `parse_ok: true`, `verified_write: true`, `undoable: false` |
| Same create repeated | `script already exists` refusal |
| `create_script` broken content | `does not parse (Parse error). Nothing was written to disk.` |
| Read the would-be broken file | `script not found` (gate honored) |
| `get_script_content` roundtrip | source identical, line/size correct |
| `list_script_diagnostics` on created script | `parse_ok: true` |
| `attach_script` onto `Player/LeftArm` | success, `verified_attachment: true`, `undoable: true` |
| Same attach repeated | idempotent no-op, `undoable: false` |
| Create second script, attach over existing | `different script attached ... Use detach_script first` |
| Attachment cross-checked via `get_node_property` | script property reports `<GDScript>` object |
| `detach_script` | success, `detached_script` path reported, `verified_attachment: true`, `undoable: true` |
| Same detach repeated | idempotent no-op |
| Ghost node / .txt extension / traversal / empty content / diagnostics on missing | all structured failures |

The validation instance was destroyed afterwards; no disk changes
remain in the real project (the harness cleans its own scratch
files).

## Live Gemini schema smoke test (Rule 12)

Provider: live `gemini-3.1-flash-lite`, real
`AgentDecisionResponse` schema after
`make_gemini_schema_compatible()`. Three scenarios, zero 400s:

| Scenario | Result |
| --- | --- |
| "Create a spawner script" (realistic multi-line GDScript) | `create_script` decision; 314 chars, 11 newlines, `extends Node2D` + `func spawn_enemy` present; JSON escaping round-trip verified programmatically |
| "Attach the script to Player/LeftArm" | `attach_script` decision, fields correct |
| Two renames without inspection | `batch` of two `rename_node` items |

## Status

Confirmed working. Python: 280 passed. Godot headless harness:
passed. Live bridge: all 18 cases matched the documented contract.
Live Gemini schema smoke test: passed (zero 400s, multi-line
content round-trip verified). The agent can now produce
parse-verified GDScript files and attach them to scene nodes;
script modification (`edit_script`) remains Phase B, and
behavioral verification remains future runtime-tool territory.

# Three-Batch Expansion: edit_script, Scene Files, Project Introspection (2026-09-10)

## Scope

Eighteen tools implemented in one session (three planned batches),
following the established architecture. Registry grows from 38 to
56 actions (33 read-only, 20 mutations, 3 meta).

**Batch 1 — script Phase B + documentation.**
`edit_script` (whole-file replacement; parse gate BEFORE write so
a rejected edit leaves the previous working content; never
creates; byte-identical no-op; non-undoable, `verified_write`
read-back), `replace_in_script` (deterministic anchored edit:
exactly-once anchor, zero-occurrence + replacement-present =
already-applied no-op, ambiguous anchors refused with match
count, deletion via empty new_string; parse gate; non-undoable),
`get_class_documentation` and `search_documentation` (Python-side
tools reading `data/godot_docs_4.7.2.json.gz` — the project's
first tools that never touch the bridge; data built by
`scripts/prepare_godot_docs.py` from the official 4.7.2-stable
docs XML, 810 classes, 1.2 MiB gzip; rationale in
`MODEL_KNOWLEDGE_DRIFT.md`). Shared `_gated_write_script` helper
now backs create/edit/replace alike.

**Batch 2 — scene file operations** (new Godot domain
`ai_agent_scene_file_tools.gd`, fifth tool domain):
`save_scene` (editor-only; verified by modification-time delta;
unsaved-new-scene handled with structured failure),
`create_scene` (headless-capable; ClassDB-validated root type;
pack + ResourceSaver; never overwrites; creates parent dirs;
deliberately does NOT open the scene; verified by load-back of
root type+name), `instantiate_scene` (undoable add_child +
set_owner action mirroring create_node's pattern; name fallback
chain new_name -> instanced root name -> file name; ACTUAL name
reported because add_child renames on conflict;
`verified_instance` via scene_file_path), `get_scene_dependencies`
(PackedScene state walk: sub-scenes via get_node_instance,
resources via property values; sorted; 200-entry cap with
`internal_omitted`), `get_scene_tree_of` (instantiates without
entering the tree, reuses node_tools serialization via
composition, frees immediately), `list_open_scenes` (editor-only;
marks the edited scene).

**Batch 3 — property introspection and project awareness.**
`get_property_info` (exact property reflection: type, hint,
hint_string, usage, editable, JSON-safe current value and ClassDB
class default), `get_node_children_summary` (bounded 200, sorted
index, `truncated`/`omitted`), `assign_resource_to_property`
(undoable property action; strict res:// path rules, any resource
extension; property-exists and editable checks; idempotent
same-path no-op; `verified_assignment` via resource-path
comparison), `get_resource_info` (class/name/local_to_scene —
local_to_scene read defensively via `get()` after the live bug
below), `list_project_files` (DirAccess walk; dot-directories
excluded; extension filter with dot normalization; limit 1-500
default 100; walk cap 5000 with `walk_truncated`),
`search_in_files` (bounded scan: 500 files, bounded large-file
region, per-line matches with bounded snippets; default
extensions gd/tscn/tres/cfg/json/md/txt; `scanned_files`,
`scan_cap`, conservative `truncated`), `get_global_class_list`
(ScriptServer is NOT exposed to GDScript — confirmed via ClassDB —
so this reads `.godot/global_script_class_cache.cfg`, the
editor's own cache), `get_input_map` (live InputMap with
`as_text()` events; note: inside the editor this includes
editor-internal actions).

## Rule 12 handling

`EditScriptAction` {script_path, content} is structurally
identical to `CreateScriptAction`, so both were added to
`GEMINI_NESTED_BATCH_EXCLUDED_ACTIONS` (established pair
exclusion). All other new actions follow tolerated live-validated
precedents (no-field family: save/list_open/get_global_class_list/
get_input_map; {node_path} family: get_node_children_summary;
{class_name} pair: get_class_documentation vs get_node_class_info;
{node_path, property_name} pair: get_property_info vs
get_node_property; unique sets: replace_in_script,
search_documentation, create_scene, instantiate_scene,
get_scene_dependencies, get_scene_tree_of,
assign_resource_to_property, get_resource_info). Documented in
tests/test_provider_adapters.py.

## Python tests

Full suite: **330 passed** (+50). Added: test_registry.py (18
dispatch cases, read-only boundary tests, boundary target
assertions, Python-side docs dispatch test),
test_batch_boundary.py (six new mutations:
content/replacement/root-type/scene/resource bypass BLOCKED,
different-file/parent not blocked, target extraction including
save_scene's empty target), test_mutation_contract.py (canonical
set extended; verified non-undoable records for edit/save/create;
failed write verification; instantiate/assign verified records),
test_provider_adapters.py (script-edit pair exclusion; full
remaining-action batch-union presence), and NEW
tests/test_godot_docs.py (bundle version, class entry structure,
sections filter, unknown class/section failures, ranked search,
bounds and input validation).

## Godot headless harnesses

All green (exit 0, zero assertion failures):

- `script_tools_harness.gd` (extended): edit/replace validation,
  never-creates contract, byte-identical no-op, parse-gate
  leaves-file-unchanged proof via read-back, ambiguous anchor
  refusal, already-applied no-op, successful anchored edit,
  replacement-that-would-not-parse refused.
- `scene_file_tools_harness.gd` (new): path discipline, root type
  validation (unknown class, non-instantiable CanvasItem),
  create/load-back verification, overwrite refusal, dependency
  structure, tree-of, editor-only tools unavailable headless,
  instantiate validation + undo/redo in the undo-capable phase;
  self-cleaning.
- `property_tools_harness.gd` (new): property info reflection,
  unknown property, resource assignment validation (missing,
  traversal, unknown property), unavailable headless; full
  assign/idempotent/undo-restore cycle in the undo-capable phase
  using res://icon.svg onto a Sprite2D texture.
- `project_inspection_harness.gd` (new): bounded/sorted/excluded
  listing, prefix+extension filters (dot normalization),
  truncation flags, limit validation, content search with hit
  verification against ai_agent_router.gd, global class list
  including the new tool classes, input map ui_* actions.
- `connect_disconnect_signal_harness.gd` (regression): unchanged.

Harness-expectation bugs fixed during development (the tools were
correct each time): an ambiguous-anchor case seeded with a
single-occurrence file, a sort-order assumption about
project.godot under the default limit, and an invalid size
comparison across different prefix filters.

## Live bridge test (headless editor with plugin, isolated instance)

Throwaway copy on port 8082, destroyed afterwards. 20+ cases:

| Area | Result |
| --- | --- |
| edit_script / replace_in_script (create -> edit -> replace -> already-applied no-op -> read-back) | all verified_write true; final source confirmed |
| create_scene | success, root name/type verified by load-back |
| instantiate_scene under Player | success, `verified_instance: true`, actual name reported |
| get_scene_dependencies on game_scene | node_count 7, reports `res://godot_bridge.gd` as script resource |
| get_scene_tree_of on SAVED game_scene after save_scene | shows the instanced child — end-to-end persistence PROOF |
| save_scene | verified_write true |
| list_open_scenes | edited_scene marked |
| get_property_info (Sprite2D.texture) | type Object, hint_string "Texture2D", editable, class_default — exactly the assignment guidance |
| assign_resource_to_property (icon.svg -> texture) | verified_assignment true, undoable |
| attach probe script onto the instanced scene root | verified, undoable |
| list_project_files / search_in_files / get_global_class_list (9 classes incl. new tools) / get_input_map | all structured and bounded |

### Bugs found by live validation (fixed and re-verified)

1. `get_resource_info` crashed with "Invalid access to property or
   key 'local_to_scene' on CompressedTexture2D": some Resource
   subclasses do not expose `local_to_scene` through their
   property list, and typed member access fails at runtime. Fixed
   by defensive `resource.get("local_to_scene")` (null when
   absent).
2. `search_in_files limit: 3` was rejected: JSON request bodies
   decode integral numbers as floats in GDScript, so the strict
   `typeof != TYPE_INT` check failed. `_validate_result_limit` now
   accepts int and float and coerces via `int()`.

## Live Gemini schema smoke test (Rule 12)

Live `gemini-3.1-flash-lite` with the full 56-action schema after
normalization. Five scenarios, zero 400s: replace_in_script
(exact anchor extraction), get_class_documentation (sections
filter respected), save_scene, assign_resource_to_property (all
fields correct), and batch generation with the new exclusions
(no create_script/edit_script items inside batches). One
scenario initially returned an unexpected (but schema-valid)
decision shape and passed on re-run with a clearer request —
noted as normal model variance, not a schema problem.

## Status

Confirmed working. Python: 330 passed. All five headless
harnesses pass. Live bridge: all cases matched the documented
contract, including the create -> instantiate -> attach -> save
-> verify-on-disk persistence chain. Live Gemini smoke: zero 400s.
Remaining known gaps: `open_scene` deferred (edited-scene context
invalidation), `create_resource` deferred (design), vision
(describe_current_scene) and runtime/playtest tools remain future
work per FUTURE_TOOLS.md.

# Autonomy Milestone: Runtime Loop, Scene Navigation, Project Configuration (2026-09-10)

## Scope

Eight tools plus two agent-infrastructure features in one session,
completing the structurally possible tool surface (vision and
editor UI excluded). Registry: 56 -> **64 actions** (38 read-only,
23 mutations, 3 meta).

**Playtest loop:** `run_scene` (editor play, main or custom scene,
verified via `is_playing_scene`/`get_playing_scene`; refuses when
a game is already running), `stop_run` (idempotent,
`verified_stop` read-back), `get_runtime_output` (debugger-capture
buffer, bounded 500, `clear` semantics), and `run_scene_offline`
(Python-side subprocess runner: headless scene execution with
exit code, bounded stdout/stderr, `script_errors_detected`, and
a killing timeout).

**Scene navigation/configuration:** `open_scene` (unsaved-changes
guard, context-switch warning, verified via scene_file_path),
`save_scene_as` (never overwrites; the API returns void so the
write is verified by read-back), `set_project_settings` (1-10
settings, sensitive keys rejected, previous values reported for
manual revert, per-key read-back verification), `create_resource`
(ClassDB-validated instantiable Resource types only, explicit
unknown-property rejection, .tres only, load-back verified).

**Infrastructure:** telemetry JSONL export
(`export_session_jsonl`; summary owned by AgentSession and passed
explicitly — a bug caught by tests) wired into session
termination, best-effort and never breaking it; the documented
empty-input silent-termination gap fixed (now logged).

## Rule 12 handling

All eight new actions follow tolerated live-validated schema
precedents; no nested-batch exclusions needed. Verified in the
live smoke implicitly by valid decision generation.

## Python tests

Full suite: **348 passed** (+18: dispatch cases, boundary
fingerprint/target tests including save_scene's empty-target
semantics, mutation records, telemetry export wiring, and the
Python-side offline-runner dispatch test).

## Godot headless harness

`runtime_tools_harness.gd` (new, headless): debugger-buffer
behavior is live-validated only (the EditorDebuggerPlugin base
class cannot be instantiated headless — `.new()` returns null);
project-settings cases (validation, sensitive rejection,
previous-value reporting, read-back verification, cleanup of the
test key) and resource cases (type validation including
non-instantiable and Node types, .tres path rule, unknown-property
rejection, create/load-back/overwrite-refusal) run fully headless
with self-cleaning. All other harnesses: regression green.

## Live bridge validation (isolated editor instance)

- Full autonomous pipeline: `open_scene` (with context-switch
  warning) → `attach_script` → `run_scene` → probe script
  self-quits → `stop_run` idempotency — all verified.
- `save_scene_as`: verified write + path switch.
- `set_project_settings`: two keys set, previous values reported
  (application/config/name changed Agent_Host ->
  Agent_Host_LiveCheck in the disposable copy), per-key verified.
- `create_resource` + `get_resource_info`: Curve created and
  inspected as Curve.
- `run_scene_offline` (against the copy, via PROJECT_PATH
  override): captured print output in stdout AND a push_error
  backtrace in stderr from a real subprocess run, with exit code
  0 and `script_errors_detected: false`.

### Engine limitation found (drives the design)

Godot 4.7.2's built-in debugger consumes a game's output and
error messages BEFORE editor debugger plugins are consulted:
`_has_capture` was queried for arbitrary prefixes
("agent_probe", "game_view") but never for "error"/"output", so
plugins cannot intercept a game's built-in output. This is why
runtime output reading is implemented as `run_scene_offline`
(subprocess ownership) rather than debugger interception. The
debugger capture remains registered for custom-capture
integrations.

### Bugs found and fixed during validation

1. `export_session_jsonl` read `summary` from the observability
   instance; the summary is owned by the AgentSession — caught
   immediately by the test-suite bootstrap (AttributeError during
   terminate would have broken every session end).
2. `EditorInterface.save_scene_as()` returns void in 4.7 (unlike
   `save_scene()`), so the mutation is verified purely by
   read-back.
3. Debugger plugin registration uses
   `EditorPlugin.add_debugger_plugin()` in 4.7 — the
   `_get_debugger_plugin()` virtual from older documentation is
   never queried; registration now happens in `_enter_tree`.

## Status

Confirmed working. Python: 348 passed. Six headless harnesses
green. Live bridge: playtest loop, scene navigation, project
configuration, resource creation, and offline execution all
matched the documented contract. The agent can now autonomously:
build scenes, write and edit scripts, wire signals, configure the
project, create resources, RUN its work headless, read its own
errors, and iterate — the full edit → run → fix loop from the
project goals. Remaining gaps: vision (describe_current_scene),
runtime tree/input inspection (needs in-game instrumentation),
editor UI (user-directed), agent-triggered undo (shared undo
stack with the human — deliberately rejected).

# Lint + Refactoring + Token Compaction Batch (2026-09-11)

## Scope

Three batches delivered as one coherent change set, bringing the
registry to **67 actions** (40 read-only, 24 mutations, 3 meta):

1. **scan_project_issues** (read-only, editor_tools): bounded
   project lint — script_parse_error / scene_load_failed /
   missing_dependency, with prefix + limit bounds, scan cap 500,
   explicit total_matches/truncated.
2. **rename_script** + **find_replace_across_files** (mutations,
   NEW `ai_agent_refactor_tools.gd`, fifth tool domain; router
   and plugin wired): deterministic, parse-gated, two-phase
   multi-file refactoring. rename_script moves the file + .uid
   sidecar first (preload() resolves at parse time) and rewrites
   references in .gd/.tscn/.tres/.cfg/project.godot; regression-
   only parse gate (a file whose original content already failed
   to parse never blocks); rollback on parse regression;
   verifies no leftover references and reports stale live nodes
   in the edited scene. find_replace_across_files is bounded by
   max_files (refuses over-bound requests entirely), parse-gated
   the same way, and verified against the exact computed
   replacement.
3. **Token compaction** (optional parameters, all backward
   compatible; full fidelity retained on demand):
   `get_script_content` start_line/line_count (1-500) with
   total_lines/end_line/truncated; `get_scene_tree` and
   `get_scene_tree_of` max_depth (1-50) with children_truncated
   markers and a top-level truncated flag; `get_node_properties`
   property_names filter (<= 50 names, missing names reported as
   not_found); `run_scene_offline` max_output_chars (500-50000,
   default 8000, tail-kept). Python-side conversation compaction
   gained dedicated summaries for paged get_script_content and
   get_node_properties results. Catalog entries 65-67 appended;
   five existing entries amended.

## Rule 12 handling

AgentDecision schema changed (3 new actions + 5 optional
parameter extensions; both unions updated). Live Gemini smoke
(gemini-3.1-flash-lite, real AgentDecisionResponse schema after
make_gemini_schema_compatible): 4/4 scenarios passed with zero
400s — scan_project_issues, rename_script,
find_replace_across_files, paged get_script_content — all
validated through the Pydantic discriminated union with correct
fields. (First attempt at one scenario produced search_in_files:
correct model behavior per the catalog's "search first" advice,
not a schema failure; the scenario was made unambiguous.)

## Python tests

358 passed (was 348): registry +boundary/mutation-contract
updates for the two new mutations (rename_script target =
script_path; find_replace_across_files = exact fingerprint only)
and new dispatch cases including every compaction parameter.

## Godot headless harness

All 21 runnable harnesses green, 0 assertion failures:
- NEW `refactor_tools_harness.gd`: rename success (reference
  rewrite in .tscn + .gd, .uid sidecar move, verified load,
  zero leftover refs), nested-directory move, refusal cases
  (missing source, existing target, identical paths, wrong
  extension), find/replace success + repeat refusal + max_files
  refusal + parse-gate abort (nothing written) + not-found +
  identical old/new. Harness lesson: it must never contain the
  searchable literals it exercises (a successful find/replace
  rewrote the harness mid-run once — markers are now assembled
  from parts).
- NEW `scan_project_issues_harness.gd`: structured shape,
  parse-error detection, missing-dependency detection
  (including a uid-form ext_resource fixture), good scene never
  flagged, nonexistent-prefix structured failure.
- `script_tools_harness.gd` extended: get_script_content paging
  (exact window, tail page untruncated, beyond-EOF empty page,
  validation failures).

## Live bridge validation (isolated editor instance, port 8082)

- scan_project_issues: full-project scan clean (42 files).
- rename_script: create -> rename -> reference updated in
  preload user script, verified_load, zero leftovers, no stale
  scene nodes.
- find_replace_across_files: verified replacement; not-found
  refusal; over-bound refusal semantics confirmed headless.
- get_script_content paging: exact windows incl. empty-line and
  tail pages.
- get_scene_tree max_depth=1 and get_node_properties
  property_names verified against the opened scene.
- get_scene_tree GET route retained; POST variant serves the
  depth-bounded request.

### Engine limitations found (three real bugs fixed during validation)

1. **class_name parse false-positive**: a fresh detached
   GDScript parse of a file whose class_name is already
   registered in the running editor fails (duplicate global
   class). scan_project_issues therefore reports a parse error
   only when the editor's own load also rejects the file
   (load() null or can_instantiate() false); find_replace/
   rename parse gates are regression-only (original parse
   status compared). Headless-only behavior is unaffected.
2. **Substring verification trap**: verifying a replacement via
   `contains(old_string)` false-alarms when new_string contains
   old_string ("Node" -> "Node2D"); verification now compares
   the read-back against the exact computed replacement.
3. **uid-form dependencies**: ResourceLoader.get_dependencies()
   returns strings like `uid://abc::::res://x.gd` that
   FileAccess cannot resolve; the res:// part is extracted
   before the existence check (game_scene.tscn's own godot_bridge
   dependency was falsely flagged before the fix).

## Status

Confirmed working. Python: 358 passed. Headless harnesses green.
Rule 12 live smoke passed. Live bridge cases matched the
documented contract. The agent can now audit the project it
mutated (lint), restructure scripts without dangling references
(refactor), and keep large inspections out of its own context
(compaction) — without expanding the rejected surface.

# Editor UI Phase 1: Agent Observability Bottom Panel (2026-09-11)

## Scope

Phase 1 of ROADMAP Phase 9 (editor UI), monitor-only: the plugin
now registers an "AI Agent" bottom panel beside Output/Debugger.
No agent controls, no AgentDecision change (Rule 12 not
triggered), registry unchanged at 67 actions.

**Data path (reverse push).** Python's `agent/ui_reporter.py`
posts flat events to the new bridge route `POST /agent_event`
(fire-and-forget, 1 s timeout, all errors swallowed, disable via
AGENT_UI_EVENTS=0). The plugin's new state store
(`ui/ai_agent_state_store.gd`, sixth tool-adjacent domain)
applies them, keeps bounded rings (500 events / 200 ledger / 200
metrics / 50 answers), and notifies the panel via signals.
`GET /agent_state` exposes a read-only snapshot for validation.
Hook sites in `godot_agent.py`: session start/terminate,
begin_next_turn (turn_started), around `ask_model`
(request_sent / model_response with real usage from
observability), execute_single_action (tool_started/tool_finished
with duration, verification, undoable, mutation target, incl.
batch items), batch start/finish, compaction (new optional
`ui_reporter` param on compact_conversation, all three call
sites), blocked actions, validation rejections, the four fatal
error paths, max-steps, turn_completed, and the premature
exit_session guard. `GODOT_BRIDGE_URL` is now env-overridable in
scene_tools (single source for tool calls and UI events).

**Panel.** Header strip: status pill (editor-theme
success/warning/error/accent colors), status detail, turn/step,
elapsed clock, model label, token totals, and a reserved
"approval gates: off" slot for the control phase. Four tabs:
Activity (turn-grouped timeline: steps, decisions, tool results
with verification/duration, compactions, blocked rows),
Mutations (ledger with verification coloring, undoable vs
file-level, double-click navigates the FileSystem dock to the
changed file), Answers (per-turn final answers), Metrics
(per-call prompt/output/duration table + totals).

## Tests

Python 364 passed (+6: reporter payload shape, disabled no-op,
network-failure swallowing, shared bridge URL, env disable,
constructor URL override). Headless harness
`agent_state_store_harness.gd` covers the full status lifecycle,
run_scene_offline's distinct status, ledger/answers/metrics
accumulation, ring bounds (600 events -> capped 500), unknown
event tolerance, usage-unavailable accounting, snapshot shape,
and the two router routes including malformed rejections. The
panel script is construct-checked against a live store.

## Live validation (isolated editor instance, port 8082)

- Plugin loads with the panel registered; zero script errors.
- Scripted event sequence via curl: status transitions
  (ready -> thinking -> executing -> completed), token totals,
  ledger entry with verification + target_path, answer stored,
  malformed event rejected.
- REAL end-to-end: one agent turn run against the copy with
  GODOT_BRIDGE_URL=http://127.0.0.1:8082 (2 model calls,
  12,891 in / 129 out tokens) — the store received the full
  timeline (steps, decisions with per-call tokens, count_nodes
  with 32 ms duration, answer) and /agent_state reported
  status completed.

### Bugs found and fixed during validation

1. `TabContainer.add_tab()` does not exist in 4.7 — tabs are
   added as children then titled by index (the panel assumed a
   newer API; caught by the live editor load).
2. JSON numbers arrive as floats in GDScript: turn numbers in
   event summaries displayed as "Turn 1.0"; now coerced to int
   in the store.

### Known limitation

Piped-stdin agent runs raise RuntimeError (PEP 479) at EOF
because `input()`'s StopIteration escapes the `iter_steps`
generator; interactive EOF raises EOFError properly. Test-
artifact only; not a product path.

## Status

Confirmed working. Python: 364 passed. Harnesses green. Live
bridge: panel loaded, event pipeline and real agent turn
verified end-to-end. Next UI phases: dock card + toasts
(phase 2), control phase (input box, New Session, context
meter — requires the service refactor), approval gates
(phase 3).

## Phase 1 revision round (2026-09-11, zenpieV feedback)

Five changes after zenpieV's first hands-on session:

1. **Mutations ledger completeness (the reported bug).** The
   batch path was verified correct end-to-end (a real
   batch-of-3 create_node run put all 3 in the ledger), but
   two real defects were found and fixed around it:
   (a) `session_started` reset the ENTIRE store, and each
   agent CLI process emits session_started at startup — so
   mutations from earlier agent runs silently vanished. The
   ledger is now a project-level audit trail that survives
   session_started (timeline/metrics/chat still reset); the
   store only rolls it over at the 200-entry cap.
   (b) create_node rows had an empty Target column (its
   mutation-target is empty by design), making rows
   indistinguishable; the reporter now synthesizes the
   target from parent_path/node_name. Batch items also carry
   batch_index/batch_size on tool_started/tool_finished.
2. **Model name**: the provider prefix ("gemini:...") was
   dropped; the header shows the plain model name.
3. **Chat tab (chat-LLM layout, ahead of the input box).**
   The Answers tab became Chat: per turn a user-request
   bubble (accent-tinted), the model's reasons as a dim
   thinking stream, then the answer bubble once the turn
   completes. Backed by a new chat_turns transcript in the
   store; the new `thinking` event (fired once the decision
   is fully validated, carrying reason + action + usage)
   feeds both the chat stream and the activity timeline,
   replacing the token-only model_response row. Turn 1 now
   announces itself (its request came from a module-level
   input() that never emitted turn_started — its thinking
   and answer were previously dropped from the transcript).
4. **THINKING status color + animation**: warm orange pulse
   (background lerps between two orange tones with a
   matching soft border, ~2.6 rad/s); red is reserved for
   errors; executing/offline stay accent-blue.
5. Verified live on the isolated 8082 instance with two
   real agent turns (batch-of-3 create_node + a count
   turn): ledger 2 create_node entries with targets across
   a later single-session run, both chat turns complete
   with reasons and answers, plain model name, zero editor
   script errors. Python: 364 passed; store harness extended
   (thinking/chat/persistent-ledger/batch-field cases).

6. **Chat rendering refinement (second round of zenpieV
   feedback).** The per-turn thinking stream collapsed from
   an accumulating list to ONE in-place dim line whose text
   is the latest decision reason (each new reason replaces
   the previous, chat-LLM style); when the turn completes
   the thinking line is removed entirely and only the
   bright answer bubble remains (explicit bright
   default_color on the RichTextLabel). Store change:
   chat thinking is a single overwritten string, cleared on
   turn_completed. Verified by harness assertions
   (overwrite + cleared-on-completion) and a scripted live
   sequence: in-flight turn shows the single line, the
   completed turn shows only the answer.

# Mode Button Restyle (2026-09-12, zenpieV feedback)

The Chat input's mode control is now a two-state display
button instead of a plain toggle: it always shows the
CURRENT mode as its text - "Plan" on an orange fill
(matching the THINKING pulse family) or "Act" on a fixed
blue - and clicking switches to the other mode. User chat
bubbles mirror the same pair (orange tint for plan turns,
blue tint for act turns) so bubble and button colors agree.

Two follow-up fixes from zenpieV's hover test, both
theme-related and worth remembering:

1. A TOGGLED-ON button that is hovered draws its
   `hover_pressed` stylebox, NOT `hover` - not overriding
   `hover_pressed` made the Plan state fall back to the
   theme's grey default on hover ("color completely
   removed"). The fix overrides every toggle state:
   normal/hover/pressed/hover_pressed/disabled, with
   focus as a border-only box on top.
2. The user's editor theme renders `accent_color` RED
   (same reason THINKING previously looked red), so Act's
   blue must be a fixed constant, not the theme accent.
   `MODE_COLOR_PLAN`/`MODE_COLOR_ACT` are now the single
   source for the button and the chat bubbles.

Verified: editor loads with zero script errors.



The Chat input's mode control is now a two-state display
button instead of a plain toggle: it always shows the
CURRENT mode as its text - "Plan" on an orange fill
(matching the THINKING pulse family) or "Act" on the editor
accent blue - and clicking switches to the other mode.
User chat bubbles mirror the same pair (orange tint for
plan turns, blue accent tint for act turns) so bubble and
button colors agree. Submitted requests carry the visible
mode as before. Verified: editor loads with zero script
errors.



Four fixes from hands-on use:

1. **MAX_STEPS 12 -> 30**, now owned by `config/settings.py`
   (complex multi-node tasks routinely exceeded the old
   per-turn cap).
2. **save_scene discipline**: the catalog entry now forbids
   saving after each mutation - save only when the user
   asks, as ONE save at the end of a turn whose mutations
   are all complete, or when a following action requires
   it. Live validation: a 3-create_node turn produced
   exactly one end-of-turn save (previously one per
   mutation).
3. **File placement**: `create_script`/`create_scene`/
   `create_resource` results now carry a
   `root_directory_hint` flag plus an explanatory message
   when the file lands in the project root (legal - bridge
   scripts live there - but flagged so the model
   course-corrects), and the catalog instructs matching the
   project's folder conventions via list_project_files.
4. **Plan/Act modes**: each turn carries a user-chosen mode.
   Bridge mode: the panel's Plan toggle rides the input
   queue (`POST /agent_input {"text", "mode"}`); stdin mode:
   a leading `/plan ` prefix. `mode_directive()` injects the
   per-turn instruction block into the turn message, and
   the loop REFUSES mutations deterministically in plan
   mode (single actions AND batches containing any
   mutation): structured refusal + conversation feedback +
   plan_mode_refusal UI event, never executed. Read-only
   inspections stay allowed; the expected plan-turn outcome
   is the workflow via final_answer. The Chat transcript
   tags plan turns (amber bubble + PLAN tag). The user
   switches to Act and asks the agent to carry the plan
   out; the plan persists in conversation history.

Validation (isolated editor + bridge-mode agent): plan turn
(0 mutations, concrete workflow as final_answer) followed by
an act turn that executed exactly that plan - 3 create_node
mutations, all verified, one end-of-turn save. Note: the
throwaway copies inherit zenpieV's in-progress scene whose
referenced scripts are mid-rename, so validation used a
minimal self-contained probe scene. Python 375 passed (+7:
mode parsing, mode directives, violation semantics,
MAX_STEPS settings ownership); store harness covers mode
through the queue and chat.



Four changes after hands-on use of the control phase:

1. **Right side dock removed entirely** (file deleted,
   plugin wiring reverted) — the bottom panel is the only
   UI surface.
2. **The status pill is now a Button that acts as Start
   Session** while no agent process is running: it spawns
   the agent itself via `OS.create_process` running
   `cmd /c "cd /d <res://Python_Agent> && py -m agent.godot_agent"`
   with `AGENT_INPUT_MODE=bridge` and the matching
   `GODOT_BRIDGE_URL` in the inherited environment. The
   button shows STARTING... until the agent's
   session_started event lands (30 s retry timeout, spawn
   failure flips to needs_attention). While a session is
   live the same button is a plain status display
   (disabled). 4.7 note: `OS.create_process` has no
   console-hiding flag, so the agent runs in a visible
   console window that doubles as its live log; closing
   that window terminates the agent. Manual terminal
   launches keep working identically.
3. **Chat auto-scroll**: after every chat rebuild the
   scrollbar pins to the bottom one frame later (await
   process_frame; guarded for the not-in-tree setup path,
   which errored once in the live editor and is now
   guarded), so the thinking line and new answers are
   always visible.
4. **GROQ_MODEL moved to config/settings.py** (matching
   the other providers; groq_provider imports it), so the
   UI model list shows `openai/gpt-oss-120b (groq)`
   instead of the bare "groq" fallback.

Validation: editor loads with zero script errors; the exact
spawn command verified against a throwaway editor (with a
full Python_Agent copy) — session started, agent connected,
one turn consumed from the input queue and completed with
an answer in the Chat transcript. Python 366 passed; store
harness green.



## Scope

- **Chat input box (control phase)**: Chat is now the FIRST
  tab with an input bar (LineEdit + Send, Enter submits).
  Submissions POST to the new `POST /agent_input` route into a
  single-slot queue (newest wins; `queued` flag reports
  displacement; text restored to the box on transport failure).
  New `agent/bridge_input.py`: with `AGENT_INPUT_MODE=bridge`,
  `godot_agent`'s input indirection (`read_user_request()`)
  polls `GET /agent_input` (consume-on-read) instead of stdin —
  the agent becomes a persistent process; stdin CLI mode stays
  the default and is untouched (`/exit` typed in the panel
  keeps its CLI meaning via the same text path).
- **Model selector**: header + dock dropdown listing every
  provider's configured model (delivered in the
  `session_started` `available_models` field). Selections
  travel as `model_selected` events and apply to the NEXT
  turn: `ask_model` overrides BOTH provider and model via
  `ACTIVE_PROVIDER`/`ACTIVE_MODEL` (all adapters share the
  `(conversation, schema)` contract). Telemetry records and
  request_sent/model_response events carry the active model.
- **Side dock glance card** (`ui/ai_agent_dock.gd`,
  DOCK_SLOT_RIGHT_UL): compact mirror of the header (status
  pill with the same THINKING pulse, turn/step, model
  selector, token totals, latest activity line, connection
  dot) plus an Open-panel button wired to the
  add_control_to_bottom_panel toggle. Read-only by design;
  shares the panel's state store instance.
- **Connection dot**: `GET /agent_input` polls double as the
  agent-alive heartbeat (last_input_poll_ms). Green while
  polling, green while a turn is in flight (busy means the
  agent legitimately stopped polling — a real fix found
  during live validation), red when the idle heartbeat goes
  stale (>2.5 s), gray when the agent never polls (stdin
  mode). Port unification: the bridge port is a single
  BRIDGE_PORT constant in the plugin, flowed to the store so
  panel/dock POSTs can never drift from the server.

## Robustness fix found live

glm-4.7-flash returned a valid decision WITHOUT the mandatory
`reason` field, failing validation and terminating the session.
`normalize_agent_response` now deterministically injects a
placeholder ("(no reason provided by the model)") when `reason`
is missing/blank on a decision dict; every other missing field
still fails strict validation. Covered by two new unit tests.

## Tests

Python: 366 passed (+2 normalization-repair tests). Store
harness extended: input validation, consume-on-read
semantics, displacement flag, model_selected handling,
available_models delivery, selection persistence across
session_started, heartbeat/connected states.

## Live validation (isolated editor instance, port 8082)

- Agent launched with AGENT_INPUT_MODE=bridge (via
  `python -m agent.godot_agent`; direct-script invocation
  cannot resolve package imports — launch from Python_Agent).
- Turn driven entirely from the control channel: curl POST
  /agent_input -> agent consumed it, turn ran (thinking
  stream visible in chat, heartbeat connected while idle
  AND while busy), final answer in the Chat transcript.
- Provider switch proven live: model_selected
  (zai/glm-4.7-flash) + new turn -> log shows
  `provider=zai model=glm-4.7-flash`; one attempt hit a Z.ai
  429 (honest model_call_failed path), the retry succeeded
  and exercised the missing-reason repair end-to-end
  (placeholder injected, turn completed with the answer).
- Editor plugin loads with panel + dock, zero script errors.

## Status

Confirmed working. Python: 366 passed. The panel is now the
primary control surface; the CLI remains for stdin workflows.
Remaining control work: New Session button + context meter
(quota/context growth), approval gates.

# Architecture Hardening Program: HTTP v2, Verification Contract, Owner Preservation, Runtime Honesty, Control Phase, Checkpoints (2026-09-12)

## Scope

Seven batches implemented from the full-architecture audit
(two parallel line-by-line reviews of every Godot tool file
plus the Python layer). Registry: 67 -> 71 actions.

1. **HTTP bridge v2** (ai_agent_http.gd rewritten):
   Content-Length framing (multi-segment requests no longer
   truncated), 64 KiB header cap, 10 MiB body cap (413),
   10 s deadline (408), chunked writes with status checks,
   real status codes (200/400/404/413/408) with the JSON
   body shape unchanged, one-frame connection draining.
   Live-verified: 400 KB create_script body, 404/400/413
   statuses, Python urllib client compat.
2. **Verification contract**: delete_node verifies removal
   (verified_deleted/verified_absent); set_properties
   verifies EVERY property by read-back (actual_value +
   verified per property, success = all retained); save_scene
   trusts the editor Error return (mtime no longer
   load-bearing); instantiate_scene/open_scene return
   success=verified; create_resource verifies every property
   after reload and refuses read-only properties.
3. **Owner preservation**: delete/reparent no longer
   re-own to the edited scene root on undo/do - the original
   owner is captured and restored, so instance-internal
   nodes are not corrupted into edited-scene nodes.
4. **Serializer hardening**: null refused for non-NIL
   expected types; TYPE_OBJECT refused (use
   assign_resource_to_property); unknown expected types are
   structured failures instead of raw passthrough; strict
   float/int component coercion (no more zero-fabrication
   from "abc"); applied to Vector2/2i/3/3i/Color.
5. **Runtime honesty**: run_scene/stop_run bounded waits
   with success=verified (failed launches no longer report
   success); debugger capture cleared at each run boundary.
6. **Discoverability**: find_nodes/count_nodes gained
   include_subclasses (ClassDB.is_parent_class); find_nodes
   results bounded at 200 with total_matches/truncated;
   disconnect_signal accepts stale connections (signal or
   method no longer exists); set_project_settings whitelists
   known keys; create/rename/duplicate validate names
   strictly (no null/empty); get_scene_dependencies reports
   every user of a resource.
7. **Control + safety**: checkpoint_create/list/restore
   (project text files into res://.agent_checkpoints/<id>,
   restore verified by read-back); run_project_tests (runs
   every headless harness, structured summary); approval
   gates (AGENT_APPROVAL_MODE=mutations; mutations pause in
   execute_single_action and poll GET /agent_approval; the
   panel renders Approve/Deny); New Session button (queues
   /exit, respawns on session_ended); context meter (prompt
   tokens vs CONTEXT_LIMIT_TOKENS); FIFO input queue (5);
   uniform transient provider retry (429/5xx, one retry);
   configurable bridge timeout; catalog-sync tests (registry
   actions must appear in the system prompt).

## Tests

Python 377 passed. Harnesses: all green including new
FIFO/mode cases in the store harness and root-hint cases in
script_tools_harness. Rule 12 smoke passed for the
include_subclasses schema change. Live validation on isolated
instances: checkpoint create/restore (85 files), approval
flow, context meter.

## Known limitations (honest)

- checkpoint_restore can fail with a Windows sharing
  violation on files the running editor holds open
  (observed: godot_bridge.gd); the tool reports the failure
  and the files restored so far. Full restores are most
  reliable with the editor closed.
- Piped-stdin agent runs hit PEP 479 RuntimeError at EOF
  (test artifact; interactive EOF is correct).
- get_undo_history_summary_harness.gd never quits headless
  (pre-existing; skipped in batch runs).

# Resource File Management Actions + Model Selection Passthrough (2026-09-12)

## Scope

zenpieV reported the agent apparently losing session memory: it created
capsule_shape.tres, "moved" it by creating a duplicate inside resources/,
then three times failed to act on "delete the older file you created" /
"delete it" with clarification-asking answers.

Diagnosis (evidence-backed, memory NOT broken):

- Telemetry shows input tokens growing monotonically across turns
  (6,731 -> 9,522 over five turns in one process that lived ~10 h), so
  the full conversation is sent on every model call.
- A live reproduction through the real Gemini adapter (exact message
  templates, real system prompt, real result payloads) showed the model
  correctly resolving "the older file you created" to
  res://capsule_shape.tres in 3/3 attempts - then hallucinating
  find_replace_across_files with empty strings, or admitting "no file
  deletion tool exposed".
- Root cause: the registry had no file-management capability. No way to
  delete, move, or rename resource files, and no explicit create-
  directory action. A flash-tier model covers a missing capability with
  clarification questions, which reads as amnesia.

Fixes implemented:

1. Three new actions (registry now 74): delete_resource (.tres/.res
   only; verified_absent read-back; "resource not found" on repeat),
   rename_resource (move/rename via DirAccess.rename_absolute;
   destination never overwritten; missing destination folders created;
   verified_destination_exists + verified_source_absent; references NOT
   rewritten - stated in the result), create_directory (fails when the
   path already exists as folder or file; verified_created). All three
   are batchable mutations with boundary fingerprints and mutation
   targets (delete_resource/rename_resource target the source path,
   like rename_script). All report undoable:false.
2. Prompt-side capability honesty: a "File mutation limits" section in
   the system prompt lists exactly which file operations exist and
   states that scenes/scripts/imports/project.godot can never be
   deleted/moved/renamed and nothing is ever overwritten; plus a rule
   that when no registered action fits, the model must return
   final_answer stating the limitation instead of inventing parameters.
   The validation-reject result message carries the same instruction.
3. Model selector passthrough (regression fix): ask_model computed
   ACTIVE_MODEL but only used it for telemetry; every adapter hardcoded
   its settings model, so the panel dropdown changed the label, not the
   API call. All five adapters now accept model=None and fall back to
   their settings default; ask_model passes the selected model through.

## Tests

Python 385 passed (new: file-op registry/schema/dispatch/batchable
tests, gemini+groq model-override adapter tests, ask_model selection +
settings-fallback tests). Harnesses 22/22 green including new file-op
cases in property_tools_harness (create_directory, create_resource
fixture, rename into missing nested folder, verified delete, duplicate/
traversal/wrong-extension rejections, FS cleanup).

## Live validation (isolated editor instance, port 8082)

- Route battery via curl: 8/8 expected outcomes (create, duplicate
  refusal, rename+auto-parent, verified delete, not-found repeat,
  project.godot extension rejection, traversal, missing-source rename).
- Rule 12 smoke: gemini-3.5-flash-lite accepted the converted schema
  with the three new unions and returned a valid delete_resource
  decision.
- Full agent scenario in bridge mode (real model): turn 1 created a
  resource; turn 2 "put this file in a /livecheck_resources folder"
  executed create_directory + rename_resource (folder created, file
  MOVED, no duplicate - the exact step that used to duplicate); turn 3
  "delete the resource file you created" executed delete_resource
  verified. Mutation ledger: 4/4 verified. Final answer named the exact
  path.

## Status

Implemented and validated; the "amnesia" report is closed as a missing
capability, not a context bug.
