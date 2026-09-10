# FUTURE_TOOLS.md

## Purpose

This document has two jobs:

1. Record the **current tool inventory** of the agent, categorized.
2. Propose a **future tool set** for the "Advanced Tools Expansion" phase,
   informed by research into what autonomous Godot editor agents need to
   fulfill real user requests.

Relationship to other documents:

- `ROADMAP.md` describes direction and priorities. This document proposes
  the concrete tool surface implied by that direction.
- `TOOL_PROTOCOL.md` is the live contract for tools that are actually
  implemented. A tool moves from this document into `TOOL_PROTOCOL.md`
  only after it is implemented and verified.
- `CURRENT_STATE.md` and `TEST_HISTORY.md` track what exists and what has
  been proven. Source code remains the ultimate authority.

---

# Part 1 — Current Tool Inventory (as of 2026-09)

Compiled from `agent/registry.py`, `agent/schemas.py`, `tools/scene_tools.py`,
and `addons/Execution_Agent/bridge/ai_agent_router.gd`. The registry defines
**64 actions**: 38 read-only, 23 mutations, 3 meta/control.
(2026-09-10 later: autonomy milestone added `run_scene`, `stop_run`,
`get_runtime_output`, `run_scene_offline`, `open_scene`,
`save_scene_as`, `set_project_settings`, `create_resource`, plus
telemetry JSONL export; see `TEST_HISTORY.md`.)
(Updated 2026-09-10: implemented since the original proposal — the signal
batch; script tools Phase A and Phase B including `edit_script`/
`replace_in_script`; the documentation tools `get_class_documentation`/
`search_documentation`; the scene-file batch `save_scene`/`create_scene`/
`instantiate_scene`/`get_scene_dependencies`/`get_scene_tree_of`/
`list_open_scenes`; and the Tier 2 introspection tools
`get_property_info`/`get_node_children_summary`/`assign_resource_to_property`/
`get_resource_info`/`list_project_files`/`search_in_files`/
`get_global_class_list`/`get_input_map`. Contracts live in
`TOOL_PROTOCOL.md`; verified records in `TEST_HISTORY.md`.)

## 1.1 Read-only inspection tools (21)

| Tool | Returns |
|---|---|
| `get_scene_tree` | Serialized tree of the currently edited scene |
| `find_nodes` | Nodes matching name/type/parent filters (exact/contains/starts_with/ends_with) |
| `count_nodes` | Count-only variant of the `find_nodes` filter semantics |
| `find_nodes_by_script` | Nodes whose attached script matches `script_path` |
| `find_nodes_by_group` | Nodes with live membership in `group_name` |
| `get_node_properties` | All editor-visible readable properties of a node |
| `get_node_property` | A single property value |
| `get_node_class_info` | ClassDB info for a class (base class, instantiable) |
| `list_node_signals` | Signals on a node (built-in + inherited, real reflection) |
| `list_node_connections` | Live incoming/outgoing signal connections of a node, with flags |
| `list_node_groups` | Groups a node is actually a member of |
| `get_script_content` | Full source of a GDScript file from disk |
| `list_script_diagnostics` | Fresh parse-check of a script file (`parse_ok`, error string) |
| `validate_node_type` | Whether a class name is a valid, instantiable node type |
| `list_available_node_types` | Bounded, filterable list of instantiable node types |
| `get_project_settings` | Selected ProjectSettings values (sensitive keys redacted to names only) |
| `list_autoloads` | Project autoload names and targets |
| `get_editor_state` | Bounded, deterministic editor state |
| `list_scenes_in_project` | Scene resource paths known to the editor filesystem scan |
| `get_undo_history_summary` | Undo/redo availability, action counts, current action name |
| `describe_current_scene` | **Stub** — Python-only placeholder; vision is not connected |

## 1.2 Mutation tools (14)

All are editor-native `EditorUndoRedoManager` actions with read-back
verification (`verified_*` fields) — except `create_script`, the
project's first deliberate non-undoable real mutation (file
creation, verified by read-back instead). All are registered in the
batch boundary (`boundary.py`).

