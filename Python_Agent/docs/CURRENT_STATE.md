# Current Project State

## Purpose of This File

This document records the current, dynamic state of the Godot AI Agent project.

Update this file after meaningful implementation milestones, architectural changes, successful tests, major failures, or changes to the immediate development focus.

Do not treat this file as permanent architecture documentation.

For stable architecture, see:

* `AGENTS.md`
* `.agentrules/01-DEVELOPMENT_RULES.md`
* `.agentrules/02-PROJECT_ARCHITECTURE.md`

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

1. Stabilize tool semantics. (largely done: bounded batches, two-tier batch boundary)
2. Reduce unnecessary model retries.
3. Improve deterministic validation and constraint handling.
4. Establish a clean provider abstraction. (done: five provider adapters — Gemini, Groq, Ollama, OpenRouter, Z.ai — plus provider contract tests)
5. Add Groq alongside Gemini and Ollama. (adapter implemented; live end-to-end validation still pending)
6. Continue expanding Godot editor operations incrementally.

With the provider abstraction, persistent sessions, agent-controlled
session termination, and Observability v1 telemetry in place, the
project is entering an **Advanced Tools Expansion** phase focused on
broadening editor operations and completing provider parity validation.

## Inspection Tools Milestone

The inspection surface is now complete at 17/17 tools:

1. `get_scene_tree`
2. `find_nodes`
3. `get_node_properties`
4. `get_node_property`
5. `validate_node_type`
6. `list_available_node_types`
7. `get_node_class_info`
8. `list_node_signals`
9. `list_node_groups`
10. `count_nodes`
11. `find_nodes_by_script`
12. `find_nodes_by_group`
13. `get_project_settings`
14. `list_autoloads`
15. `get_editor_state`
16. `list_scenes_in_project`
17. `get_undo_history_summary`

The final four are read-only and batchable. `list_autoloads` reads live
`ProjectSettings`; the other three use editor-owned APIs injected by the
plugin (`EditorInterface`, `EditorFileSystem`, and
`EditorUndoRedoManager`). Normal headless scripts explicitly report editor
state, filesystem, and undo-manager unavailability instead of fabricating
values. Full editor-backed smoke validation requires an editor process with
the plugin bridge available.

Mutation tools are no longer a future milestone: the mutation
architecture landed with `create_node` … `remove_from_group` and is
now extended by the signal-connection tools below. Screenshot support
also remains deferred.

---

# Signal Connection Tools Milestone (2026-09-09)

Three tools covering live signal-connection state were implemented
end-to-end, following the add/remove-from-group pattern exactly:

* `list_node_connections` (read-only) — live incoming/outgoing
  connections of one node from real reflection
  (`get_incoming_connections`, `get_signal_connection_list`), with
  deterministic sorting and per-connection flags (`deferred`,
  `persistent`, `one_shot`). Editor-internal connections whose peer
  lies outside the edited scene (e.g. `SceneTreeEditor` hooks) are
  omitted from the entries and reported as
  `internal_connections_omitted`, preserving the scene-relative path
  contract without silently hiding data.
* `connect_signal` (mutation) — emitter node + signal -> receiver
  node + method, addressed exactly like the editor's Connect dialog;
  callable expressions and bound args deliberately unsupported.
  Validates `has_signal`/`has_method` before connecting; idempotent
  no-op when already connected; persistent (optionally deferred)
  single undoable `EditorUndoRedoManager` action; `verified_connection`
  read-back.
* `disconnect_signal` (mutation) — inverse operation; the undo
  restores the original connection flags; idempotent no-op when not
  connected (works even without the undo manager, since no change is
  made); `verified_connection` read-back.

Rule 12 handling: `ConnectSignalAction`/`DisconnectSignalAction` are
a structurally identical pair and are excluded from the Gemini
provider-only nested batch union (same precedent as
`AddToGroupAction`/`RemoveFromGroupAction`); both remain valid
top-level actions. `ListConnectionsAction` needed no exclusion.

Verified by: 258-passing Python suite (16 new/extended tests), the
`connect_disconnect_signal_harness.gd` headless harness, a 14-case
live bridge validation against a headless editor with the plugin
(isolated instance; the user's editor keeps the previously loaded
plugin build), and a live Gemini schema smoke test on
`gemini-3.1-flash-lite` (three scenarios, zero 400s). See
`docs/TEST_HISTORY.md`.

---

# Script Tools Milestone Phase A (2026-09-09)

Five tools covering script creation, attachment, and inspection —
the agent's entry point into code-producing tasks:

* `create_script` (mutation) — writes a new `.gd` file with full
  content. **The agent's first non-undoable real mutation**
  (`undoable: false`), verified by read-back (`verified_write`).
  Parse-gated BEFORE writing (fresh `GDScript` parse): unparseable
  content is never written, so the agent cannot create an
  unfixable broken file. Existing files are never overwritten;
  missing parent directories are created.
* `attach_script` (mutation) — node-scoped, undoable
  `EditorUndoRedoManager` property action; idempotent when the
  same script is attached; deterministic refusal when a different
  script is attached ("detach first"); `verified_attachment`
  read-back.
* `detach_script` (mutation) — undo restores the previous script;
  idempotent no-op works without the undo manager;
  `verified_attachment` read-back.
* `get_script_content` (read) — full source of a script file from
  disk.
* `list_script_diagnostics` (read) — fresh parse-check reporting
  `parse_ok` plus the Godot error string; works headless (an
  improvement over the originally planned live-editor-only
  diagnostics).

Godot side lives in a new `ai_agent_script_tools.gd`
(`AIAgentScriptTools`), wired through the router as a fourth tool
domain; the plugin instantiates and injects it. Rule 12: no
Gemini nested-batch exclusions were needed — the structural
analysis (identical required sets only against tolerated
precedents: `delete_node`/{node_path}, `find_nodes_by_script`/
{script_path}) was confirmed by the live smoke test.