| Tool | Effect |
|---|---|
| `create_node` | Create node of `node_type` named `node_name` under `parent_path` |
| `rename_node` | Rename node at `node_path` to `new_name` |
| `delete_node` | Delete node at `node_path` |
| `reparent_node` | Move node under `new_parent_path` |
| `duplicate_node` | Duplicate subtree to `new_parent_path` with `new_name` |
| `set_properties` | Set multiple properties as one validated, undoable batch |
| `move_child` | Move node to sibling index `new_index` |
| `add_to_group` | Add node to persistent group (idempotent) |
| `remove_from_group` | Remove node from persistent group (idempotent) |
| `connect_signal` | Wire emitter signal to receiver method (idempotent, verified) |
| `disconnect_signal` | Remove a signal connection (idempotent, flag-preserving undo) |
| `create_script` | Write a new, parse-gated `.gd` file (NOT undoable, write verified) |
| `attach_script` | Attach an existing script to a node (idempotent, verified) |
| `detach_script` | Remove a node's script attachment (idempotent, undo restores) |

## 1.3 Meta / control actions (3)

| Tool | Purpose |
|---|---|
| `batch` | Ordered 1–5 actions per round-trip, stop-on-first-failure |
| `final_answer` | End the current turn (session stays alive) |
| `exit_session` | Terminate the session (guarded against premature exit) |

## 1.4 Known asymmetries

- `describe_current_scene` is registered and batchable but has **no Godot
  route** — it is a vision placeholder.
- The Godot router serves `POST /ping` (health check) which Python never calls.
- `get_editor_state`, `list_scenes_in_project`, and `get_undo_history_summary`
  require the live editor (explicitly unavailable in headless runs).

---

# Part 2 — Research: what an autonomous Godot editor agent needs

Findings from surveying existing Godot agent/MCP toolsets (godot-ai with
46 tools / 120+ operations, keeveeg's godot-mcp, satelliteoflove godot-mcp)
and from the project's own roadmap:

1. **Scene-tree manipulation is table stakes** — this project already
   covers it well, with stronger verification semantics than most
   surveyed toolsets.
2. **The biggest capability gaps everywhere are scripts, signals, and
   resources.** An agent that can build node hierarchies but cannot
   attach a script, wire a signal, or assign a texture cannot complete
   any real user request ("make a button that spawns an enemy").
3. **Runtime feedback closes the loop.** The strongest pattern in current
   toolsets is combining editor tools with playtesting: run the scene,
   inject input, inspect live state, read errors. Without it, the agent
   edits blind.
4. **Vision is a differentiator but not a prerequisite.** Structured
   inspection (ClassDB, property lists, dependency graphs) substitutes
   for most "seeing" needs; screenshots matter mainly for UI/layout work.
5. **File/resource search across the project** is what enables
   multi-scene, project-aware reasoning rather than single-scene editing.
6. **Restraint wins.** Toolsets with 300+ tools are harder for models to
   use reliably. The better pattern is a focused set where every tool is
   deterministic, verified, and documented — matching this project's
   existing philosophy.

Sources surveyed: [hi-godot/godot-ai](https://github.com/hi-godot/godot-ai),
[keeveeg/godot-mcp](https://mcpservers.org/servers/keeveeg/godot-mcp),
[satelliteoflove godot-mcp](https://skillsllm.com/skill/satelliteoflove-godot-mcp),
[Godot forum MCP addon thread](https://forum.godotengine.org/t/godot-free-open-source-mcp-server-addon/133890),
[r/godot runtime-input MCP](https://www.reddit.com/r/godot/comments/1rh7tkd/i_built_an_mcp_server_that_lets_ai_assistants/),
[SoonLab comparison](https://www.soonlab.ai/blog/best-ai-agents-for-godot/),
[SummerEngine plugin guide](https://www.summerengine.com/blog/godot-ai-plugin).

---

# Part 3 — Proposed future tools

Priorities follow `ROADMAP.md` Phase 3 (expand editor operations) →
Phase 8 (project-aware development) → Phase 10 (advanced capabilities).
Every mutation below must obey the standing contract: editor-native,
undoable via `EditorUndoRedoManager`, read-back verified, registered in
`registry.py` + `boundary.py`, unit-tested, harness-tested headless,
and live-Gemini smoke tested (Rule 12).

## Tier 1 — Script tools (next major milestone)

**Status: Phase A IMPLEMENTED 2026-09-09** (`get_script_content`,
`create_script`, `attach_script`, `detach_script`,
`list_script_diagnostics`). **Phase B IMPLEMENTED 2026-09-10**
(`edit_script`, `replace_in_script` — the code-repair loop is
closed). See `TOOL_PROTOCOL.md` and `TEST_HISTORY.md`. The table
below is retained as the original proposal record.

The single highest-leverage expansion. Without scripts, the agent can
build scaffolding but not behavior.

| Proposed tool | Kind | Purpose |
|---|---|---|
| `get_script_content` | read | Return the source of the script attached to a node, or of a script resource path |
| `list_script_diagnostics` | read | Parser/compiler errors and warnings for a script (ScriptEditor/EditorInterface diagnostics) |
| `create_script` | mutation | Create a script file (`res://` path, base class, template) — not attached to anything yet |
| `attach_script` | mutation | Attach an existing script resource to a node (undoable) |
| `detach_script` | mutation | Remove the script attachment from a node (undoable) |
| `edit_script` | mutation | Controlled edit: replace whole content or a bounded, anchored region; verify by re-parse before returning success |

Notes:

- `edit_script` must include a verification step per ROADMAP Phase 3
  ("Script modification should eventually include verification steps"):
  parse-check the result and return diagnostics with the mutation result.
- Prefer whole-file or explicit-anchor edits over fuzzy search/replace.
- Script content on the Python side is text, but the *contract* stays
  structured: success, path, parse status, diagnostics list.

## Tier 1 — Signal and connection tools

**Status: IMPLEMENTED 2026-09-09** (`list_node_connections`,
`connect_signal`, `disconnect_signal` — see `TOOL_PROTOCOL.md` and
`TEST_HISTORY.md`). The table below is retained as the original
proposal record.

| Proposed tool | Kind | Purpose |
|---|---|---|
| `list_node_connections` | read | All incoming/outgoing signal connections of a node, with target nodes and bound method names |
| `connect_signal` | mutation | Connect `signal_name` on source node to a method on target node (undoable); verify via `is_connected` |
| `disconnect_signal` | mutation | Remove a connection (undoable); idempotent no-op if absent |

## Tier 1 — Scene file operations

**Status: IMPLEMENTED 2026-09-10** (`save_scene`, `create_scene`,
`instantiate_scene`, `get_scene_dependencies`,
`get_scene_tree_of`, `list_open_scenes` — see `TOOL_PROTOCOL.md`
and `TEST_HISTORY.md`). `open_scene` (switching the edited scene)
remains deliberately deferred with the documented conversation
context invalidation concern.

Notes:

- Requires deciding how callable targets are addressed: node path +
  method name (editor-native, matches the Connect dialog) is the
  deterministic choice. Callable expressions should be rejected.
- `list_node_connections` pairs with `list_node_signals` (already
  implemented) to give the model the full wiring picture.

## Tier 1 — Scene file operations

| Proposed tool | Kind | Purpose |
|---|---|---|
| `save_scene` | mutation | Save the currently edited scene to its path (undoable where Godot supports it; report explicitly if not) |
| `create_scene` | mutation | Create a new scene file with a root node of `node_type`, optionally open it |
| `instantiate_scene` | mutation | Instance an existing scene file as a child of a node (undoable); returns the instance path |
| `get_scene_dependencies` | read | External resources and sub-scene references of a scene file |
| `list_open_scenes` | read | Scenes currently open in the editor with which one is active |

Notes:

- `save_scene` is the gateway to durability: until it exists, every
  mutation is an in-editor change that dies with the editor. High value,
  but needs care around unsaved-changes semantics and the "verified"
  contract (verification = re-read from disk, not from memory).
- `open_scene` (switching the edited scene) should be considered at the
  same time, but note it invalidates most node paths the conversation is
  holding — batch boundary implications must be analyzed before adding it.

## Tier 2 — Resource tools

**Status: PARTIALLY IMPLEMENTED 2026-09-10** (`assign_resource_to_property`,
`get_resource_info`). `create_resource` remains deferred (inline vs
file-backed design); `list_resources_in_project` is covered by the
implemented `list_project_files` with an extension filter.

| Proposed tool | Kind | Purpose |
|---|---|---|
| `list_resources_in_project` | read | Bounded, filterable (type/prefix) listing of project resources, like `list_scenes_in_project` but for all resource types |
| `get_resource_info` | read | Type, path, and properties of a resource |
| `create_resource` | mutation | Create an inline or file-backed resource (e.g., a `SpriteFrames`, `Curve`, `Material`) for assignment |
| `assign_resource_to_property` | mutation | Load a `res://` resource and assign it to a node property (undoable); verify by reading the property back |

Notes:

- Texture/material/audio assignment is what makes `set_properties`
  actually useful in real scenes; currently properties can only be set
  with JSON-safe primitive values.
- Sensitive-resource concern is low, but file-backed writes must be
  explicit (no silent in-memory-only resources the user cannot see).

## Tier 2 — Deep property introspection

**Status: IMPLEMENTED 2026-09-10** (`get_property_info`,
`get_node_children_summary`).

| Proposed tool | Kind | Purpose |
|---|---|---|
| `get_property_info` | read | Type, hint, hint text, and default value for a property of a node class — lets the model construct valid `set_properties` payloads instead of guessing |
| `get_node_children_summary` | read | Lightweight child list (name, type, index) without full tree serialization, for large scenes |

Notes:

- `get_property_info` directly reduces the Gemini malformed-parameter
  failure mode observed historically: the model learns the expected type
  before writing the value.

## Tier 2 — Project-level awareness (ROADMAP Phase 8)

**Status: IMPLEMENTED 2026-09-10** (`list_project_files`,
`search_in_files`, `get_global_class_list`, `get_input_map`).
`get_scene_tree_of` was implemented with the scene-file batch.

| Proposed tool | Kind | Purpose |
|---|---|---|
| `list_project_files` | read | Bounded, type-filtered (`*.gd`, `*.tscn`, `*.tres`, …) file listing under a `res://` prefix |
| `search_in_files` | read | Bounded text search across script/resource files (name or content) |
| `get_global_class_list` | read | Project's `class_name` globals (ScriptServer) |
| `get_input_map` | read | Configured input actions and their events |
| `get_scene_tree_of` | read | Serialized tree of any scene file (not just the open one), via load-without-instancing |

## Tier 2 — Documentation and knowledge tools (proposed)

Rationale and full analysis: `MODEL_KNOWLEDGE_DRIFT.md`. In short:
reasoning models have fixed training cutoffs; the architecture is
drift-resistant for tool-mediated operations (the running editor is
the authority) but drift-prone for GDScript generation, where the
failure mode is currently silent (parses fine, wrong API, no
runtime feedback yet).

| Proposed tool | Kind | Purpose |
|---|---|---|
| `get_class_documentation` | read | Bounded, structured class reference for one Godot class (description, methods, properties, signals, enums) from version-matched bundled docs XML |
| `search_documentation` | read | Bounded search across class and member names/descriptions |

Design notes:

- The docs XML must be **pinned to the engine version the project
  targets** (4.7.2) — better than model memory and better than live
  web docs, which may not match the editor. If a future Godot
  release exposes `EditorHelp::get_doc_data()` to GDScript plugins
  (proposals #13608/#12531), reading the editor's live DocData
  becomes the preferred source.
- Offline-capable, deterministic, curated content: no open-web
  prompt-injection surface in a conversation with editor mutation
  rights.
- A general `fetch_url` tool was considered and **deferred**: if
  built later, v1 must be restricted to user-provided URLs only,
  with size-bounded, clearly-attributed external content.

## Tier 3 — Editor diagnostics and vision

| Proposed tool | Kind | Purpose |
|---|---|---|
| `get_editor_errors` | read | Errors/warnings currently visible in the Output/Debugger panels |
| `get_editor_screenshot` | read | Capture the editor viewport for vision analysis |
| `describe_current_scene` (implement) | read | Replace the existing stub with real vision: screenshot + analysis. Also decide whether it stays batchable |
| `get_node_screenshot` | read | Viewport capture scoped to a node (UI/layout debugging) |

Notes:

- Vision connects the one existing stub. It is deliberately Tier 3:
  structured inspection covers most needs, and vision adds provider and
  content-size complexity. ROADMAP positions screenshots/vision as
  deferred.
- `get_editor_errors` is cheap and disproportionately useful once the
  agent starts creating scripts (Tier 1) — it is the natural companion
  to `list_script_diagnostics`; implement whichever comes first.

## Tier 3 — Runtime and playtesting (ROADMAP Phase 10 territory)

**Status: PARTIALLY IMPLEMENTED 2026-09-10** (`run_scene`,
`stop_run`, `get_runtime_output` editor-side; `run_scene_offline`
as the autonomous output-reading tool — see `TEST_HISTORY.md` for
the verified built-in-capture engine limitation that shaped this
split). Runtime scene tree, input injection, and runtime node
state remain deferred: they require in-game instrumentation
(an autoload probe) and their own safety design.

The largest step outside the current architecture: these tools observe a
*running game*, not the editor. Requires its own design pass (lifecycle,
timeouts, process boundaries, what "undoable" even means at runtime).

| Proposed tool | Kind | Purpose |
|---|---|---|
| `run_scene` | control | Launch the current scene (or a target scene) with a bounded session |
| `stop_run` | control | Stop the running game |
| `get_runtime_output` | read | Stdout/stderr and errors from the running game |
| `get_runtime_scene_tree` | read | Live tree of the running game (diffable against the editor tree) |
| `inject_input` | control | Simulate key/mouse/action input in the running game |
| `get_runtime_node_state` | read | Property values of live nodes during the run |

Notes:

- The surveyed toolsets that rate "most capable" all have some form of
  this; deterministic playtesting is what turns the agent from an editor
  macro into a game developer's assistant. It is listed last because it
  violates several standing invariants (undoability, single authoritative
  state) and needs its own safety rules, not because it is low value.

## Explicitly rejected / deferred tool ideas

- **Arbitrary GDScript execution in the editor** — breaks every safety
  invariant in `01-DEVELOPMENT_RULES.md`. Not planned.
- **Project settings / input map mutation** — inspect-only for now;
  these change project-global behavior, deserve their own confirmation
  design per ROADMAP Phase 6 (previews, confirmation requirements).
- **Fuzzy/natural-language node addressing** — node paths and explicit
  filters stay the addressing scheme; ambiguity is resolved by the model
  via `find_nodes`, not by magic in tools.
- **A "do everything" composite tool** (e.g., `build_character`) —
  planning is the model's job through the existing step loop; composite
  tools would hide observable, undoable steps in one opaque call.

---

# Part 4 — Cross-cutting requirements for every new tool

Regardless of tier, every addition must follow the established contract:

1. **Registry first**: new `ActionSpec` in `registry.py` with correct
   `is_mutation` classification; Pydantic action in `schemas.py`.
2. **Boundary registration is mandatory for mutations** (enforced by
   `test_registry.py`): `_MUTATION_TARGET_KEYS` and
   `_BATCH_ACTION_EQUIVALENCE_KEYS` entries in `boundary.py`.
3. **Structured results only**: `success`, resolved paths, old/new
   values, `verified_*` fields, `undoable` flag — no free-text reports.
4. **Verify by read-back**: every mutation reports what Godot actually
   observed after the operation, not what was requested.
5. **Headless honesty**: tools that need the live editor must return the
   explicit unavailable error (`_editor_unavailable` pattern), never a
   fabricated result.
6. **Gemini schema compatibility (Rule 12)**: any `AgentDecision` schema
   change requires `make_gemini_schema_compatible()` analysis, overlap
   checking, adapter tests, and a mandatory live Gemini smoke test when
   credentials exist.
7. **Harness + unit tests + TEST_HISTORY entry** before a tool is
   considered implemented; only then does it graduate into
   `TOOL_PROTOCOL.md`.
8. **Batch-size discipline**: new tools should be batchable unless they
   are control-flow actions; remember `MAX_BATCH_SIZE = 5` bounds total
   work per round-trip.