Verified by: 280-passing Python suite (+22 tests), the
self-cleaning `script_tools_harness.gd` headless harness, an
18-case live bridge validation (isolated instance), and a live
Gemini smoke test including a realistic multi-line GDScript
content round-trip (the batch's new failure surface). See
`docs/TEST_HISTORY.md`.

---

# Three-Batch Expansion: Script Phase B, Scene Files, Project Introspection (2026-09-10)

Eighteen tools implemented in one session across three planned
batches, bringing the registry to **56 actions** (33 read-only,
20 mutations, 3 meta):

**Batch 1 — script Phase B + documentation (4 tools).**
`edit_script` (whole-file replacement, parse-gated before write,
never creates) and `replace_in_script` (deterministic anchored
edit: exactly-once anchor, already-applied no-op detection,
ambiguous anchors refused) close the code-repair loop; both are
non-undoable file mutations with `verified_write` read-back.
`get_class_documentation` and `search_documentation` are the
project's first Python-side tools (no bridge call): they serve the
version-pinned bundled class reference
(`data/godot_docs_4.7.2.json.gz`, built by
`scripts/prepare_godot_docs.py`; rationale in
`MODEL_KNOWLEDGE_DRIFT.md`).

**Batch 2 — scene file operations (6 tools, new Godot domain
`ai_agent_scene_file_tools.gd`).** `save_scene` (durability:
persists the edited scene; verified by modification-time
comparison), `create_scene` (new file, never overwrites,
deliberately does NOT open the scene, root type validated against
ClassDB), `instantiate_scene` (undoable instancing with
`verified_instance` read-back), `get_scene_dependencies`
(structured sub-scene/resource deps from PackedScene state, never
text parsing), `get_scene_tree_of` (any scene's tree without
opening it), `list_open_scenes` (editor-only).

**Batch 3 — property introspection and project awareness (8
tools).** `get_property_info` (type/hint/default/current for one
property — directly targets the malformed-parameter failure
mode), `get_node_children_summary` (bounded lightweight child
listing), `assign_resource_to_property` (undoable resource
assignment with path-verified read-back), `get_resource_info`,
`list_project_files` and `search_in_files` (bounded DirAccess
project inspection excluding `.godot`/`.git`),
`get_global_class_list` (reads the editor's own global-class
cache; ScriptServer is not exposed to GDScript), `get_input_map`.

Rule 12: `EditScriptAction` is structurally identical to
`CreateScriptAction`, so both are excluded from the Gemini
provider-only nested batch union; every other new action follows
tolerated live-validated precedents. Live smoke passed (zero 400s,
five scenarios).

Live validation found and fixed two real bugs: a crash on
`local_to_scene` for resource subclasses that do not expose it
(`CompressedTexture2D`), and integral JSON numbers decoding as
floats in GDScript (strict `TYPE_INT` limit checks rejected valid
limits; both limits now coerce). Both re-verified live.

Verified by: **330-passing** Python suite (+50 tests), four green
headless harnesses (script/scene-file/property/project-inspection,
all self-cleaning where applicable), and a 20-case live bridge
validation on an isolated editor instance — including end-to-end
persistence proof: create scene → instantiate into the edited
scene → attach script → `save_scene` → `get_scene_tree_of` on the
saved file shows the instanced child. See `docs/TEST_HISTORY.md`.

---

# Autonomy Milestone: Runtime Loop, Scene Navigation, Project Configuration (2026-09-10)

Eight more tools plus two agent-infrastructure features, completing
the structurally possible tool surface (vision and editor UI remain
out of scope). Registry grows to **64 actions** (38 read-only,
23 mutations, 3 meta).

**The playtest loop (4 tools).** `run_scene` (editor play of the
main or a custom scene, verified via `is_playing_scene`),
`stop_run` (idempotent stop, verified),
`get_runtime_output` (debugger-capture buffer), and — the
cornerstone — `run_scene_offline` (Python-side tool): runs a scene
as a headless subprocess via the configured engine binary and
returns exit code, stdout, stderr, and a
`script_errors_detected` flag with a bounded timeout. The offline
runner exists because of a verified engine limitation: Godot's
built-in debugger consumes a game's output/error messages before
editor debugger plugins can see them, so editor-side output
capture is impossible; owning the subprocess makes the output
fully readable. This closes the autonomous edit → run → fix loop.

**Scene navigation and configuration (4 tools).** `open_scene`
(edited-scene switch with an unsaved-changes guard and explicit
context-switch warning), `save_scene_as` (new-path save-as,
void-returning API verified by read-back), `set_project_settings`
(1-10 typed settings per call, sensitive keys rejected, previous
values reported for manual revert, read-back verified),
`create_resource` (file-backed `.tres` creation with
ClassDB-validated Resource types and explicit unknown-property
rejection).

**Agent infrastructure.** Telemetry JSONL export
(ROADMAP Phase 5 deferred item): a terminated session persists its
model calls, tool actions, batches, mutations, compactions, and
summary to `logs/telemetry/<session_id>.jsonl` — best-effort,
never breaking termination. The documented empty-input silent
termination gap is fixed (now logged with a reason).

The debugger capture (`ai_agent_debugger_capture.gd`, registered
via `EditorPlugin.add_debugger_plugin`) buffers custom-capture
messages per the engine limitation above and gives the plugin a
runtime-integration point for future in-game instrumentation.

Rule 12: all eight new actions follow tolerated live-validated
schema precedents (no-field family: run_scene/stop_run;
{scene_path} family: open_scene/save_scene_as; unique sets:
get_runtime_output/set_project_settings/create_resource/
run_scene_offline). No exclusions needed.

Verified by: **348-passing** Python suite (+18 tests), six green
headless harnesses (new: runtime/project/resource harness), and
live validation on an isolated editor instance: the full
autonomous pipeline (open scene → attach script → run → script
self-quits), save-as, settings mutation with previous-value
reporting, resource creation + inspection, and the offline runner
capturing both print output and push_error backtraces from a real
subprocess run.

---

# Lint + Refactoring + Token Compaction Batch (2026-09-11)

Three batches as one change set. Registry grows to **67 actions**
(40 read-only, 24 mutations, 3 meta). See `docs/TEST_HISTORY.md`
for the full verified record, including three engine quirks found
during live validation.

**Project lint (1 read-only tool).** `scan_project_issues`
(editor tools domain): bounded scan for script_parse_error,
scene_load_failed, and missing_dependency with prefix/limit
bounds, a 500-file scan cap, and explicit truncated metadata.
Parse-error reporting requires double evidence (fresh detached
parse fails AND the editor's own load rejects the file) because
a fresh parse of a class_name-bearing script inside the running
editor fails spuriously on duplicate global-class registration.

**Project refactoring (2 mutations, NEW fifth tool domain
`ai_agent_refactor_tools.gd`).** `rename_script` moves a .gd
file (+ .uid sidecar) and rewrites every textual res:// path
reference across .gd/.tscn/.tres/.cfg/project.godot in one
phased, parse-gated operation: references computed first, the
file moved second (preload() resolves at parse time), affected
scripts parse-checked third (regression-only gate), writes
verified by read-back, rollback on any parse regression, final
re-scan proves zero leftover references, and stale live nodes in
the edited scene are reported. `find_replace_across_files`
applies one exact replacement across a bounded file set
(max_files refuses over-bound requests entirely), with the same
regression-only parse gate and exact-computed-content read-back
verification (not a substring check — "Node" → "Node2D" would
false-alarm otherwise). Both are file-level operations and
report `undoable: false`.

**Token compaction (optional parameters, backward compatible).**
`get_script_content` gained start_line/line_count paging (1-500)
with total_lines/end_line/truncated; `get_scene_tree` and
`get_scene_tree_of` gained max_depth (1-50) with
children_truncated node markers and a top-level truncated flag
(POST /scene_tree route added; GET retained);
`get_node_properties` gained a property_names filter (≤ 50
names, missing names reported as not_found); `run_scene_offline`
gained max_output_chars (500-50000, default 8000, tail kept).
Python-side conversation compaction gained dedicated summaries
for paged script reads and filtered property reads. The design
goal holds: bounded output never blocks reasoning, because the
full-fidelity path remains available and the summaries say what
to re-request.

Rule 12: live Gemini smoke passed 4/4 scenarios with zero 400s
(scan_project_issues, rename_script, find_replace_across_files,
paged get_script_content). Verified by **358-passing** Python
suite (+10 tests), 21 green headless harnesses (new:
refactor_tools_harness, scan_project_issues_harness;
script_tools_harness extended with paging cases), and live
bridge validation on an isolated port-8082 editor instance.

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

Detailed implementation notes are superseded by the feature sections below and by `docs/TEST_HISTORY.md`.

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
| `move_child` | `node_path`, `new_index` |
| `add_to_group` | `node_path`, `group_name` |
| `remove_from_group` | `node_path`, `group_name` |
| `connect_signal` | `node_path`, `signal_name`, `target_path`, `method_name`, `deferred` |
| `disconnect_signal` | `node_path`, `signal_name`, `target_path`, `method_name` |
| `create_script` | `script_path`, `content` |
| `attach_script` | `node_path`, `script_path` |
| `detach_script` | `node_path` |

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
| `move_child` | `node_path` | The child being reordered |
| `add_to_group` | `node_path` | The node whose membership changes |
| `remove_from_group` | `node_path` | The node whose membership changes |
| `connect_signal` | `node_path`, `signal_name`, `target_path`, `method_name` | The full connection identity; `deferred` is result state, so toggling it cannot bypass |
| `disconnect_signal` | `node_path`, `signal_name`, `target_path`, `method_name` | The full connection identity |
| `create_script` | `script_path` | The script file being created (project-level resource) |
| `attach_script` | `node_path` | The node's script attachment (script change cannot bypass) |
| `detach_script` | `node_path` | The node's script attachment |

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

# Bug Fix: Premature `exit_session` (Part 1: deterministic guard)

A live stress test exposed a control-flow bug: for the request
`delete omnitrix and end session`, Gemini returned only `exit_session`
with `"Deleted 'Omnitrix' node and terminating the session as
requested."` — no `delete_node` action was ever executed, and the
session terminated anyway.

## Root cause

The main loop honored `exit_session` unconditionally. Because
`exit_session` terminates the session, its free-text `exit_summary`
was effectively treated as evidence that requested work had been done,
letting the model substitute a bare exit for unperformed mutations.

## Fix

A deterministic Python-side guard in the main loop
(`agent/godot_agent.py`):

- The loop tracks how many tool actions were executed in the current
  turn (`executed_tool_actions_this_turn`, reset at each turn start).
- `exit_session` is honored only after at least one tool action has
  actually executed in the current turn
  (`exit_session_is_allowed()`).
- When `exit_session` is proposed with zero executed tool actions,
  the session is NOT terminated. The decision is rejected with a
  tool-result-shaped observation
  (`build_premature_exit_session_result()`), logged, appended to
  conversation history like a validation failure, and the model is
  asked to perform the requested work first (or reply with
  `final_answer` and tell the user to type `/exit`).

`/exit` remains the human-controlled host-level termination path and
is unchanged. `exit_session` remains fully usable after real work has
executed in the same turn.

## Regression Tests

- `test_exit_session_cannot_substitute_for_unexecuted_mutation` —
  the exact live failure shape is rejected, never dispatches
  `delete_node`, and the session stays open.
- `test_valid_delete_node_then_exit_session_still_works` — a real
  `delete_node` followed by `exit_session` still works.
- `test_prompt_requires_work_before_exit_session` — the system prompt
  requires requested work to be executed before `exit_session` and
  forbids claiming unexecuted actions.

## Remaining limitation

The guard is a deterministically detectable invariant (at least one
tool action executed in the current turn). It cannot prove that a
multi-step user request is fully complete: a model could still perform
only part of the work (or perform unrelated work), then legitimately
terminate. Detecting true request completeness would require a
natural-language intent parser, which is intentionally out of scope.
The system prompt therefore also requires the model to execute all
requested actions before `exit_session` and to never claim in
`exit_summary` that any action was performed without a tool result
proving it.

---

# Feature: Observability v1 Telemetry

Observability v1 adds structured, in-memory session telemetry without
changing agent behavior, `AgentDecision` schemas, tool semantics, or
the HTTP protocol.

## Implementation

- `agent/telemetry.py` (new): the telemetry model and collector. It is
  deliberately free of logging, Godot, and provider-SDK dependencies.
- `agent/godot_agent.py`: the agent loop records telemetry at each
  instrumentation point and attaches a `SessionObservability` instance
  to the persistent `AgentSession`.

## Core telemetry model

- `TokenUsage`: normalized token counts from a single model call.
  Values come only from provider usage metadata; when a provider
  exposes no usage metadata, all fields are `None` and `available` is
  `False`. Token counts are never estimated or fabricated.
- `normalize_usage(metadata)`: maps provider-specific usage fields to
  `input_tokens` / `output_tokens` / `total_tokens`. Recognized
  aliases include Gemini (`prompt_token_count`,
  `candidates_token_count`, `total_token_count`), OpenAI-compatible
  APIs (`prompt_tokens`, `completion_tokens`, `total_tokens`), and
  Ollama (`eval_count`).
- `ProviderResult`: the return envelope for provider adapters,
  wrapping the raw response text plus normalized `TokenUsage` so the
  agent loop can record telemetry without re-parsing SDK objects.
- `safe_error_message(error)`: truncates error text to 200 characters
  and redacts `GEMINI_API_KEY`, `GROQ_API_KEY`, and
  `OPENROUTER_API_KEY` values before the message is recorded.

## Recorded events

`SessionObservability` (keyed by session ID) collects:

- Model calls (`record_model_call`): call ID, turn/step numbers,
  provider, model, duration, usage, success/failure, and a safe error
  message on failure. Recorded for every provider invocation,
  including failures.
- Tool actions (`record_tool_action`): turn/step, action type,
  success, duration, and the originating model-call ID. Recorded for
  single actions, batch items, validation rejections, and
  batch-boundary rejections.
- Batches (`record_batch`): batch size, succeeded/failed counts,
  `stopped_early`, `stopped_at_index`, duration, and overall success.
- Compactions (`record_compaction`): turn/step, original vs. summary
  length, the triggering action, and duration.

## Session summary

When `AgentSession.terminate()` runs, `get_summary()` aggregates the
recorded events into a `SessionSummary`: turns completed, distinct
agent steps, model calls, token totals, action success/failure counts,
batch counts, compaction count, wall duration, and the termination
reason. The summary is logged as `"Session summary: ..."`. When usage
metadata is missing for some calls, `usage_unavailable_count` is
nonzero and `total_tokens_complete` is `False` rather than the totals
being guessed.

## Backward compatibility

- No changes to `AgentDecision` schemas or tool semantics.
- Provider adapters now return `ProviderResult`; the agent-facing
  `ask_model()` still returns the model text as a string.
- Future consumers (JSONL export, Godot UI, cost analysis) are
  explicitly deferred and are not built in this milestone.

---

# Feature: Tool Expansion V2 - validate_node_type

The first Tool Expansion V2 tool adds a read-only, Godot-side
pre-flight check for node type names.

## Behavior

- Decision:
  `{"action": "validate_node_type", "reason": "...", "node_type": "..."}`.
- The Godot bridge answers from the running editor's `ClassDB`
  (`addons/Execution_Agent/scene/ai_agent_node_tools.gd`,
  `validate_node_type_from_request()`). The type is `valid` only
  if it exists as a registered class, inherits from `Node`, and
  can be instantiated directly; abstract bases such as
  `CanvasItem` and non-Node classes such as `Resource` are
  reported as not valid for node creation.
- Result: `success`, `action`, `node_type` (trimmed), `valid`,
  `exists`, `is_node_class`, `can_instantiate`, `parent_class`,
  and `message`. Read-only: no scene access, no undo/redo
  involvement.
- Registered in `agent/registry.py` as read-only and batchable;
  routed at `/validate_node_type` through the standard bridge
  router.
- Verified against live Godot 4.7.2 headless (8/8 cases passed:
  valid type, abstract base, non-Node class, unknown class,
  whitespace-only, missing key, `Node` itself, whitespace
  trimming).

## Not covered

- Script-defined (`class_name`) custom types: `ClassDB` covers
  native classes only. Script-class validation is future work.

---

# Advanced Tool: `list_available_node_types`

`list_available_node_types` is a read-only ClassDB discovery tool for
finding native, instantiable Godot `Node` classes before selecting an
exact candidate for `validate_node_type` and, eventually, `create_node`.

## Contract

- Optional filters: `inherits_from` (a registered `Node` class) and
  case-insensitive `name_contains`.
- Optional `limit`: 1–100; the default is 50. Unfiltered requests are
  allowed but are still bounded.
- Results contain only sorted class names that inherit from `Node` and
  can be instantiated. They include `total_matches` and `truncated`, so
  a bounded result is never presented as an exhaustive list.
- Invalid or non-Node `inherits_from`, blank supplied filters, and an
  invalid limit return the standard structured failure form. No match is
  a successful result with `total_matches: 0` and an empty `node_types`
  list.
- It is registered as read-only and batchable, matching the existing
  policy for inspection actions. It has no scene, undo/redo, telemetry,
  or interrupted-batch-boundary side effects.

## Deliberate boundary

This is candidate discovery, not an arbitrary ClassDB metadata dump.
It exposes no methods, signals, properties, documentation, or parent
metadata. `validate_node_type` remains the exact pre-flight check for a
chosen candidate and `create_node` remains the only creation operation.

---

# Feature: `find_nodes_by_group` Action

`find_nodes_by_group` is a read-only inspection action that returns
the nodes in the currently edited scene that are members of the
requested group, answered from each node's live group state
(`Node.is_in_group()`).

## Contract

- Required field: `group_name` (str, non-empty). Matching is exact and
  case-sensitive, preserving Godot's group-name identity. No fuzzy,
  case-insensitive, wildcard, or regex matching.
- Implemented by the shared `collect_matching_nodes` traversal used by
  `find_nodes`/`find_nodes_by_script` (extended with an optional group
  filter that defaults off), so traversal order and the node result
  shape (`name`, `node_type`, `path`, `is_root`) are identical to
  `find_nodes`. Returns `group_name`, `count`, and `nodes`; zero
  matches are a successful empty result.
- Missing/blank `group_name` returns the standard structured failure
  form, passed through to the agent unchanged.
- Registered in `agent/registry.py` as read-only and batchable; it is
  not in `agent/boundary.py` mutation-target tracking. Routed at
  `/find_nodes_by_group` through the standard bridge router.

## Deliberate boundary

This is group-membership inspection only: no group creation/removal,
no project-wide group discovery, no multi-group boolean expressions,
no group metadata, and no mutation of membership.

---

# Feature: `find_nodes_by_script` Action

`find_nodes_by_script` is a read-only inspection action that returns
the nodes in the currently edited scene whose attached script matches
the requested script resource path, answered from each node's live
`Node.get_script()` state.

## Contract

- Required field: `script_path` (str, non-empty). Matching is against
  the canonical `res://` resource path of the attached script;
  requests without the prefix are deterministically normalized by
  prepending `res://`. Matching is exact; no fuzzy matching, regex,
  or filesystem scanning.
- Implemented by the shared `collect_matching_nodes` traversal used by
  `find_nodes` (extended with an optional script filter that defaults
  off), so traversal order and the node result shape
  (`name`, `node_type`, `path`, `is_root`) are identical to
  `find_nodes`. Returns `script_path` (normalized), `count`, and
  `nodes`; zero matches are a successful empty result.
- Missing/blank `script_path` returns the standard structured failure
  form, passed through to the agent unchanged.
- Registered in `agent/registry.py` as read-only and batchable; it is
  not in `agent/boundary.py` mutation-target tracking. Routed at
  `/find_nodes_by_script` through the standard bridge router.

## Deliberate boundary

This is script-attachment inspection only. No script editing, no
inheritance analysis, no project-wide script discovery, and no
mutation of attachments.

---

# Feature: `count_nodes` Action

`count_nodes` is a read-only aggregate inspection action that counts
nodes in the currently edited scene matching the same filter semantics
as `find_nodes`, returning only the count. It supports deterministic
aggregate verification ("how many enemies exist?") without retrieving
node lists.

## Contract

- Optional filters, identical to `find_nodes`: `node_name`, `node_type`
  (exact `get_class()` equality), `parent_path` (count this node's
  subtree; must exist), and `name_match` (`exact` default, `contains`,
  `starts_with`, `ends_with`, case-insensitive). No `include_root`
  field; the scene root itself is never counted.
- Implemented Godot-side by the shared `_parse_find_node_filters` +
  `collect_matching_nodes` machinery used by `find_nodes`, so the two
  tools cannot drift; `find_nodes` behavior is unchanged.
- Success returns `count` (the established field name, matching
  `find_nodes`), the applied filters, and never a node list. Zero
  matches is a successful `count: 0`. Invalid `name_match` and missing
  parents return the existing structured failures.
- Registered in `agent/registry.py` as read-only and batchable; it is
  not in `agent/boundary.py` mutation-target tracking. Routed at
  `/count_nodes` through the standard bridge router.

## Deliberate boundary

The tool only reports authoritative scene state. It is a primitive for
the observe → mutate → verify workflow; completion-declaration logic
lives elsewhere. No generic query language, no extra filters, no
screenshot or multimodal dependencies.


# Feature: `get_project_settings` Action

`get_project_settings` is a read-only project-configuration inspection
action that reads specific settings from the live Godot `ProjectSettings`
state. It never dumps the whole settings database: the agent must request
exact setting names and/or a bounded prefix.

## Contract

- Optional filters, at least one required: `setting_names` (exact keys,
  deduped, blanks dropped) and/or `prefix` (key begins-with, bounded).
  Both may be combined as additive filters.
- `limit` caps prefix results (1-100, default 50); exact-name matches are
  never removed by the limit.
- Implemented Godot-side from the live `ProjectSettings` runtime state
  (`ProjectSettings.has_setting()`, `get_setting()`, and
  `get_property_list()`); `project.godot` is never parsed manually.
- Exact missing keys are reported in `missing`, not treated as a request
  failure. Settings whose name contains a sensitive token (`password`,
  `token`, `secret`, `api_key`, `credential`, `private_key`) are excluded:
  only their names appear in `redacted`, never their values.
- Prefix results are lexicographically sorted and include `total_matches`,
  `returned_matches`, and `truncated` metadata.
- Values are serialized through the project's shared
  `ai_agent_variant_serializer.gd` to plain JSON-compatible values.
- Registered in `agent/registry.py` as read-only and batchable; it is not
  in `agent/boundary.py` mutation-target tracking. Routed at
  `/get_project_settings` through the standard bridge router.

## Deliberate boundary

Reads only live `ProjectSettings` state; no project-setting mutation is
provided. Sensitive-setting protection covers setting names only (values
are never exposed). It is the project-level counterpart to the structural
scene-inspection tools, not a bulk configuration dump. Completion-declaration
logic does not belong to this tool.

---

---

# Feature: `list_node_groups` Action

`list_node_groups` is a read-only inspection action that reports the
groups a single node in the currently edited scene is actually a member
of, answered from the node's real instance state (`Node.get_groups()`).

## Contract

- Required field: `node_path` (str, non-empty, editor-relative; `"."` is
  the scene root), resolved with the same helper as the other node
  inspection tools.
- The bridge returns `node_path`, `node_name`, `node_type`,
  `total_groups`, and a deterministic, alphabetically sorted `groups`
  list of plain strings. A node with no groups is a successful result
  with an empty list.
- Missing/blank `node_path` and nonexistent nodes return the standard
  structured failure form, passed through to the agent unchanged.
- Registered in `agent/registry.py` as read-only and batchable; it is
  not in `agent/boundary.py` mutation-target tracking and is safe to
  execute after an interrupted mutation batch. Routed at
  `/list_node_groups` through the standard bridge router.

## Deliberate boundary

This is group-membership inspection only: it does not scan the scene
tree, list project-wide groups, or expose group owners/definitions or
any mutation of membership.

---

# Feature: `list_node_signals` Action

`list_node_signals` is a read-only inspection action that lists the
signals actually available on one node in the currently edited scene,
answered from the node's real reflection data (`Node.get_signal_list()`),
including built-in and inherited signals.

## Contract

- Required field: `node_path` (str, non-empty, editor-relative; `"."` is
  the scene root), resolved with the same helper as the property tools.
- The bridge returns `node_path`, `node_name`, `node_type`,
  `total_signals`, and a deterministic, alphabetically sorted `signals`
  list; each signal carries `name` and JSON-safe `args` entries with
  `name`, `type`, and `type_id`.
- Missing/blank `node_path` and nonexistent nodes return the standard
  structured failure form, passed through to the agent unchanged.
- Registered in `agent/registry.py` as read-only and batchable; it is
  not in `agent/boundary.py` mutation-target tracking and is safe to
  execute after an interrupted mutation batch. Routed at
  `/list_node_signals` through the standard bridge router.

## Deliberate boundary

This is signal discovery only. It does not expose connection state,
method lists, or any mutation capability. The original roadmap draft
proposed an optional `include_connections` flag; it was intentionally
not implemented. The final request contract is `node_path` only and the
tool reports signal definitions, not connection state. Connection
inspection can be considered separately later if a demonstrated need
arises. This reduced contract is intentional, not a missing feature.

---

# Feature: Tooling V3 — `get_node_property` Action

A new `get_node_property` action reads a single, already-known
property of a single node, avoiding the overhead of re-requesting the
node's entire property list (`get_node_properties`) just to inspect one
value. It is the single-value counterpart to the multi-value inspector
and is read-only, batchable, and side-effect-free.

## Scope

- Required fields: `node_path` (str), `property_name` (str).
- Both must be non-empty after whitespace stripping; blank strings are
  rejected client-side before the bridge is called.
- `node_path` follows the same editor-relative conventions as
  `get_node_properties` (`"."` = the edited scene root).

## Provider contract

- Provider: Godot bridge
  (`agent/scene_tools.py` → `tools/scene_tools.py`
  → `AIAgentPropertyTools.get_node_property_from_request`).
- Success returns the resolved node name, node type, property type /
  type id, `editable` flag, and the property value serialized via
  `AIAgentVariantSerializer` into a JSON-compatible structure.
- Failures propagate the standard structured-failure form
  (`{"success": false, "error": "..."}`): node not found, unsupported
  property, and Python-side validation
  rejections. A bridge failure is returned to the agent unchanged (no
  exception wrapping, no partial execution).

## Implementation summary

- `agent/schemas.py`: `GetNodePropertyAction` (reason, node_path,
  property_name) added to the `AgentDecision` union and the
  `BatchableAction` union.
- `agent/godot_agent.py`: `ACTION_REQUIREMENTS`
  (`"get_node_property": ("node_path", "property_name")`); dispatch
  case routed to `scene_tools.get_node_property`; documented as item #5
  in the system-prompt action list (read-only).
- `agent/registry.py`: registered as read-only, batchable, routed at
  `/get_node_property` through the standard bridge router.
- `tools/scene_tools.py`: `get_node_property` endpoint.
- `addons/Execution_Agent/scene/ai_agent_property_tools.gd`:
  `get_node_property_from_request` Godot-side handler.

## Verification

- 8 new Python contract tests (validation, blank-field rejection,
  batch membership, success/failure passthrough).
- Verified against live Godot 4.7.2 headless (8/8 cases passed:
  read position of named node, read property of root node,
  nonexistent property, nonexistent node, missing `node_path`,
  missing `property_name`, blank `node_path`, blank `property_name`).

## Not covered

- No change to `get_node_properties` semantics; the two actions remain
  distinct. `get_node_property` additionally supports the special,
  scene-tree-visible `Node.name` attribute as a read-only value because
  Godot omits it from the editor-property enumeration. Node renames still
  use the dedicated undoable `rename_node` action.

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

## Gemini Response-Schema Compatibility Fix (Verified 2026-09-08)

Gemini 3.1 Flash Lite initially returned `400 INVALID_ARGUMENT` for every
agent request after the `count_nodes` action was added. The failure was not
the Godot bridge or the standalone action schema. It occurred because the
Gemini-normalized schema placed `CountNodesAction` inside the nested
`batch.actions` union, where its filter shape overlapped `FindNodesAction`
after Pydantic discriminator metadata was removed.

The Gemini adapter now keeps `count_nodes` available as a normal top-level
action but omits that branch from the provider-only nested batch union. The
public Pydantic schema, registry, bridge endpoint, and tool behavior are
unchanged. The provider adapter tests cover the normalized shape.

Live verification on 2026-09-08 succeeded for both a project-settings request
and a general tool-capabilities request using `gemini-3.1-flash-lite`.

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

Status update: Priorities 1 and 2 below are complete. Priority 3 is
partially complete (the Groq adapter is implemented and covered by
contract tests; live end-to-end validation is still pending). The
project is entering an Advanced Tools Expansion phase: broadening
Godot editor operations while completing provider parity validation.

## Priority 1: Inspect and Stabilize Current Agent Architecture (COMPLETED)

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

## Priority 2: Provider Abstraction (COMPLETED)

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

## Priority 3: Groq Integration (ADAPTER IMPLEMENTED; LIVE E2E VALIDATION PENDING)

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

# GIT INITIALIZED

Git version control initialized on 2026-09-06.

# Mutation Architecture (2026-09-08)

A minimal mutation architecture was added on the Python side. The
Godot side already executes all scene mutations
(create_node, rename_node, delete_node, reparent_node,
duplicate_node, set_properties, move_child) as editor-native,
undoable
`EditorUndoRedoManager` actions and reports `undoable` and
`verified_*` fields in its results; no Godot-side changes were
needed at the time. `move_child` was added later (see below).

# move_child Tool (2026-09-08)

The first real mutation tool built on top of the mutation
architecture, implemented end to end:

* Schema: `MoveChildAction` (`action`, `node_path`, `new_index`
  with `ge=0`), registered in `BatchableAction` and
  `AgentDecision`; registry entry with `required_fields=
  ("node_path",)` and `is_mutation=True`.
* Boundary: `move_child` uses fingerprint fields
  (`node_path`, `new_index`) and target field (`node_path`), so
  a skipped move blocks any automatic resume targeting the same
  node regardless of the requested index.
* Godot side (`move_child_from_request` in
  `ai_agent_node_tools.gd`, routed at `POST /move_child`):
  validates field presence/types, node existence, parent
  existence, and index range; handles already-at-index requests
  deterministically as a success with `moved: false` and no undo
  history; performs the move as one undoable
  `EditorUndoRedoManager` action; reads the real resulting index
  and sibling order back and reports `verified_index` /
  `verified_order`; reports explicit unavailable errors where the
  editor undo manager is absent (headless).
* Python side: `scene_tools.move_child()` posts to
  `/move_child`; results flow through the existing mutation
  contract (`verified_index`/`verified_order` are `verified_*`
  claims) and mutation telemetry on both standalone and batch
  paths.

# add_to_group / remove_from_group Tools (2026-09-08)

Group membership mutations built on the same mutation architecture:

* Schemas: `AddToGroupAction` and `RemoveFromGroupAction` (`action`,
  `node_path`, `group_name`), registered in `BatchableAction` and
  `AgentDecision`; registry entries with `required_fields=("node_path",
  "group_name")` and `is_mutation=True`.
* Boundary: both use fingerprint fields (`node_path`, `group_name`)
  and target field (`node_path`), so a skipped group mutation blocks
  any automatic resume targeting the same node regardless of the
  group name.
* Godot side (`add_to_group_from_request` /
  `remove_from_group_from_request` in `ai_agent_node_tools.gd`,
  routed at `POST /add_to_group` and `POST /remove_from_group`):
  validates field presence/types, node existence, and non-empty group
  name; handles idempotent cases (already a member / not a member)
  deterministically as successes with `changed: false` and no undo
  history; performs the change as one undoable
  `EditorUndoRedoManager` action; reads the real resulting membership
  back via `is_in_group` and reports `verified_membership`; reports
  explicit unavailable errors where the editor undo manager is absent
  (headless).
* Python side: `scene_tools.add_to_group()` /
  `scene_tools.remove_from_group()` post to the new endpoints;
  results flow through the existing mutation contract
  (`verified_membership` is a `verified_*` claim) and mutation
  telemetry on both standalone and batch paths.
* Verified live against a running editor bridge: add, idempotent
  add, remove, idempotent remove, missing node, and empty group name
  all returned the documented structured results.


* Verified live against a running editor bridge: real move,
  no-op, out-of-range index, and missing node all returned the
  documented structured results.


Python-side additions:

* `agent/mutation.py` - the single mutation contract layer:
  - `is_mutation_action()` classifies actions using the
    registry's authoritative `is_mutation` flag.
  - `validate_mutation_result()` enforces the structured result
    contract: a mutation result must be a dict with a boolean
    `success` key. Contract violations are recorded as failures,
    never as successes.
  - `classify_verification()` derives a verification status from
    the bridge's own `verified_*` claims: `verified` (success and
    all claims true), `unverified` (success, no claims), or
    `failed` (failure, or any claim false). Status is never
    fabricated.
  - `build_mutation_record()` produces a frozen `MutationRecord`
    per mutation execution carrying action, mutation target
    (from `agent/boundary.py`), success, verification status,
    editor-reported undoability, and error details.
* `agent/telemetry.py` - `MutationTelemetry` records plus
  `SessionObservability.record_mutation()` and mutation counts
  (`mutation_count`, `successful_mutation_count`,
  `failed_mutation_count`, `unverified_mutation_count`) in
  `SessionSummary`.
* `agent/godot_agent.py` - `execute_single_action()` now builds
  and records a `MutationRecord` for every mutation action, on
  both the standalone and batch paths, in addition to (not instead
  of) the existing `ToolActionTelemetry`. Tool results and tool
  behavior are unchanged.

Batch semantics, interrupted-batch blocking, batch limits, session
control, and all existing undo behavior are untouched. No new
mutation tools were added.

Current limitation: Python-side verification status reflects only
what the Godot bridge reports at mutation time; a "verified"
status is not a persistent guarantee of scene state.

---

# Gemini structured-output 400 regression: confirmed root cause (2026-09-09)

The two sections below titled "Gemini Schema Compatibility Fix for move_child" are a
historical record of the initial (superseded) hypothesis. They describe a `result_mode`
enum-injection workaround and an earlier live probe at
`gemini-2.5-flash-preview-09-2025` that are NOT the current explanation for the 400 and
are NOT the current fix.

Confirmed diagnosis (authoritative — matches the current implementation):

- The Gemini `400 INVALID_ARGUMENT` on the full `AgentDecision` schema was caused by
  provider-incompatible JSON-schema constraint keywords that Pydantic emits:
  `discriminator`, `minimum`, `maximum`, `minItems`, `maxItems`.
- `make_gemini_schema_compatible()` (in `models/gemini_provider.py`) is the permanent,
  provider-only fix. It normalizes the schema by recursively:
  - converting `oneOf` to `anyOf`,
  - removing `discriminator`,
  - removing `minimum`, `maximum`, `minItems`, and `maxItems`.
  Host-side Pydantic validation is unchanged and remains authoritative.
- The `result_mode` enum injection for `CountNodesAction` / `MoveChildAction` is a
  separate, still-present structural-uniqueness workaround. It is NOT the 400 fix.
- Current default model: `gemini-3.1-flash-lite` (`config/settings.py::GEMINI_MODEL`).
- The temporary probe `tmp_gemini_regression_probe.py` was removed after investigation.
- Regression coverage: the six permanent tests in `tests/test_gemini_provider.py`
  assert the recursive removal of `discriminator`, `minimum`, `maximum`, `minItems`,
  `maxItems`, including on the real `AgentDecision` schema.
- Provider suite (`tests/test_gemini_provider.py`, `tests/test_provider_adapters.py`,
  `tests/test_provider_contract.py`): 121 passing tests. Full Python suite: 242 passing.
- Live end-to-end validation with `gemini-3.1-flash-lite` passed all five scenarios
  (greeting, scene-tree inspection, `move_child`, a bounded batch, and a constrained
  `list_available_node_types`) with zero `400`s.

---

# Gemini Schema Compatibility Fix for move_child (2026-09-09)

## Problem

When `MoveChildAction` was added to the `AgentDecision` union in
`agent/schemas.py`, Gemini began rejecting the full schema request with
`400 INVALID_ARGUMENT`. The initial diagnosis by a prior agent concluded
the problem was structural overlap and added `MoveChildAction` to both
`GEMINI_NESTED_BATCH_EXCLUDED_ACTIONS` and `GEMINI_TOP_LEVEL_EXCLUDED_ACTIONS`
in `models/gemini_provider.py`. That removal was the wrong fix: it stripped
`MoveChildAction` entirely from Gemini's generated schema, so the system
prompt could still describe `move_child` as a tool while Gemini's
structured-output schema made it impossible for the model to select. The
practical symptom was that the agent repeatedly chose `set_properties` or
`rename_node` even when its own reasoning identified `move_child` as the
correct action.

## Investigation

Live A/B isolation was decisive: removing `MoveChildAction` from the Gemini
schema restored request acceptance, while removing the structurally-
overlapping group actions did not. Unlike `AddToGroupAction` /
`RemoveFromGroupAction`, which overlap each other, `MoveChildAction` was
the single action causing Gemini's union validator to reject the schema —
mirroring the earlier `CountNodesAction` failure pattern.

## Fix

Followed the proven `CountNodesAction` path: add a Gemini-only `result_mode`
enum injection in `make_gemini_schema_compatible()` so `MoveChildAction`
becomes structurally unique in the union, and remove it from both exclusion
sets so it flows into the top-level and nested-batch schemas. The public
Pydantic schema was intentionally left untouched (no `result_mode` field on
`MoveChildAction`); the Gemini transform injects `result_mode:
Literal["move_child"]` only in the converted schema Gemini sees. This keeps
`MoveChildAction` valid for Pydantic round-trip while making it
distinguishable from other union branches for Gemini.

## Result

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

## Live validation

A live Gemini schema probe was performed via the temporary
`tmp_gemini_regression_probe.py` script using the live Gemini API
(`models/gemini-2.5-flash-preview-09-2025`). Before the fix, a raw
`AgentDecision` schema produced `400 INVALID_ARGUMENT`. After the fix,
the same schema with the `result_mode` injection and exclusions removed
was accepted (`200 OK`). This confirms the fix resolves the structural
Gemini incompatibility without changing public schemas or tool semantics.

The probe was removed after validation. No `GEMINI_API_KEY` is committed
to the repo.

---

# Gemini Schema Compatibility Fix: move_child (2026-09-09)

## Problem

When `MoveChildAction` was added to the `AgentDecision` union, Gemini started rejecting
the full schema request with `400 INVALID_ARGUMENT`. The initial diagnosis by a prior
agent concluded the problem was structural overlap and added `MoveChildAction` to both
`GEMINI_NESTED_BATCH_EXCLUDED_ACTIONS` and `GEMINI_TOP_LEVEL_EXCLUDED_ACTIONS` in
`models/gemini_provider.py`. That removal was the wrong fix: it stripped
`MoveChildAction` entirely from Gemini's generated schema, so the system prompt could
still describe `move_child` as a tool while Gemini's structured-output schema made it
impossible for the model to select. The practical symptom was that the agent repeatedly
chose `set_properties` or `rename_node` even when its own reasoning identified
`move_child` as the correct action.

## Investigation

Live A/B isolation was decisive: removing `MoveChildAction` from the Gemini schema
restored request acceptance, while removing the structurally-overlapping group actions
did not. Unlike `AddToGroupAction`/`RemoveFromGroupAction`, which overlap each other,
`MoveChildAction` was the single action causing Gemini's union validator to reject the
schema — mirroring the earlier `CountNodesAction` failure pattern.

## Fix

Followed the proven `CountNodesAction` path: add a Gemini-only `result_mode` enum
injection in `make_gemini_schema_compatible()` so `MoveChildAction` becomes structurally
unique in the union, and remove it from both exclusion sets so it flows into the
top-level and nested-batch schemas. The public Pydantic schema was intentionally left
untouched (no `result_mode` field on `MoveChildAction`); the Gemini transform injects
`result_mode: Literal["move_child"]` only in the converted schema Gemini sees. This
keeps `MoveChildAction` valid for Pydantic round-trip while making it distinguishable
from other union branches for Gemini.

## Result

- `MoveChildAction` is now present in both the top-level `AgentDecision` union and the
  nested `batch.actions` union in the Gemini-generated schema.
- `AddToGroupAction` and `RemoveFromGroupAction` remain excluded from the nested
  batch union only (unchanged); they are still valid standalone actions and in the
  public Pyddc schema.
- `result_mode` appears in Gemini's view of `MoveChildAction` properties/required,
  matching the `CountNodesAction` pattern.
- No Godot code, mutation execution, registry semantics, batch behavior, or other
  providers were changed.
- All 8 provider adapter tests pass; full suite 236 passed.

