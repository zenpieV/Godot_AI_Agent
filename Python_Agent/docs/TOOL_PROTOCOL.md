# Godot AI Agent Tool Protocol

## Purpose

This document defines the structured communication protocol between the Python AI agent and the Godot EditorPlugin bridge.

The purpose of this protocol is to ensure that:

- Python sends deterministic requests.
- Godot validates editor operations.
- Tool results are structured and machine-readable.
- The language model reasons from actual editor observations.
- Tool failures provide enough information for recovery.
- Python code does not invent scene state.
- Godot remains authoritative for the currently open editor and scene state.

This document describes the current tool protocol and its intended semantics.

For the current implementation state, see:

- `CURRENT_STATE.md`

For verified historical behavior and test results, see:

- `TEST_HISTORY.md`

For architectural rules, see:

- `.agentrules/01-DEVELOPMENT_RULES.md`
- `.agentrules/02-PROJECT_ARCHITECTURE.md`

---

# Core Architecture

The communication flow is:

    User request
    -> Python agent
    -> model provider
    -> structured agent decision
    -> decision validation and deterministic constraint repair
    -> Python HTTP bridge
    -> Godot EditorPlugin
    -> Godot editor operation
    -> structured tool result
    -> Python agent
    -> next reasoning step or final answer

The model does not directly manipulate Godot.

The model selects an action through a structured decision.

Python validates and dispatches that decision.

The Godot EditorPlugin performs the editor-native operation and returns the authoritative result.

---

# General Tool Result Rules

All tool results should be JSON-compatible dictionaries.

Every tool result should include:

    success

Where:

- `true` means the requested tool operation completed successfully.
- `false` means the tool operation failed.

Failures should include:

    error

Example:

    {
      "success": false,
      "error": "Parent node not found: PersistentEnemy"
    }

Successful results should include information relevant to the operation.

The agent must reason from these results.

A tool result is not merely diagnostic text for the user.

It is an observation used by the next reasoning step.

---

# Scene Path Semantics

## Root Node

The scene root is represented by:

    .

Example root result:

    {
      "is_root": true,
      "name": "game_scene",
      "node_type": "Node2D",
      "path": "."
    }

The root path must not be confused with the root node name.

---

## Descendant Paths

Descendant nodes use slash-separated paths.

Examples:

    CharacterBody2D

    CharacterBody2D/PersistentEnemy

    CharacterBody2D/PersistentEnemy/NestedTest

Paths returned by Godot are authoritative.

The Python agent and model should prefer exact paths returned by tool results rather than guessing paths.

---

# Tool: get_scene_tree

## Purpose

Returns the hierarchy of the currently active scene.

This tool is useful when:

- node paths are unknown,
- searches have failed,
- hierarchy context is required,
- multiple nodes must be located,
- recovery requires inspecting the entire scene.

---

## Input

The current tool requires no significant node-selection parameters.

Conceptually:

    {}

---

## Successful Result

Example:

    {
      "action": "get_scene_tree",
      "scene_tree": {
        "children": [
          {
            "children": [
              {
                "children": [],
                "is_root": false,
                "name": "PersistentEnemy",
                "node_type": "Node2D",
                "path": "CharacterBody2D/PersistentEnemy"
              }
            ],
            "is_root": false,
            "name": "CharacterBody2D",
            "node_type": "CharacterBody2D",
            "path": "CharacterBody2D"
          }
        ],
        "is_root": true,
        "name": "game_scene",
        "node_type": "Node2D",
        "path": "."
      },
      "success": true
    }

---

## Scene Tree Structure

Each node may contain:

    children
    is_root
    name
    node_type
    path

The structure is recursive.

Conceptually:

    scene_tree
    |
    +-- root
        |
        +-- children[]
            |
            +-- child
                |
                +-- children[]
                +-- name
                +-- node_type
                +-- path
                +-- is_root

Python code processing this structure must handle arbitrary nesting.

Do not assume that a target node exists at a fixed depth.

Do not manually construct paths when authoritative paths are available in the returned structure.

---

# Tool: find_nodes

## Purpose

Searches the current scene for nodes matching structured criteria.

This tool should normally be preferred over `get_scene_tree` when searching for a known node name.

---

## Input Fields

Possible fields include:

    node_name
    node_type
    parent_path
    name_match
    include_root

Not every field is required for every search.

---

## node_name

The node name to search for.

Example:

    {
      "node_name": "PersistentEnemy"
    }

---

## node_type

Optional Godot node type filter.

Example:

    {
      "node_type": "Node2D"
    }

---

## parent_path

Optional search scope.

When provided, the search is limited to the specified parent scope according to the implementation.

Example:

    {
      "parent_path": "CharacterBody2D"
    }

Important semantic rule:

A node mentioned by the user as a destination for another operation must not automatically become a `find_nodes.parent_path`.

For example:

    Move FinalTestEnemy under PersistentEnemy.

This contains two semantic targets:

- source node: `FinalTestEnemy`
- destination parent: `PersistentEnemy`

Searching for `FinalTestEnemy` should not automatically be restricted to children of `PersistentEnemy`.

The correct recovery sequence may be:

1. Find `FinalTestEnemy`.
2. Find `PersistentEnemy`.
3. Use their authoritative paths.
4. Call `reparent_node`.

Only use `parent_path` when the user explicitly intends the search itself to be scoped.

---

## name_match

Defines how `node_name` is matched.

Expected values include:

    exact
    contains

Examples:

    {
      "node_name": "PersistentEnemy",
      "name_match": "exact"
    }

Or:

    {
      "node_name": "Enemy",
      "name_match": "contains"
    }

Prefer `exact` when the user provides a complete explicit node name.

Use `contains` only when broader discovery is actually needed.

---

## include_root

Boolean indicating whether the scene root may be included in search results.

Example:

    {
      "include_root": false
    }

---

## Successful Result

Example:

    {
      "action": "find_nodes",
      "count": 1,
      "include_root": false,
      "name_match": "exact",
      "node_name_filter": "PersistentEnemy",
      "node_type_filter": "",
      "nodes": [
        {
          "is_root": false,
          "name": "PersistentEnemy",
          "node_type": "Node2D",
          "path": "CharacterBody2D/PersistentEnemy"
        }
      ],
      "parent_path_filter": "",
      "success": true
    }

---

## Important Result Semantics

A successful search request does not necessarily mean that a node was found.

Example:

    {
      "success": true,
      "count": 0,
      "nodes": []
    }

This means:

- the search operation succeeded,
- but no matching nodes were found.

The agent must distinguish:

    tool failure

from:

    successful search with zero matches

These require different recovery behavior.

---

# Tool: create_node

## Purpose

Creates a Godot node under a specified parent.

The operation should be editor-native and undoable when supported by the current implementation.

---

## Required Input

    parent_path
    node_type
    node_name

Example:

    {
      "parent_path": "CharacterBody2D/PersistentEnemy",
      "node_type": "Node2D",
      "node_name": "NestedTest"
    }

---

## Validation

Before dispatching the request, the agent should ensure that all required fields are available.

An incomplete request such as:

    {
      "action": "create_node",
      "parent_path": "PersistentEnemy"
    }

should not ideally result in repeated identical calls.

A validation failure may return:

    {
      "success": false,
      "error": "create_node requires parent_path, node_type, and node_name."
    }

The next step should materially improve the missing information.

---

## Successful Result

Example:

    {
      "action": "create_node",
      "created_path": "CharacterBody2D/PersistentEnemy/NestedTest",
      "message": "Undoable node created successfully in the Godot editor.",
      "node_name": "NestedTest",
      "node_type": "Node2D",
      "parent_path": "CharacterBody2D/PersistentEnemy",
      "success": true,
      "undoable": true
    }

The returned `created_path` should be preferred as the authoritative path for future operations.

---

## Parent Not Found

Example:

    {
      "success": false,
      "error": "Parent node not found: PersistentEnemy"
    }

Potential recovery:

1. Search for the parent node by exact name.
2. Obtain its authoritative path.
3. Retry with the full path.

The agent should not repeatedly call `create_node` with the same invalid parent path.

---

# Tool: rename_node

## Purpose

Renames an existing node.

---

## Required Input

    node_path
    new_name

Example:

    {
      "node_path": "CharacterBody2D/TestEnemy",
      "new_name": "RenamedTestEnemy"
    }

---

## Validation Failure

Example:

    {
      "success": false,
      "error": "rename_node requires node_path and new_name."
    }

If the model only knows the node name, it should first locate the node.

Typical recovery:

1. Use `find_nodes`.
2. Obtain the exact `path`.
3. Call `rename_node`.

---

## Successful Result

Example:

    {
      "action": "rename_node",
      "message": "Node renamed successfully in the Godot editor.",
      "new_name": "RenamedTestEnemy",
      "node_path_before": "CharacterBody2D/TestEnemy",
      "old_name": "TestEnemy",
      "success": true,
      "undoable": true
    }

Important:

After renaming a node, the previous path may no longer be valid.

The agent should treat old paths carefully.

If the renamed node will be used again, its new path should be resolved or deterministically derived only when path semantics make that safe.

---

# Tool: move_child

## Purpose

Moves an existing child node within its parent to a requested
sibling index, changing sibling order without changing the parent.

The Godot editor handles this as one undoable
`EditorUndoRedoManager` action ("AI Agent: Move \<name\> to index \<n\>").

## Request

```json
{
  "action": "move_child",
  "reason": "Move RightArm above the sprite.",
  "node_path": "Player/RightArm",
  "new_index": 0
}
```

- `node_path`: scene-relative path of the child to move.
- `new_index`: target sibling index within the parent,
  `0 <= new_index < child_count`. Rejected outside the range.

## Validation (Godot side, in order)

1. `node_path` and `new_index` present; `new_index` must be an
   integer (integral floats accepted, fractional values rejected).
2. Node must exist.
3. The scene root cannot be moved; the node must have a parent.
4. `new_index` must be in `[0, child_count - 1]`.

## No-op semantics

If the node is already at `new_index`, the tool returns success
with `"moved": false` and `"undoable": false`. No undo history is
created and no scene state changes; the sibling order is still
read back and verified.

## Success response

```json
{
  "action": "move_child",
  "message": "Node moved successfully in the Godot editor.",
  "moved": true,
  "node_name": "RightArm",
  "node_path": "Player/RightArm",
  "old_index": 2,
  "new_index": 0,
  "requested_index": 0,
  "parent_path": "Player",
  "sibling_order_before": ["Sprite2D", "LeftArm", "RightArm", "LeftLeg", "RightLeg", "SessionLifecycleTest"],
  "sibling_order_after": ["RightArm", "Sprite2D", "LeftArm", "LeftLeg", "RightLeg", "SessionLifecycleTest"],
  "verified_index": true,
  "verified_order": true,
  "success": true,
  "undoable": true
}
```

- `sibling_order_after` is read back from the real scene after the
  move; `verified_order` compares it against the expected order
  computed by simulating the move on `sibling_order_before`.
  Verification is never fabricated.
- `verified_index` is `false` if the node's actual index after the
  move differs from the requested index (treated as a verification
  failure by the Python mutation contract).

## Failure response

```json
{
  "error": "move_child new_index 99 is out of range: the parent Player has 6 child(ren); valid indices are 0 to 5.",
  "success": false
}
```

A headless process without the plugin-owned
`EditorUndoRedoManager` receives an explicit unavailable error
instead of mutating without undo support.

---

# Tool: add_to_group

## Purpose

Adds an existing node in the currently edited scene to a persistent
group. Group membership is instance state on the node.

The Godot editor handles this as one undoable
`EditorUndoRedoManager` action ("AI Agent: Add \<name\> to group
\<group\>").

## Request

```json
{
  "action": "add_to_group",
  "reason": "Mark Sprite2D as a damageable target.",
  "node_path": "Player/Sprite2D",
  "group_name": "damageable"
}
```

- `node_path`: scene-relative path of the node to add.
- `group_name`: non-empty group name (whitespace-stripped).

## Validation (Godot side, in order)

1. `group_name` present and a non-empty string (after stripping).
2. `node_path` present.
3. Node must exist.

## Idempotent semantics

If the node is already in `group_name`, the tool returns success with
`"changed": false` and `"undoable": false`. No undo history is created
and no scene state changes; membership is still read back from the
node and verified.

## Success response

```json
{
  "action": "add_to_group",
  "message": "Node added to group successfully in the Godot editor.",
  "changed": true,
  "node_name": "Sprite2D",
  "node_path": "Player/Sprite2D",
  "group_name": "damageable",
  "was_member": false,
  "is_member": true,
  "verified_membership": true,
  "success": true,
  "undoable": true
}
```

- `is_member` is read back from the real node after the change;
  `verified_membership` is `true` only when the actual membership
  matches the expected post-add state. Verification is never
  fabricated.

## Failure response

```json
{
  "error": "add_to_group requires a non-empty group_name.",
  "success": false
}
```

A headless process without the plugin-owned
`EditorUndoRedoManager` receives an explicit unavailable error
instead of mutating without undo support.

---

# Tool: remove_from_group

## Purpose

Removes an existing node in the currently edited scene from a
persistent group.

The Godot editor handles this as one undoable
`EditorUndoRedoManager` action ("AI Agent: Remove \<name\> from group
\<group\>").

## Request

```json
{
  "action": "remove_from_group",
  "reason": "Sprite2D should no longer be damageable.",
  "node_path": "Player/Sprite2D",
  "group_name": "damageable"
}
```

- `node_path`: scene-relative path of the node to remove.
- `group_name`: non-empty group name (whitespace-stripped).

## Validation (Godot side, in order)

1. `group_name` present and a non-empty string (after stripping).
2. `node_path` present.
3. Node must exist.

## Idempotent semantics

If the node is not in `group_name`, the tool returns success with
`"changed": false` and `"undoable": false`. No undo history is created
and no scene state changes; membership is still read back from the
node and verified.

## Success response

```json
{
  "action": "remove_from_group",
  "message": "Node removed from group successfully in the Godot editor.",
  "changed": true,
  "node_name": "Sprite2D",
  "node_path": "Player/Sprite2D",
  "group_name": "damageable",
  "was_member": true,
  "is_member": false,
  "verified_membership": true,
  "success": true,
  "undoable": true
}
```

- `is_member` is read back from the real node after the change;
  `verified_membership` is `true` only when the actual membership
  matches the expected post-remove state. Verification is never
  fabricated.

## Failure response

```json
{
  "error": "remove_from_group requires a non-empty group_name.",
  "success": false
}
```

A headless process without the plugin-owned
`EditorUndoRedoManager` receives an explicit unavailable error
instead of mutating without undo support.

---


# Tool: list_node_connections

## Purpose

Lists the live signal connections of one node in the currently
edited scene, in both directions. Complements `list_node_signals`,
which reports the signal definitions but never connection state.

The result answers from the node's real connection state
(`get_incoming_connections` and `get_signal_connection_list`).
No scene state is modified.

## Request

```json
{
  "action": "list_node_connections",
  "reason": "Audit how Sprite2D is wired before rewiring.",
  "node_path": "Player/Sprite2D"
}
```

- `node_path`: scene-relative path (use `.` for the scene root).

## Successful Result

```json
{
  "action": "list_node_connections",
  "node_path": "Player/Sprite2D",
  "node_name": "Sprite2D",
  "node_type": "Sprite2D",
  "total_incoming": 1,
  "total_outgoing": 2,
  "internal_connections_omitted": 5,
  "incoming": [
    {
      "signal": "tree_entered",
      "source": "Player/Sprite2D",
      "source_name": "Sprite2D",
      "method": "queue_free",
      "deferred": false,
      "persistent": true,
      "one_shot": false
    }
  ],
  "outgoing": [
    {
      "signal": "tree_exited",
      "target": "Player/RightArm",
      "target_name": "RightArm",
      "method": "queue_free",
      "deferred": true,
      "persistent": true,
      "one_shot": false
    }
  ],
  "success": true
}
```

- Entries are sorted by signal name, then peer path, then method
  name, for deterministic output.
- `deferred` / `persistent` / `one_shot` are read from the real
  connection flags.

## Editor-internal connection filtering

Inside a running editor every node carries non-persistent editor
plumbing (for example `SceneTreeEditor` hooks into
`script_changed`). Connections whose peer node lies outside the
edited scene are omitted from `incoming`/`outgoing` and reported
only as `internal_connections_omitted`, keeping the bridge's
scene-relative path contract. Nothing is silently hidden.

## Failure response

```json
{
  "error": "Node not found: Ghost",
  "success": false
}
```

This tool is read-only and works without the editor undo manager.

---


# Tool: connect_signal

## Purpose

Connects a signal on one existing node (the emitter) to a method
on another existing node (the receiver). Connections are addressed
exactly like the editor's Connect dialog: emitter node path +
signal name -> receiver node path + method name. Callable
expressions and bound arguments are deliberately not supported.

The Godot editor handles an actual change as one undoable
`EditorUndoRedoManager` action ("AI Agent: Connect \<emitter\>.
\<signal\> to \<receiver\>.\<method\>"). Connections are created
persistent (so they serialize with the scene, matching editor-made
wiring) and optionally deferred.

## Request

```json
{
  "action": "connect_signal",
  "reason": "Spawn an enemy whenever the timer ticks.",
  "node_path": "SpawnTimer",
  "signal_name": "timeout",
  "target_path": "EnemySpawner",
  "method_name": "spawn_enemy",
  "deferred": false
}
```

- `node_path`: emitter node (scene-relative).
- `signal_name`: non-empty signal name (whitespace-stripped).
- `target_path`: receiver node (scene-relative).
- `method_name`: non-empty method name (whitespace-stripped).
- `deferred`: optional boolean (default false).

## Validation (Godot side, in order)

1. `signal_name`, `target_path`, `method_name` present, strings,
   non-empty.
2. `node_path` present.
3. Emitter node must exist; receiver node must exist.
4. Emitter must actually have the signal (`has_signal`) - the
   error points to `list_node_signals`.
5. Receiver must actually have the method (`has_method`).
6. `deferred`, if present, must be a boolean.

## Idempotent semantics

If the exact pair (same signal, same receiver, same method) is
already connected, the tool returns success with `"changed": false`
and `"undoable": false`. No undo history is created; the
connection is still read back from the emitter and verified.

## Success response

```json
{
  "action": "connect_signal",
  "message": "Signal connected successfully in the Godot editor.",
  "node_path": "SpawnTimer",
  "node_name": "SpawnTimer",
  "signal_name": "timeout",
  "target_path": "EnemySpawner",
  "target_name": "EnemySpawner",
  "method_name": "spawn_enemy",
  "deferred": false,
  "was_connected": false,
  "is_connected": true,
  "changed": true,
  "verified_connection": true,
  "success": true,
  "undoable": true
}
```

- `is_connected` is read back from the real emitter after the
  change; `verified_connection` is `true` only when the actual
  connection state matches the expected post-connect state.

## Failure response

```json
{
  "error": "connect_signal: node Sprite2D has no signal named made_up_signal. Use list_node_signals to discover valid signal names.",
  "success": false
}
```

A headless process without the plugin-owned
`EditorUndoRedoManager` receives an explicit unavailable error
instead of mutating without undo support.

---


# Tool: disconnect_signal

## Purpose

Removes an existing signal connection between two nodes.

The Godot editor handles an actual change as one undoable
`EditorUndoRedoManager` action ("AI Agent: Disconnect \<emitter\>.
\<signal\> from \<receiver\>.\<method\>"); the undo restores the
original connection including its exact flags.

## Request

```json
{
  "action": "disconnect_signal",
  "reason": "This stale wiring fires the old handler.",
  "node_path": "SpawnTimer",
  "signal_name": "timeout",
  "target_path": "EnemySpawner",
  "method_name": "spawn_enemy"
}
```

- Same fields as `connect_signal`, without `deferred`.

## Validation (Godot side, in order)

1. `signal_name`, `target_path`, `method_name` present, strings,
   non-empty.
2. `node_path` present.
3. Emitter node must exist; receiver node must exist.
4. Emitter must actually have the signal; receiver must actually
   have the method.

## Idempotent semantics

If the pair is not connected, the tool returns success with
`"changed": false` and `"undoable": false`. No undo history is
created; the state is still read back and verified. Because this
case needs no undo support, it also works in processes without
the editor undo manager.

## Success response

```json
{
  "action": "disconnect_signal",
  "message": "Signal disconnected successfully in the Godot editor.",
  "node_path": "SpawnTimer",
  "node_name": "SpawnTimer",
  "signal_name": "timeout",
  "target_path": "EnemySpawner",
  "target_name": "EnemySpawner",
  "method_name": "spawn_enemy",
  "was_connected": true,
  "is_connected": false,
  "changed": true,
  "verified_connection": true,
  "success": true,
  "undoable": true
}
```

- `verified_connection` is `true` only when the actual connection
  state matches the expected post-disconnect state.

## Failure response

```json
{
  "error": "disconnect_signal: node EnemySpawner has no method named spawn_enemy.",
  "success": false
}
```

An actual disconnect requires the plugin-owned
`EditorUndoRedoManager`; without it the tool reports an explicit
unavailable error instead of mutating without undo support.

---


# Tool: create_script

## Purpose

Creates a NEW GDScript file in the project with the full content
provided by the model. This is the agent's first code-producing
tool.

Contract decisions that differ deliberately from scene mutations:

- File creation is NOT undoable through the editor's undo system;
  the result reports `"undoable": false` and verifies the write by
  reading the file back (`verified_write`).
- The content is parse-checked BEFORE writing: content that does
  not parse is never written to disk, so the agent cannot create
  an unfixable broken script file.
- Existing files are never overwritten (no script modification in
  this tool set).
- Missing parent directories are created.

## Request

```json
{
  "action": "create_script",
  "reason": "The spawner needs its behavior script.",
  "script_path": "res://scripts/enemy_spawner.gd",
  "content": "extends Node2D\n\nfunc spawn_enemy() -> void:\n\t...\n"
}
```

- `script_path`: `res://` path ending in `.gd` (prefix auto-added
  if missing); no directory traversal, no backslashes.
- `content`: the complete GDScript source; non-empty.

## Validation (Godot side, in order)

1. `script_path` present, non-empty string; normalized to
   `res://`; must end in `.gd`; no `..`; no backslashes; non-empty
   file name.
2. `content` present, a non-empty string.
3. The file must not already exist.
4. Parse gate: a fresh `GDScript` parse of the content must
   succeed.

## Success response

```json
{
  "action": "create_script",
  "message": "Script created successfully in the project.",
  "script_path": "res://scripts/enemy_spawner.gd",
  "line_count": 7,
  "parse_ok": true,
  "changed": true,
  "verified_write": true,
  "success": true,
  "undoable": false
}
```

- `verified_write` is `true` only when the file read back from
  disk equals the requested content.

## Failure response

```json
{
  "error": "create_script: content does not parse (Parse error). Nothing was written to disk.",
  "success": false
}
```

Other structured failures: `script already exists: ...`, missing
`.gd` extension, directory traversal, backslash paths, empty
content, unwritable directory.

This tool needs no editor undo manager (it writes a file, not an
undoable scene change).

---


# Tool: attach_script

## Purpose

Attaches an existing GDScript resource to an existing node in the
currently edited scene as one undoable `EditorUndoRedoManager`
property action ("AI Agent: Attach \<script\> to \<node\>"); the
undo restores the previous attachment (including "no script").

## Request

```json
{
  "action": "attach_script",
  "reason": "LeftArm should use the probe behavior.",
  "node_path": "Player/LeftArm",
  "script_path": "res://scripts/agent_probe.gd"
}
```

## Validation (Godot side, in order)

1. `node_path` and `script_path` present, non-empty strings
   (script path normalized/validated like `create_script`).
2. Node must exist; script file must exist.
3. The resource must load and be a GDScript.
4. Idempotent case: the SAME script already attached is a
   deterministic no-op success (`changed: false`).
5. Deterministic refusal: a DIFFERENT script already attached
   fails with "Use detach_script first" - attaching is never
   implicitly destructive.

## Success response

```json
{
  "action": "attach_script",
  "message": "Script attached successfully in the Godot editor.",
  "node_path": "Player/LeftArm",
  "node_name": "LeftArm",
  "script_path": "res://scripts/agent_probe.gd",
  "was_attached": false,
  "is_attached": true,
  "changed": true,
  "verified_attachment": true,
  "success": true,
  "undoable": true
}
```

- `is_attached` is read back from the node (`get_script()` +
  `resource_path` comparison) after the change.

## Failure response

```json
{
  "error": "attach_script: node LeftArm already has a different script attached (res://scripts/agent_probe.gd). Use detach_script first.",
  "success": false
}
```

A headless process without the plugin-owned
`EditorUndoRedoManager` receives an explicit unavailable error
instead of mutating without undo support.

---


# Tool: detach_script

## Purpose

Removes the script attached to a node as one undoable
`EditorUndoRedoManager` property action; the undo restores the
previous script.

## Request

```json
{
  "action": "detach_script",
  "reason": "This node should not carry behavior anymore.",
  "node_path": "Player/LeftArm"
}
```

## Idempotent semantics

If the node has no script attached, the tool returns success with
`"changed": false` and `"undoable": false`. Because nothing
changes, this no-op also works in processes without the editor
undo manager. Removing an existing attachment requires the
undo manager and reports the explicit unavailable error without
it.

## Success response

```json
{
  "action": "detach_script",
  "message": "Script detached successfully in the Godot editor.",
  "node_path": "Player/LeftArm",
  "node_name": "LeftArm",
  "detached_script": "res://scripts/agent_probe.gd",
  "was_attached": true,
  "is_attached": false,
  "changed": true,
  "verified_attachment": true,
  "success": true,
  "undoable": true
}
```

---


# Tool: get_script_content

## Purpose

Reads the source of a GDScript file from the project. The
bridge reads the real file from disk; nothing is fabricated. To
learn which script a node uses, inspect the node with
`get_node_properties` or `find_nodes_by_script` first.

Optional line paging (`start_line` 1-based, `line_count` 1-500)
bounds large reads: a paged result reports `total_lines`,
`start_line`, `end_line`, and `truncated` so a bounded read is
never mistaken for the whole file. Without them the full source
is returned (historical behavior; `total_lines` is now also
reported).

## Request

```json
{
  "action": "get_script_content",
  "reason": "I need the current source before suggesting changes.",
  "script_path": "res://scripts/agent_probe.gd"
}
```

## Successful Result

```json
{
  "action": "get_script_content",
  "script_path": "res://scripts/agent_probe.gd",
  "source": "extends Node\n\nvar probe_health := 10\n",
  "total_lines": 4,
  "line_count": 4,
  "size_bytes": 45,
  "success": true
}
```

Read-only; works headless. Missing scripts return a structured
`"script not found: ..."` failure.

---


# Tool: list_script_diagnostics

## Purpose

Parse-checks a GDScript file and reports the result. The bridge
performs a fresh parse of the current file content; the Godot
error code is the only programmatic parse signal available, so
line-level diagnostics are never fabricated.

Use it after `create_script` or before `attach_script` when the
script's validity is uncertain.

## Request

```json
{
  "action": "list_script_diagnostics",
  "reason": "Confirm the new script parses before attaching.",
  "script_path": "res://scripts/agent_probe.gd"
}
```

## Successful Result

```json
{
  "action": "list_script_diagnostics",
  "script_path": "res://scripts/agent_probe.gd",
  "parse_ok": true,
  "error": "",
  "line_count": 4,
  "size_bytes": 45,
  "success": true
}
```

For a script that fails to parse, `parse_ok` is `false` and
`error` carries the Godot error string (e.g. `"Parse error"`).
Read-only; works headless and in the live editor.

---


# Tool: edit_script

## Purpose

Replaces the ENTIRE content of an existing GDScript file. The
parse gate runs BEFORE writing: content that does not parse is
never written, so the previous working content stays on disk.
Byte-identical replacement is a deterministic no-op success.
`edit_script` never creates files; `create_script` never edits.

Non-undoable (file write); verified by reading the file back
(`verified_write`).

## Request

```json
{
  "action": "edit_script",
  "reason": "Replace the whole probe script with the fixed logic.",
  "script_path": "res://scripts/probe.gd",
  "content": "extends Node\n\nvar value := 20\n"
}
```

## Validation (Godot side, in order)

1. `script_path` present and normalized (same rules as
   `create_script`); `content` present, non-empty string.
2. The file must exist ("Use create_script for new files").
3. Idempotent case: byte-identical content is a no-op success.
4. Parse gate on the new content.

## Success response

```json
{
  "action": "edit_script",
  "message": "Script content replaced successfully.",
  "script_path": "res://scripts/probe.gd",
  "line_count": 7,
  "parse_ok": true,
  "changed": true,
  "verified_write": true,
  "success": true,
  "undoable": false
}
```

## Failure response

```json
{
  "error": "edit_script: content does not parse (Parse error). Nothing was written to disk.",
  "success": false
}
```

---


# Tool: replace_in_script

## Purpose

Deterministic anchored edit inside an existing GDScript file:
`old_string` must occur EXACTLY ONCE in the current content and is
replaced by `new_string`. Zero occurrences with the replacement
already present is an already-applied no-op; zero occurrences
otherwise is a structured failure; multiple occurrences are
refused ("use a longer anchor"). Never fuzzy-matched.

Non-undoable; parse gate before write; `verified_write` read-back.

## Request

```json
{
  "action": "replace_in_script",
  "reason": "Bump the probe value after diagnostics.",
  "script_path": "res://scripts/probe.gd",
  "old_string": "var value := 20",
  "new_string": "var value := 30"
}
```

`new_string` may be an empty string (deletion); `old_string` must
be non-empty.

## Success response

```json
{
  "action": "replace_in_script",
  "message": "Script edited successfully.",
  "script_path": "res://scripts/probe.gd",
  "line_count": 7,
  "parse_ok": true,
  "changed": true,
  "verified_write": true,
  "success": true,
  "undoable": false
}
```

Idempotent responses carry `"changed": false` with
`"message": "Replacement already applied; no change was made."`.

## Failure response

```json
{
  "error": "replace_in_script: old_string occurs 2 times in res://scripts/probe.gd. The anchor must be unique; use a longer anchor.",
  "success": false
}
```

---


# Tool: get_class_documentation

## Purpose

Python-side tool (never touches the bridge): returns the structured
documentation entry for one Godot class from the bundled,
version-pinned reference (`data/godot_docs_4.7.2.json.gz`, built by
`scripts/prepare_godot_docs.py` from the official engine docs XML).
Use BEFORE writing code against unfamiliar classes; see
`MODEL_KNOWLEDGE_DRIFT.md` for the rationale.

## Request

```json
{
  "action": "get_class_documentation",
  "reason": "Check the exact AnimationPlayer API before coding.",
  "class_name": "AnimationPlayer",
  "sections": ["brief", "methods"]
}
```

- `class_name`: required.
- `sections`: optional list drawn from `brief`, `description`,
  `methods`, `constructors`, `properties`, `signals`, `constants`,
  `theme_items`. Unrequested sections are absent, never fabricated.

## Successful Result

`success`, `class_name`, `docs_version`, `inherits` (always
included), plus each requested section: methods carry
`{signature, description}`, properties `{type, default,
description}`, signals `{signature, description}`, constants
`{value, enum?, description}`.

Unknown classes return a structured failure pointing to
`search_documentation`.

---


# Tool: search_documentation

## Purpose

Python-side tool: bounded, ranked, case-insensitive search across
class names, member names, and documentation text of the bundled
reference. Ranking: exact class name > class name substring >
member name > description text (full-text requires queries of 4+
characters).

## Request

```json
{
  "action": "search_documentation",
  "reason": "Find the right class for a one-shot timer.",
  "query": "timer",
  "limit": 5
}
```

- `query` required; `limit` optional (1-25, default 10).

## Successful Result

```json
{
  "action": "search_documentation",
  "query": "timer",
  "docs_version": "4.7.2",
  "total_matches": 12,
  "truncated": true,
  "limit": 5,
  "matches": [
    {"kind": "class", "class_name": "Timer", "member_name": "",
     "rank": 0, "snippet": "Counts down..."}
  ],
  "success": true
}
```

Match kinds: `class`, `method`, `property`, `signal`,
`description`.

---


# Tool: save_scene

## Purpose

Saves the currently edited scene to its own file on disk via the
editor. Requires the running editor (explicit unavailable error
headless). Persistence is what makes every other mutation survive
the editor session.

## Request

`{"action": "save_scene", "reason": "Persist the completed work."}`
- No parameters. Scenes that have never been saved (no file path)
  return a structured failure pointing at `create_scene`.

## Success response

```json
{
  "action": "save_scene",
  "message": "Scene saved successfully in the Godot editor.",
  "scene_path": "res://game_scene.tscn",
  "scene_name": "game_scene",
  "changed": true,
  "verified_write": true,
  "success": true,
  "undoable": false
}
```

`verified_write` compares the file's modification time before and
after the save.

---


# Tool: create_scene

## Purpose

Creates a NEW scene file with a root node of the requested type.
Never overwrites; creates missing parent directories. The file is
created on disk but deliberately NOT opened in the editor (opening
changes the edited-scene context and would invalidate the
conversation's node paths).

Non-undoable; verified by loading the file back and checking the
instantiated root's type and name (the root is named after the
scene file).

## Request

```json
{
  "action": "create_scene",
  "reason": "The enemy needs its own scene.",
  "scene_path": "res://scenes/enemy.tscn",
  "root_node_type": "CharacterBody2D"
}
```

Validation: strict `.tscn` path rules (same discipline as script
paths), root type must exist in ClassDB and be directly
instantiable.

## Success response

`success`, `scene_path`, `root_node_type`, `root_name`,
`changed: true`, `verified_write`, `undoable: false`.

---


# Tool: instantiate_scene

## Purpose

Instances an existing scene file as a child of a node in the
currently edited scene, as one undoable `EditorUndoRedoManager`
action (add_child + set_owner; undo removes the child).

## Request

```json
{
  "action": "instantiate_scene",
  "reason": "Place the enemy in the level.",
  "parent_path": "Level",
  "scene_path": "res://scenes/enemy.tscn",
  "new_name": "Enemy1"
}
```

- `new_name` optional; falls back to the instanced root's own
  name, then the scene file name. `add_child()` silently renames
  on conflicts, so the ACTUAL name is reported.

## Success response

```json
{
  "action": "instantiate_scene",
  "message": "Scene instanced successfully in the Godot editor.",
  "scene_path": "res://scenes/enemy.tscn",
  "parent_path": "Level",
  "node_path": "Level/Enemy1",
  "node_name": "Enemy1",
  "requested_name": "Enemy1",
  "changed": true,
  "verified_instance": true,
  "success": true,
  "undoable": true
}
```

`verified_instance` reads the child back and compares
`scene_file_path` with the requested scene.

---


# Tool: get_scene_dependencies

## Purpose

Reports the sub-scenes and external resources a scene file depends
on, answered from the loaded `PackedScene` state — never by
parsing file text. The scene is loaded without being opened; the
edited scene is untouched.

## Request

```json
{
  "action": "get_scene_dependencies",
  "reason": "Check what the level pulls in.",
  "scene_path": "res://game_scene.tscn"
}
```

## Successful Result

`node_count`, `sub_scenes` (list of `{scene_path, used_by_node}`),
`resources` (list of `{resource_path, used_by}`), `total_*`
counts, and `internal_omitted` when the bounded cap (200) is
reached. Sorted for deterministic output.

---


# Tool: get_scene_tree_of

## Purpose

Serializes the node tree of any scene file without opening it,
using the same node serialization as `get_scene_tree` scoped to
the requested file. The scene is instantiated without entering
the tree and freed immediately. Use for multi-scene reasoning;
prefer `get_scene_tree` for the currently edited scene.

## Request / Result

Request takes `scene_path`. Result carries
`scene_tree` (same structure as `get_scene_tree`, with the
file's root reported as `is_root: true` and paths relative to
it), plus `scene_path`.

---


# Tool: list_open_scenes

## Purpose

Lists scenes currently open in the running editor with the
actively edited scene marked. Requires the running editor
(explicit unavailable error headless).

## Result

`open_scenes` (sorted paths), `count`, `edited_scene`.

---


# Tool: get_property_info

## Purpose

Deep introspection for ONE property of a node: real reflection
type/hint/usage from `get_property_list`, the current value
serialized JSON-safely, and the class default from ClassDB. Use
BEFORE `set_properties` to learn the expected value shape instead
of guessing the property schema (this directly targets the
historical malformed-parameter failure mode).

## Request

```json
{
  "action": "get_property_info",
  "reason": "Learn the expected texture assignment shape.",
  "node_path": "Player/Sprite2D",
  "property_name": "texture"
}
```

## Successful Result

`type`, `type_id`, `hint`, `hint_string`, `usage`, `editable`,
`current_value`, `class_default` (all JSON-safe), plus node
identity fields. Unknown properties return a structured
"Property not found" failure.

---


# Tool: get_node_children_summary

## Purpose

Lightweight child listing for one node: `{name, node_type, index,
child_count}` per child, without full subtree serialization.
Preferred over `get_scene_tree` for large scenes. Bounded at 200
children with `truncated`/`omitted` reporting.

## Request / Result

Request takes `node_path`. Result: `total_children`, `truncated`,
`omitted`, `children`, plus node identity fields.

---


# Tool: assign_resource_to_property

## Purpose

Loads a `res://` resource and assigns it to one property of a node
as a single undoable `EditorUndoRedoManager` property action (undo
restores the previous value). This is what makes `set_properties`
useful in real scenes: textures, materials, audio, curves.

## Request

```json
{
  "action": "assign_resource_to_property",
  "reason": "Give the sprite its texture.",
  "node_path": "Player/Sprite2D",
  "property_name": "texture",
  "resource_path": "res://icon.svg"
}
```

## Validation (Godot side, in order)

1. `node_path`/`property_name`/`resource_path` present and valid
   (resource path: `res://` auto-prefix, no traversal, no
   backslashes; any resource extension).
2. Node exists; property exists and is editable.
3. Resource file exists, loads, and is a Resource.
4. Idempotent case: the same resource path already assigned is a
   no-op success.

## Success response

```json
{
  "action": "assign_resource_to_property",
  "message": "Resource assigned successfully in the Godot editor.",
  "node_path": "Player/Sprite2D",
  "node_name": "Sprite2D",
  "property_name": "texture",
  "resource_path": "res://icon.svg",
  "previous_resource_path": "",
  "changed": true,
  "verified_assignment": true,
  "success": true,
  "undoable": true
}
```

`verified_assignment` reads the property back and compares
resource paths.

---


# Tool: get_resource_info

## Purpose

Read-only identity check for one resource file answered from the
real loaded resource: `resource_class`, `resource_name`,
`local_to_scene` (read defensively; `null` for subclasses that do
not expose it), and `resource_path`. Works headless.

---


# Tool: list_project_files

## Purpose

Bounded, filterable listing of project files under a `res://`
prefix using plain `DirAccess` traversal, so it works headless and
in the editor. Editor-internal directories (`.godot`, `.git`, and
any dot-directory) are always excluded.

## Request

```json
{
  "action": "list_project_files",
  "reason": "Find the project's scripts.",
  "prefix": "addons/Execution_Agent/bridge",
  "extensions": ["gd"],
  "limit": 50
}
```

- `prefix` optional (res:// paths below it); `extensions` optional
  (dot-normalized, e.g. `".gd"` equals `"gd"`); `limit` optional
  (1-500, default 100). Walks are additionally capped (5000 files)
  with `walk_truncated` reporting.

## Successful Result

`files` (sorted `res://` paths), `total_matches`, `truncated`,
`limit`, `walked_files`, `walk_truncated`.

---


# Tool: search_in_files

## Purpose

Bounded case-insensitive text search across project text files
(default extensions: gd, tscn, tres, cfg, json, md, txt). Scanning
is bounded (500 files, first bounded region of very large files);
results carry `{file_path, line_number, snippet}` per match with
`total_matches`, `truncated`, `scanned_files`, and `scan_cap`
reporting. Never mistaken for exhaustive: a hit at the limit or a
hit scan cap sets `truncated`.

## Request

```json
{
  "action": "search_in_files",
  "reason": "Find where route_request is called.",
  "query": "route_request",
  "extensions": ["gd"],
  "limit": 3
}
```

---


# Tool: get_global_class_list

## Purpose

Lists the project's `class_name` globals. `ScriptServer` is not
exposed to GDScript, so this reads the editor's own global class
cache (`.godot/global_script_class_cache.cfg`) — the same data the
editor maintains — and reports `{class_name, script_path,
base_class}` entries sorted by name. A missing cache is a
structured failure (no globals or no editor scan yet). Works
headless.

---


# Tool: get_input_map

## Purpose

Reports the project's configured input actions
(`{action, deadzone, events}` with `InputEvent.as_text()` event
descriptions) answered from the live InputMap, sorted by action
name. Works headless. Note: inside the running editor the InputMap
additionally contains editor-internal actions; a running game
reports only project actions.

---


# Tool: run_scene

## Purpose

Runs the game from the editor (EditorInterface play
methods) so the human can watch it live. Without
`scene_path` the project's MAIN scene runs; with a
scene_path that scene runs instead. Verified by
`is_playing_scene()` / `get_playing_scene()` read-back.

IMPORTANT: to read the game's output and errors
autonomously, use `run_scene_offline` instead - the
engine's built-in debugger consumes a game's output and
error messages before editor plugins can see them, so
editor-side output capture is not possible.

## Request

```json
{"action": "run_scene", "reason": "Run the level.",
 "scene_path": "res://scenes/level.tscn"}
```

- `scene_path` optional (.tscn, strict path rules);
  omit for the main scene.
- Refuses when a game is already running (call
  `stop_run` first).

## Success response

`success`, `playing_scene`, `requested_scene`,
`is_playing: true`, `changed: true`, `verified_run: true`,
`undoable: false`.

## Failure response

```json
{"error": "A game is already running (res://...). Call stop_run first.",
 "success": false}
```

---


# Tool: stop_run

## Purpose

Stops the game run from the editor. Idempotent: with
nothing playing it is a no-op success. Verified by
`is_playing_scene()` read-back. Requires the running
editor.

## Success response

`success`, `stopped_scene` (when one was running),
`changed`, `is_playing: false`, `verified_stop: true`,
`undoable: false`.

---


# Tool: get_runtime_output

## Purpose

Reads entries captured by the plugin's debugger capture
(registered via `EditorPlugin.add_debugger_plugin`).

ENGINE LIMITATION (verified on 4.7.2): a game's built-in
output and error messages are consumed by the editor's
own debugger and are NOT routed to editor debugger
plugins. This tool therefore only ever sees messages a
game sends under custom capture prefixes via
`EngineDebugger.send_message`. For autonomous output
reading use `run_scene_offline`.

## Request / Result

Request: optional `clear` (boolean, default false; true
empties the buffer after the read). Result: `entries`
(list of `{kind, text, session_id}`), `count`, `dropped`,
`buffer_full` (bounded at 500), `is_playing`,
`playing_scene`, `cleared`.

---


# Tool: open_scene

## Purpose

Opens a scene file, making it the edited scene
(editor-native). Guarded: refuses while the current
scene has unsaved changes (silent loss prevention), and
the result warns that all node paths from the previous
scene are invalid after the switch. Verified by the
edited root's `scene_file_path` read-back.

## Request

```json
{"action": "open_scene", "reason": "Work in the level now.",
 "scene_path": "res://scenes/level.tscn"}
```

## Success response

`success`, `scene_path`, `previous_scene`, `root_name`,
`root_type`, `context_switched: true`, `changed: true`,
`verified_open: true`, `undoable: false`. Idempotent
when the requested scene is already the edited scene.

## Failure response

```json
{"error": "open_scene: the currently edited scene has unsaved changes (res://...). Call save_scene first.",
 "success": false}
```

---


# Tool: save_scene_as

## Purpose

Editor-native save-as of the currently edited scene to a
NEW res:// path. Existing files are never overwritten.
`EditorInterface.save_scene_as()` returns void, so the
write is verified entirely by read-back: the file exists
and the edited scene's path switched to the new location.
Requires the running editor.

## Request / Result

Request: `scene_path` (.tscn, strict path rules).
Result: `success`, `scene_path`, `previous_path`,
`scene_name`, `changed: true`, `verified_write: true`,
`undoable: false`.

---


# Tool: set_project_settings

## Purpose

Sets one or more project settings in the live
ProjectSettings (display, physics, window, etc.).
Not undoable: every changed key's previous value is
reported in the result so the human can revert, and
values persist to project.godot when the editor saves
the project. Sensitive keys (password/token/secret/
api_key/credential/private_key) are rejected outright.
Works headless.

## Request

```json
{"action": "set_project_settings",
 "reason": "Switch the game to 1280x720.",
 "settings_json": "{\"display/window/size/viewport_width\": 1280}"}
```

- 1-10 settings per call; existing keys are coerced to
  their current type before validation.

## Success response

`settings` (list of `{key, had_previous, previous_value,
new_value, verified}`), `setting_count`, `changed: true`,
`verified_settings`, `undoable: false`.

---


# Tool: create_resource

## Purpose

Creates a NEW file-backed `.tres` resource of the
requested Resource type (ClassDB-validated: must be an
instantiable Resource, never a Node) with type-aware
property application (same serialization rules as
`set_properties`). Unknown property names are rejected
explicitly (`Object.set` would silently ignore them).
Never overwrites; creates parent directories; verified
by loading the file back. Works headless. Not undoable.

## Request

```json
{"action": "create_resource",
 "reason": "The enemy AI needs its curve.",
 "resource_path": "res://resources/patrol.tres",
 "resource_type": "Curve",
 "properties_json": "{\"max_value\": 10.0}"}
```

## Success response

`success`, `resource_path`, `resource_type`,
`property_count`, `changed: true`, `verified_write: true`,
`undoable: false`.

---


# Tool: delete_resource

## Purpose

Deletes an existing `.tres` or `.res` resource file and
verifies absence by read-back. Restricted to resource
files only: directories, scenes (.tscn), scripts (.gd),
project.godot, and imported assets are refused
structurally, so the model can never delete them through
this action. File deletion is not undoable; scenes or
resources referencing the path will report a missing
dependency. Works headless.

## Request

```json
{"action": "delete_resource",
 "reason": "The root copy is the stale one.",
 "resource_path": "res://capsule_shape.tres"}
```

## Success response

`success`, `resource_path`, `message`,
`verified_deleted: true`, `verified_absent: true`,
`changed: true`, `undoable: false`.

A second delete of the same path fails with
`resource not found` (honest failure, not idempotent
success).

---


# Tool: rename_resource

## Purpose

Renames or moves an existing `.tres`/`.res` file to a new
res:// path in one deterministic operation. Missing
destination folders are created; an existing destination
file or folder is never overwritten (structured failure
instead). Verified by read-back: destination exists AND
source is absent. References to the old path are NOT
rewritten (unlike `rename_script`) - the result message
says so, and `scan_project_issues` will report the
missing dependencies until the model updates the
referencing files. Not undoable. Works headless.

## Request

```json
{"action": "rename_resource",
 "reason": "The resource belongs under resources/.",
 "resource_path": "res://capsule_shape.tres",
 "new_resource_path": "res://resources/capsule_shape.tres"}
```

## Success response

`success`, `resource_path` (old), `new_resource_path`,
`verified_moved: true`, `verified_destination_exists: true`,
`verified_source_absent: true`, `changed: true`,
`undoable: false`.

---


# Tool: create_directory

## Purpose

Creates a folder inside the project, nested parents
included. Fails when the path already exists as a folder
or as a file, so an existing folder is never mistaken for
a created one (the agent previously had no way to create
a folder explicitly; `create_resource` creates parents
implicitly). Verified by read-back. Not undoable. Works
headless.

## Request

```json
{"action": "create_directory",
 "reason": "The project needs a resources folder.",
 "directory_path": "res://resources"}
```

## Success response

`success`, `directory_path`, `verified_created: true`,
`changed: true`, `undoable: false`.

---


# Tool: run_scene_offline

## Purpose

Python-side tool (never touches the bridge): runs a scene
as a HEADLESS subprocess via the configured engine binary
(`GODOT_BINARY_PATH` / `PROJECT_PATH` in
`config/settings.py`, env-overridable) and returns its
exit code, stdout, and stderr. This is the autonomous
playtest tool: after creating or editing scripts and
scenes, run the scene offline, read
`script_errors_detected` / stderr backtraces, fix, and
re-run - a full behavioral feedback loop with no editor
and no human in the loop. A scene that outlives the
timeout is killed and reported as timed out, never as
successful. Output is bounded (tail) with truncation
flags.

## Request

```json
{"action": "run_scene_offline",
 "reason": "Check the probe scene for errors.",
 "scene_path": "res://scenes/probe_run.tscn",
 "timeout": 30}
```

## Successful Result

```json
{
  "action": "run_scene_offline",
  "scene_path": "res://scenes/probe_run.tscn",
  "timeout_seconds": 30,
  "timed_out": false,
  "exit_code": 0,
  "duration_s": 0.42,
  "stdout": "...",
  "stdout_truncated": false,
  "stderr": "ERROR: ...
   at: push_error ...",
  "stderr_truncated": false,
  "script_errors_detected": false,
  "success": true
}
```

`script_errors_detected` is true when the stderr
contains "SCRIPT ERROR" entries.

---


# Tool: reparent_node

## Purpose

Moves an existing node under a different parent.

---

## Required Input

    node_path
    new_parent_path

Example:

    {
      "node_path": "CharacterBody2D/FinalTestEnemy",
      "new_parent_path": "CharacterBody2D/PersistentEnemy"
    }

---

## Recommended Resolution Sequence

For a request such as:

    Move FinalTestEnemy under PersistentEnemy.

A robust sequence is:

1. Find `FinalTestEnemy` using `find_nodes`.
2. Find `PersistentEnemy` using `find_nodes`.
3. Use returned exact paths.
4. Call `reparent_node`.

Example source search result:

    CharacterBody2D/FinalTestEnemy

Example destination search result:

    CharacterBody2D/PersistentEnemy

Then the operation uses:

    {
      "node_path": "CharacterBody2D/FinalTestEnemy",
      "new_parent_path": "CharacterBody2D/PersistentEnemy"
    }

---

## Successful Result

Example:

    {
      "action": "reparent_node",
      "message": "Node reparented successfully in the Godot editor.",
      "new_parent_path": "CharacterBody2D/PersistentEnemy",
      "node_name": "FinalTestEnemy",
      "node_path_before": "CharacterBody2D/FinalTestEnemy",
      "success": true,
      "undoable": true
    }

After reparenting, the old path should not be assumed to remain valid.

The new hierarchy may need to be inspected if another operation depends on the node's new exact path.

---

# Tool: get_node_properties

## Purpose

Returns the editable properties of an existing node in the currently
edited scene.

This is a read-only inspection tool; it never mutates the scene.

---

## Required Input

    node_path

Example:

    {
      "node_path": "CharacterBody2D/TestSprite"
    }

---

## Successful Result

Example shape:

    {
      "success": true,
      "action": "get_node_properties",
      "node_path": "CharacterBody2D/TestSprite",
      "node_name": "TestSprite",
      "node_type": "Sprite2D",
      "property_count": 2,
      "properties": {
        "position": { "type": "Vector2", "x": 100.0, "y": 200.0 },
        "visible": true
      }
    }

Property values are serialized by the Godot bridge into
JSON-compatible structures.

---

## Node Not Found

A missing node returns a structured failure of the standard form:

    {
      "success": false,
      "error": "..."
    }

Recovery: locate the node with `find_nodes`, then retry with the
returned exact path.

---

# Tool: get_node_property

Inspects a single property of a single node so the agent can read a
precise, already-known value without re-requesting the entire property
list (which it would do with `get_node_properties`). It is the
single-value counterpart to `get_node_properties` and, like it, is a
read-only inspection action.

- Provider: Godot bridge (`AIAgentPropertyTools.get_node_property_from_request`).
- Batchable: yes — may appear as a batch item (read-only, no boundary).
- Mutation: no.

## Parameters

| Field           | Type   | Required | Notes                                                                 |
|-----------------|--------|----------|-----------------------------------------------------------------------|
| `node_path`     | `str`  | yes      | Editor-relative path (e.g. `"."` for the edited root, `"Player"`).    |
| `property_name` | `str`  | yes      | An editor-visible readable property, or the special scene-tree-visible `Node.name` attribute. |

Both must be non-empty; blank/whitespace strings are rejected by the
agent-side `validate_agent_action` check before the bridge is called.

## Response (success)

Returned verbatim from the bridge:

    {
      "success": true,
      "action": "get_node_property",
      "node_path": "<input node_path>",
      "node_name": "<resolved node name>",
      "node_type": "<resolved node type>",
      "property_name": "<input property_name>",
      "property_type": "<type string>",
      "property_type_id": <int>,
      "editable": <bool>,
      "value": { "type": "<type string>", ... }
    }

`value` is normalized via `AIAgentVariantSerializer` into a JSON-
compatible structure. Scalar values are emitted directly; compound values
carry the serializer's existing type-specific JSON structure.

## Errors

- Missing or blank `node_path` / `property_name` → rejected client-side
  by `validate_agent_action`
  (`"requires non-empty field(s): <field>"`).
- Node not found → `{"success": false, "error": "Node not found: <path>"}`.
- Unsupported property →
  `{"success": false, "error": "Property not found: <property> on node <name>"}`.

`name` is readable for every `Node`, even though Godot omits it from the
editor-property enumeration. It is returned as a read-only `StringName`;
use `rename_node` for changes so normal undo behavior is preserved.

All errors are the standard structured-failure form
(`{"success": false, "error": "..."}`); a bridge failure is propagated
to the agent unchanged (no exception wrapping, no partial execution).

Recovery: locate the node with `find_nodes`, then retry with the
returned exact path.

---

# Tool: validate_node_type

## Purpose

Read-only pre-flight check for node-type dependent operations such
as `create_node`. The Godot bridge answers from the actual
`ClassDB` of the running editor, so the result is authoritative.

Use before creating a node whenever the exact Godot class name is
not certain, instead of guessing type names or retrying failed
`create_node` calls with different spellings.

---

## Required Input

    node_type

Example:

    {
      "node_type": "CharacterBody2D"
    }

---

## Successful Result

The tool call succeeds whenever the bridge could answer; the
`valid` field carries the answer:

    {
      "success": true,
      "action": "validate_node_type",
      "node_type": "CharacterBody2D",
      "valid": true,
      "exists": true,
      "is_node_class": true,
      "can_instantiate": true,
      "parent_class": "PhysicsBody2D",
      "message": "'CharacterBody2D' is a valid, instantiable node type."
    }

Field semantics:

- `exists`: the name is a registered Godot class.
- `is_node_class`: the class inherits from `Node`.
- `can_instantiate`: the class can be instantiated directly
  (abstract bases such as `CanvasItem` are `false`).
- `valid`: `exists` AND `is_node_class` AND `can_instantiate`.
- `node_type`: the requested type after whitespace trimming.
- `parent_class`: the direct Godot parent class (`""` when the
  type does not exist).

A type that exists but is not usable for node creation (for
example `Resource`, which is not a Node class, or `CanvasItem`,
which is abstract) returns `"valid": false` with an explanatory
`message`, not a failed tool call.

---

## Validation Failure

A missing or empty `node_type` returns the standard structured
failure:

    {
      "success": false,
      "error": "validate_node_type requires node_type."
    }

---

## Limitations

`ClassDB` covers native Godot classes only. Script-defined
(`class_name`) custom node types are not validated by this tool
yet.

---

# Tool: list_available_node_types

## Purpose

Lists bounded candidates from the running editor's `ClassDB` for native,
instantiable Godot `Node` classes. Use it to discover plausible names,
then use `validate_node_type` on an exact candidate before `create_node`.
It is read-only and batchable.

## Parameters

All parameters are optional.

| Field | Type | Notes |
|---|---|---|
| `inherits_from` | `str` | Restrict to this class and its descendants. Must name a registered `Node` class. |
| `name_contains` | `str` | Case-insensitive substring filter for the class name. |
| `limit` | `int` | Maximum returned names, from 1–100. Defaults to 50. |

Unfiltered queries are allowed, but the result is still bounded. Supplied
string filters must be non-empty after trimming.

## Successful Result

    {
      "success": true,
      "action": "list_available_node_types",
      "inherits_from": "Node2D",
      "name_contains": "body",
      "limit": 50,
      "total_matches": 2,
      "truncated": false,
      "node_types": ["CharacterBody2D", "StaticBody2D"]
    }

`node_types` is alphabetical and contains only native `Node` classes
that `ClassDB` reports as directly instantiable. `total_matches` is the
number before applying `limit`; `truncated` is true precisely when more
matches exist than were returned. A successful no-match result has
`total_matches: 0` and `node_types: []`.

## Errors

Invalid `inherits_from` filters, blank supplied filters, and limits
outside 1–100 return `{"success": false, "error": "..."}`. An
`inherits_from` value that names a non-Node class is invalid rather than
a no-match result.

## Limitations

Only native `ClassDB` classes are listed. Script-defined `class_name`
types are deliberately outside this tool's scope, and no ClassDB
metadata beyond candidate names is exposed.

---

# Tool: list_node_signals

## Purpose

Lists the signals actually available on one node in the currently edited
scene, from the node's real reflection data (`Node.get_signal_list()`).
It includes built-in and inherited signals. Use it to determine whether
a named signal exists on a node before attempting any future connection
work. It is read-only and batchable.

## Parameters

| Field | Type | Notes |
|---|---|---|
| `node_path` | `str` | Required, non-empty. Relative to the edited scene root; `"."` is the scene root. |

## Successful Result

    {
      "success": true,
      "action": "list_node_signals",
      "node_path": "Player",
      "node_name": "Player",
      "node_type": "Area2D",
      "total_signals": 31,
      "signals": [
        {
          "name": "area_entered",
          "args": [
            {"name": "area", "type": "Object", "type_id": 24}
          ]
        }
      ]
    }

`signals` is sorted alphabetically by signal name and is deterministic.
Each entry carries the signal `name` and its argument list; each argument
carries `name`, Godot `type` string, and numeric `type_id`. No other
metadata is exposed.

## Errors

A missing or blank `node_path`, a disallowed absolute path, and a
nonexistent node return the standard structured failure form
`{"success": false, "error": "..."}`. Missing-node failures are
produced by the same node-resolution helper used by the property tools.

## Limitations

The result reflects Godot's reflection API only. Script-defined signals
appear only if the running node actually exposes them through
`get_signal_list()`. No connection state is exposed.

## Contract decision

The original roadmap draft also proposed an optional
`include_connections` flag. It was intentionally **not** implemented.
The final request contract is `node_path` only, and the tool reports
signal definitions, not connection state. Connection inspection can be
considered separately later if there is a demonstrated need. This is a
deliberate scope reduction, not a missing feature: the current goal is
reliable signal discovery, not signal wiring inspection.

---

# Tool: list_node_groups

## Purpose

Reports the groups a single node in the currently edited scene is
actually a member of, from the node's real instance state
(`Node.get_groups()`). Use it to answer: which groups is this node in,
is this node a member of group X, does this node have any groups.
It is read-only and batchable.

## Parameters

| Field | Type | Notes |
|---|---|---|
| `node_path` | `str` | Required, non-empty. Relative to the edited scene root; `"."` is the scene root. |

## Successful Result

    {
      "success": true,
      "action": "list_node_groups",
      "node_path": "Player",
      "node_name": "Player",
      "node_type": "CharacterBody2D",
      "total_groups": 2,
      "groups": ["characters", "players"]
    }

`groups` is sorted alphabetically and is deterministic. A node with no
groups is a successful result with `total_groups: 0` and `groups: []`.

## Errors

A missing or blank `node_path`, a disallowed absolute path, and a
nonexistent node return the standard structured failure form
`{"success": false, "error": "..."}` via the shared node-resolution
helper.

## Limitations

Group membership is instance state. No group owners, project-wide
group lists, group definitions, or editor metadata are exposed, and no
mutation of group membership exists in this tool.

---

# Tool: count_nodes

## Purpose

Counts the nodes in the currently edited scene matching the same filter
semantics as `find_nodes`, without returning the node list. Use it when
only the number is needed, e.g. "how many Enemy nodes are in the
scene?", "are there exactly 5 enemies?", "do we have at least 3 trigger
areas?". It is read-only and batchable.

The distinction from `find_nodes`:

    find_nodes  -> I need the matching nodes.
    count_nodes -> I only need to know how many.

Do not use screenshots or visual reasoning for structural counts;
`count_nodes` provides the deterministic answer.

## Parameters

All parameters are optional; omitted fields do not filter.

| Field | Type | Notes |
|---|---|---|
| `node_name` | `str` | Node name filter. |
| `node_type` | `str` | Exact Godot class name filter (`get_class()` equality). |
| `parent_path` | `str` | Restrict counting to this node's subtree. Must resolve to an existing node. |
| `name_match` | `str` | `exact` (default), `contains`, `starts_with`, `ends_with`. Case-insensitive. |

## Successful Result

    {
      "success": true,
      "action": "count_nodes",
      "count": 3,
      "node_name_filter": "Enemy",
      "node_type_filter": "Area2D",
      "parent_path_filter": "Enemies",
      "name_match": "exact"
    }

The field name is `count`, matching the existing `find_nodes` result
convention; no competing name is used. Zero matches is a successful
result with `count: 0`. The matching node list is never returned.

## Errors

An invalid `name_match` mode returns the shared structured error
(`Invalid name_match mode: ...`). A `parent_path` that does not resolve
returns the existing `Parent node not found: ...` failure. All failures
use the standard `{"success": false, "error": "..."}` form.

## Limitations

The count reflects only the currently edited scene, as with
`find_nodes`. There is no `include_root` parameter; the edited scene
root itself is never counted. This tool reports state only; completion
declaration logic does not belong to this tool.

---

# Tool: find_nodes_by_script

## Purpose

Finds the nodes in the currently edited scene whose attached script
matches the requested script resource path, by inspecting each node's
live attached script (`Node.get_script()`) during a real traversal.
Use it for questions like "which nodes use player.gd?". It is
read-only and batchable.

The architectural distinction remains:

    find_nodes             -> general name/type search
    count_nodes            -> aggregate count
    find_nodes_by_script   -> script-attachment search

## Parameters

| Field | Type | Notes |
|---|---|---|
| `script_path` | `str` | Required, non-empty. The script resource path to match. |

## Script path semantics

Matching is against the canonical Godot resource path of the attached
script (e.g. `res://scripts/player.gd`). A request without the
`res://` prefix is deterministically normalized by prepending it, so
`scripts/player.gd` and `res://scripts/player.gd` are equivalent.
Matching is exact: no fuzzy matching, regex, filename-only guessing,
or filesystem scanning is performed.

## Successful Result

    {
      "success": true,
      "action": "find_nodes_by_script",
      "script_path": "res://scripts/player.gd",
      "count": 2,
      "nodes": [
        {
          "name": "Player",
          "node_type": "CharacterBody2D",
          "path": "Player",
          "is_root": false
        }
      ]
    }

`nodes` reuses the exact `find_nodes` node representation and the same
deterministic traversal ordering. A zero-match script is a successful
result with `count: 0` and an empty `nodes` list, not an error.

## Errors

A missing or blank `script_path` returns the standard structured
failure form `{"success": false, "error": "..."}`.

## Limitations

Only direct script attachment is inspected. Script inheritance,
tool/export metadata, and filesystem-wide script discovery are outside
this tool's scope.

---

# Tool: find_nodes_by_group

## Purpose

Finds the nodes in the currently edited scene that are members of the
requested group, by inspecting each node's live group membership
(`Node.is_in_group()`) during a real traversal. Use it for questions
like "which nodes are in the enemies group?". It is read-only and
batchable.

The architectural distinction remains:

    find_nodes             -> general name/type search
    count_nodes            -> aggregate count
    find_nodes_by_script   -> script-attachment search
    find_nodes_by_group    -> exact group-membership search
    list_node_groups       -> groups belonging to one specific node

## Parameters

| Field | Type | Notes |
|---|---|---|
| `group_name` | `str` | Required, non-empty. The exact group name to match. |

## Group-name semantics

Matching is **exact and case-sensitive**, preserving Godot's own
group-name identity: `enemies` matches only `enemies`, never `enemy`,
`Enemies`, or `hostile_enemies`. No case-insensitive, contains, fuzzy,
regex, or wildcard matching is performed. Zero matches are a
successful result, not an error.

## Successful Result

    {
      "success": true,
      "action": "find_nodes_by_group",
      "group_name": "enemies",
      "count": 2,
      "nodes": [
        {
          "name": "Enemy",
          "node_type": "Area2D",
          "path": "Enemy",
          "is_root": false
        }
      ]
    }

`nodes` reuses the exact `find_nodes` node representation and the same
deterministic traversal ordering. A node belonging to multiple groups
appears when querying each of those groups.

## Errors

A missing or blank `group_name` returns the standard structured
failure form `{"success": false, "error": "..."}`.

## Limitations

Only direct live group membership is inspected. No group creation or
removal, no project-wide group discovery, no multi-group boolean
expressions, and no group metadata are exposed.


# Tool: get_project_settings

## Purpose

Reads specific settings from the live Godot `ProjectSettings` state. It never
dumps the whole settings database: the agent must ask for exact setting
names and/or a bounded prefix. Use it for questions like "what is the
viewport width?", "what renderer is configured?", "what is the main scene?".

This is the project-level counterpart to the structural scene-inspection
tools. It is read-only and batchable.

## Parameters

At least one of `setting_names` or `prefix` must be provided and non-empty.
Both may be provided; they are treated as additive filters.

| Field | Type | Notes |
|---|---|---|
| `setting_names` | `list[str]` | Exact setting keys to look up. Duplicates are deduped; blank entries are dropped. |
| `prefix` | `str` | Return settings whose key begins with this prefix (bounded, lexicographically sorted). |
| `limit` | `int` | Max prefix matches to return (1-100, default 50). Ignored for exact-name requests. |

## Exact-name semantics

- Keys are matched exactly against `ProjectSettings.has_setting()`.
- Missing keys are reported in `missing`, not treated as a request failure.
- Settings whose name contains a sensitive token (`password`, `token`,
  `secret`, `api_key`, `credential`, `private_key`) are excluded from the
  response: only their names appear in `redacted`, never their values.

## Prefix semantics

- Uses `ProjectSettings.get_property_list()` and selects keys with
  `begins_with(prefix)`, then sorts lexicographically.
- Results are bounded by `limit` (default 50, max 100).
- `total_matches`, `returned_matches`, and `truncated` are reported.
- Exact-name matches are never removed by the prefix limit.

## Successful Result

    {
      "success": true,
      "action": "get_project_settings",
      "setting_names": ["display/window/size/viewport_width"],
      "prefix": "",
      "settings": {
        "display/window/size/viewport_width": 1280
      },
      "missing": [],
      "redacted": []
    }

A prefix query adds `total_matches`, `returned_matches`, `truncated`:

    {
      "success": true,
      "action": "get_project_settings",
      "setting_names": [],
      "prefix": "display/window/size/",
      "settings": { "...": "..." },
      "missing": [],
      "redacted": [],
      "total_matches": 8,
      "returned_matches": 8,
      "truncated": false
    }

Zero matches is a successful result with `settings: {}` and `missing: []`.
A request with neither filter returns a structured validation error.

## Errors

- Neither filter provided:
  `get_project_settings requires at least one of non-empty setting_names or prefix.`
- `setting_names` is not a list:
  `get_project_settings setting_names must be a list.`
- Invalid `limit`:
  `get_project_settings limit must be an integer from 1 to 100.`

All failures use the standard `{"success": false, "error": "..."}` form.

## Serialization

Values are serialized through the project's shared
`ai_agent_variant_serializer.gd`. Integers, floats, booleans, strings,
arrays, and dictionaries are represented as plain JSON-compatible values.
Godot Object values are converted to the serializer's safe representation
rather than being blindly JSON-encoded.

## Limitations

Reads only the live `ProjectSettings` runtime state; the `project.godot`
file is never parsed manually. No project-setting mutation is provided.
Sensitive-setting protection covers setting names only (values are never
exposed); it is a small deterministic filter, not a secret-detection
system. Completion-declaration logic does not belong to this tool.

---

---

# Tool: list_autoloads

## Purpose

Lists the project's configured autoload entries from live Godot
`ProjectSettings`. It is read-only and batchable.

## Parameters

None.

## Successful Result

    {
      "success": true,
      "action": "list_autoloads",
      "count": 1,
      "autoloads": [
        {
          "name": "GameState",
          "path": "res://game_state.gd",
          "resource_target": "*res://game_state.gd"
        }
      ]
    }

Entries are sorted by autoload name. The leading `*` used by Godot to mark
script autoloads is removed from `path` and preserved in
`resource_target`. Empty projects return a successful empty list.

## Limitations

The tool reads `ProjectSettings.get_property_list()` and does not parse
`project.godot`, scan files, infer autoloads, or mutate project settings.

---

# Tool: get_editor_state

## Purpose

Reports bounded current state from the running Godot editor. It is
read-only and batchable.

## Parameters

None.

## Successful Result

The response includes whether an edited scene exists, its path/name/type,
open scene paths, selected node name/type/path entries, playing-scene state,
and a selection count. Selected node paths are relative to the edited scene
when possible.

## Limitations

The implementation uses the injected `EditorInterface`; it does not scrape
editor UI text, screenshots, or arbitrary editor internals. A normal
headless `SceneTree` process returns an explicit editor-unavailable error.
Editor mode/context beyond the stable APIs listed above is intentionally not
invented.

---

# Tool: list_scenes_in_project

## Purpose

Lists scene resources known to the Godot editor filesystem. It is read-only
and batchable.

## Parameters

None.

## Successful Result

    {
      "success": true,
      "action": "list_scenes_in_project",
      "count": 1,
      "scenes": ["res://game_scene.tscn"],
      "scanning": false,
      "importing": false
    }

Paths are filtered by the editor's `PackedScene` resource type and sorted
lexicographically. The tool does not instantiate or open scenes.

## Limitations

The editor resource filesystem is authoritative for this tool. While it is
scanning or importing, the tool returns a structured not-ready failure
instead of silently returning an incomplete list. Normal headless runtime
processes do not provide this editor cache.

---

# Tool: get_undo_history_summary

## Purpose

Summarizes current editor undo/redo availability without performing undo or
redo. It is read-only and batchable.

## Parameters

None.

## Successful Result

The response includes aggregate `undo_available`, `redo_available`, and
`current_action_name` fields, plus per-history summaries for the global and
edited-scene histories where available. Per-history summaries include
`history_id`, action count, undo/redo flags, and the current action name.

## Limitations

The tool uses the injected `EditorUndoRedoManager` and does not expose raw
undo objects or mutate history. A normal headless `SceneTree` process cannot
obtain the plugin-owned manager and returns an explicit unavailable error.
Separate undo/redo mutation tools remain future work.

---

# Tool: delete_node

## Purpose

Deletes an existing node from the currently edited scene.

The Godot editor handles this as an undoable
`EditorUndoRedoManager` action.

---

## Required Input

    node_path

Example:

    {
      "node_path": "CharacterBody2D/TestEnemy"
    }

---

## Successful Result

Example:

    {
      "success": true,
      "action": "delete_node",
      "message": "Node deleted successfully in the Godot editor.",
      "node_path": "CharacterBody2D/TestEnemy",
      "undoable": true
    }

After deletion, the path is no longer valid. Do not reuse a deleted
node's path without re-inspecting the scene.

---

## Validation Failure

A missing `node_path` or an unresolvable node returns a structured
failure of the standard form:

    {
      "success": false,
      "error": "..."
    }

Recovery: locate the node with `find_nodes`, obtain the exact path,
and retry.

---

# Tool: duplicate_node

## Purpose

Duplicates an existing node including its subtree, placing the copy
under a new parent with the specified name.

The operation is editor-native and undoable. Ownership of the entire
duplicated subtree is set to the edited scene root so the copy is
saved with the scene.

---

## Required Input

    node_path
    new_parent_path
    new_name

Example:

    {
      "node_path": "CharacterBody2D/PersistentEnemy",
      "new_parent_path": "CharacterBody2D",
      "new_name": "EnemyCopy"
    }

---

## Validation Rules

- Duplicating the edited scene root is not supported.
- A node cannot be duplicated under itself or one of its own
  descendants.
- The new parent must exist and be resolvable.

Failure returns the standard structured form, e.g.:

    {
      "success": false,
      "error": "New parent node not found: CharacterBody2D/MissingParent"
    }

---

## Successful Result

Example:

    {
      "success": true,
      "action": "duplicate_node",
      "message": "Node duplicated successfully in the Godot editor.",
      "node_name": "EnemyCopy",
      "actual_node_name": "EnemyCopy",
      "node_path_before": "CharacterBody2D/PersistentEnemy",
      "new_parent_path": "CharacterBody2D",
      "node_path_after": "CharacterBody2D/EnemyCopy",
      "name_collision_detected": false,
      "verified_exists": true,
      "verified_owned": true,
      "undoable": true
    }

Important:

The editor silently renames the new child if a sibling already has the
same name. `actual_node_name`, `node_path_after`, and
`name_collision_detected` report the authoritative result. Always
prefer `node_path_after` for subsequent operations.

---

# Tool: set_properties

## Purpose

Sets one or more editable properties on a node in the currently
edited Godot scene.

The Godot editor bridge validates all requested properties before
applying them as one undoable operation.

---

## Required Input

The decision carries a JSON string of property names to values:

    node_path
    properties_json

Example:

    {
      "node_path": "CharacterBody2D/TestSprite",
      "properties_json": "{\"position\": {\"type\": \"Vector2\", \"x\": 100, \"y\": 200}, \"visible\": true}"
    }

Python parses `properties_json` before dispatch; malformed JSON or
invalid values are rejected before any Godot call.

---

## Successful Result

Example:

    {
      "success": true,
      "action": "set_properties",
      "message": "Properties set successfully in the Godot editor.",
      "node_path": "CharacterBody2D/TestSprite",
      "properties": {
        "position": { "type": "Vector2", "x": 100.0, "y": 200.0 },
        "visible": true
      },
      "undoable": true
    }

The returned `properties` reflect what the bridge applied.

---

## Validation Failure

A missing or empty `node_path` / property set, or a property that
fails bridge-side validation, returns a structured failure of the
standard form:

    {
      "success": false,
      "error": "..."
    }

Recovery: inspect the node with `get_node_properties`, then retry with
valid property values.

---

# Tool: batch

## Purpose

Allows the model to propose a short, ordered sequence of actions that
execute in one host round-trip instead of one model call per action.

---

## Rules

- `actions` must contain 1 to `MAX_BATCH_SIZE` (currently 5) items;
  a larger batch is rejected outright, never silently truncated.
- Batch items reuse the exact same per-action schemas as standalone
  decisions and are validated identically.
- `final_answer`, `exit_session`, and nested `batch` actions are not
  valid batch items.
- Execution is sequential with a stop-on-first-failure boundary.
- If a batch stops early, skipped actions are recorded by
  `agent/boundary.py`. Python then blocks any later decision that
  attempts to resume a skipped mutation, including same-target
  parameter changes. Read-only recovery actions remain allowed.

---

## Decision Example

    {
      "action": "batch",
      "reason": "Create the node, then verify it exists.",
      "actions": [
        {
          "action": "create_node",
          "reason": "Create the test node.",
          "parent_path": ".",
          "node_type": "Node2D",
          "node_name": "BatchProbe"
        },
        {
          "action": "find_nodes",
          "reason": "Verify the created node.",
          "node_name": "BatchProbe"
        }
      ]
    }

---

## Successful Result

Example:

    {
      "action": "batch",
      "success": true,
      "batch_size": 2,
      "succeeded_count": 2,
      "failed_count": 0,
      "stopped_early": false,
      "stopped_at_index": null,
      "results": [ ...per-item tool results... ],
      "message": "Batch completed: 2/2 action(s) succeeded."
    }

---

## Early Stop

When an item fails, execution stops at that item and remaining items
are skipped:

    {
      "action": "batch",
      "success": false,
      "batch_size": 3,
      "succeeded_count": 1,
      "failed_count": 1,
      "stopped_early": true,
      "stopped_at_index": 2,
      "results": [ ...including skipped items flagged with "skipped": true... ],
      "message": "Batch stopped at action 2/3 after a failure; 1 action(s) were skipped. ..."
    }

Skipped actions must not be automatically resumed. Attempting to
resume one is rejected by Python before any Godot call, and the
rejection is returned as a tool-result-shaped observation.

---

# Tool: final_answer

## Purpose

Indicates that the agent believes the task is complete or cannot be recovered.

This is not a Godot editor operation.

It terminates the reasoning loop.

---

## Expected Fields

    final_answer
    reason

Example:

    {
      "action": "final_answer",
      "reason": "The requested node was successfully created.",
      "final_answer": "Successfully created Node2D node 'NestedTest' under 'CharacterBody2D/PersistentEnemy'."
    }

---

## Failure Final Answer

Example:

    {
      "action": "final_answer",
      "reason": "The requested parent node could not be found after inspection.",
      "final_answer": "Could not create the node because the requested parent does not exist in the current scene."
    }

The agent should not claim success unless a successful tool result supports that claim.

---

## Session Termination

The agent operates within a persistent `AgentSession` that spans multiple
user turns. Three distinct termination paths exist:

| Path | Trigger | Effect |
|------|---------|--------|
| `final_answer` | Model decision | Current turn ends. Session stays alive and prompts for next turn. |
| `exit_session` | Model decision | Entire session closes. No further turns are prompted. |
| `/exit` | Human CLI input | Host-level escape hatch. Session closes immediately. |

### final_answer

Use when the current user turn is complete. The session remains alive.

    {
      "action": "final_answer",
      "reason": "All requested operations are complete.",
      "final_answer": "Created the node and verified its properties."
    }

### exit_session

Use only when the entire persistent session is explicitly complete or
genuinely unrecoverable. Do NOT use `exit_session` merely because the
current task is complete — use `final_answer` for normal turn completion.

`exit_session` is a top-level decision only. It must never appear inside
a batch.

Required parameter:

    exit_summary

Example:

    {
      "action": "exit_session",
      "reason": "All work is done and the user has no further requests.",
      "exit_summary": "Session complete. All requested scene modifications were applied successfully."
    }

---

# Agent Decision Schema

The model produces a structured decision containing fields relevant to possible actions.

The observed decision structure includes fields such as:

    action
    reason
    final_answer
    node_name
    node_type
    parent_path
    name_match
    include_root
    node_path
    new_name
    new_parent_path
    properties_json
    actions
    exit_summary

Not every field is relevant to every action.

Unused fields may be `null`.

Example:

    {
      "action": "rename_node",
      "reason": "Rename the node using its exact path.",
      "final_answer": null,
      "node_name": null,
      "node_type": null,
      "parent_path": null,
      "name_match": null,
      "include_root": null,
      "node_path": "CharacterBody2D/TestEnemy",
      "new_name": "RenamedTestEnemy",
      "new_parent_path": null,
      "properties_json": null
    }

The model may omit fields or produce incomplete decisions.

Therefore the Python agent must not assume that model output is always valid.

---

# Decision Validation Principles

Before dispatching an action:

1. Determine the selected action.
2. Determine the fields required by that action.
3. Check whether required fields are present.
4. Apply conservative deterministic repair only when the repair is unambiguous.
5. Otherwise allow the reasoning loop to recover using observations.

The system should avoid silently inventing values.

---

# Constraint Repair Principles

Constraint repair exists to correct structural issues in model decisions.

It must not reinterpret the user's request beyond what is safe.

Good repair:

    The model searches for a node named explicitly by the user.
    The model omitted an irrelevant optional field.

Potentially dangerous repair:

    The user mentioned a destination parent.
    Therefore every node search should be scoped to that parent.

The second behavior can hide nodes and cause repeated failures.

Constraint repair should prefer preserving the model's intended operation.

---

# Failure Recovery Principles

When a tool returns `success: false`:

1. Read the error.
2. Identify what information is missing or invalid.
3. Select an action that can obtain or repair that information.
4. Avoid repeating the same invalid request.
5. Stop when further recovery would be speculative.

Examples:

## Missing Required Parameters

Error:

    create_node requires parent_path, node_type, and node_name.

Recovery:

- obtain missing parameters,
- validate the next decision,
- retry with materially improved input.

## Parent Not Found

Error:

    Parent node not found: PersistentEnemy

Recovery:

- search for `PersistentEnemy`,
- use the returned full path.

## Search Found Nothing

Result:

    {
      "success": true,
      "count": 0,
      "nodes": []
    }

Recovery:

- report that the node was not found,
- or perform broader inspection only when justified.

Do not confuse this with a failed tool request.

---

# Authoritative Data Rules

The Godot EditorPlugin is authoritative for:

- current scene hierarchy,
- node existence,
- node paths,
- node types,
- operation success,
- editor state visible to the bridge.

The Python model layer is not authoritative for scene state.

The model may propose:

    PersistentEnemy

but Godot determines whether that node exists and where it actually lives.

Whenever Godot returns an exact path, prefer that path.

---

# Future Tool Expansion

Implemented tools are documented in the `# Tool:` sections above.
`get_node_properties`, `delete_node`, `duplicate_node`, and
`set_properties` are no longer future work.

Future tools may include:

- `inspect_node`
- `attach_script`
- `inspect_script`
- `create_scene`
- `instantiate_scene`
- `save_scene`
- resource inspection operations

Every new tool should document:

1. purpose,
2. required input fields,
3. optional input fields,
4. validation behavior,
5. successful result structure,
6. failure structure,
7. path semantics,
8. recovery expectations,
9. undoability.

Do not add a new Godot operation without defining its structured protocol.

---

# Protocol Design Rule

The preferred contract is:

    Small action
    -> validated input
    -> editor-native execution
    -> structured observation
    -> agent reasoning

Avoid tools that require the model to provide large speculative structures when smaller inspect-and-act operations would work.

The protocol should support iterative reasoning.

It should not require the model to perfectly understand the entire scene before performing its first operation.

---

# Mutation Result Contract (Python side)

All seven scene mutations (`create_node`, `rename_node`,
`delete_node`, `reparent_node`, `duplicate_node`,
`set_properties`, `move_child`) are executed on the Godot side as editor-native,
undoable `EditorUndoRedoManager` actions. The Python side adds a
uniform contract layer over their results in `agent/mutation.py`:

1. **Classification.** An action is a mutation if and only if the
   action registry's `is_mutation` flag says so (`is_mutation_action()`).
   The registry, `agent/boundary.py` mutation metadata, and the
   classification layer are pinned to the same six-action set by
   contract tests.
2. **Result contract.** Every mutation tool result must be a dict
   containing a boolean `success` key (`validate_mutation_result()`).
   A contract violation is recorded as a failure, never as a
   success.
3. **Verification status.** Derived only from the bridge's own
   `verified_*` result fields (`classify_verification()`):
   - `failed` - the mutation reported failure, or any
     `verified_*` claim was false,
   - `verified` - success with at least one `verified_*` claim,
     all true,
   - `unverified` - success with no `verified_*` claims.
   `name_collision_detected` is informational and is not a
   verification claim. Verification status is never fabricated.
4. **Execution records.** Each mutation execution produces a
   frozen `MutationRecord` (action, mutation target from
   `agent/boundary.py`, success, verification status, bridge-
   reported `undoable`, error, turn/step, duration) and a
   `MutationTelemetry` entry, recorded by `execute_single_action()`
   on both standalone and batch paths, in addition to the existing
   tool-action telemetry.

Batch partial-failure semantics are unchanged: a batch stops at
the first invalid or failed sub-action, remaining sub-actions are
recorded as skipped, and skipped mutations remain blocked from
automatic resume by `agent/boundary.py`.

Undoability is a property of the Godot-side execution
(`EditorUndoRedoManager`); the Python layer only carries the
bridge's `undoable` reporting forward into records and telemetry.
No separate Python-side undo mechanism exists or is planned.


---

---

# Gemini Schema Compatibility for move_child

## Background

When `MoveChildAction` was added to the `AgentDecision` union, Gemini
began rejecting the full schema request with `400 INVALID_ARGUMENT`. The
confirmed root cause is that the provider cannot accept some
provider-incompatible JSON-schema constraint keywords that Pydantic emits
(`discriminator`, `minimum`, `maximum`, `minItems`, `maxItems`). The
permanent, provider-only fix in `make_gemini_schema_compatible()` is to
recursively convert `oneOf` to `anyOf` and remove `discriminator`,
`minimum`, `maximum`, `minItems`, and `maxItems` from the transformed
schema before it is sent to Gemini. Public Pydantic schemas and host-side
validation are unchanged.

`MoveChildAction` is kept in both the top-level `AgentDecision` union and
the nested `batch.actions` union in the Gemini-generated schema. To make
it structurally distinguishable, the Gemini adapter additionally injects
a Gemini-only `result_mode` field (enum `["move_child"]`) into the
transformed schema. This mirrors the existing `CountNodesAction` pattern
and is a structural-uniqueness workaround, not the 400 fix. The public
Pydantic schema is unchanged — `MoveChildAction` in
`agent/schemas.py` has no `result_mode` field; the field is injected only
in the Gemini-converted schema.

## Current state

- `MoveChildAction` is present in both the top-level union and the nested
  batch union in Gemini's schema.
- `AddToGroupAction` and `RemoveFromGroupAction` remain excluded from the
  nested batch union only (intentional, for structural overlap reasons).
- `result_mode: Literal["move_child"]` appears in Gemini's view of
  `MoveChildAction` properties/required.

## Viewed vs. sent

The system prompt describes `move_child` as a tool the model may use. The
Gemini response schema now includes `MoveChildAction` as a valid branch.
Both views are consistent. No structural exclusion of `MoveChildAction`
from Gemini's schema remains.

---

# Tool: scan_project_issues

## Purpose

Read-only project lint: bounded scan for mechanical problems a
mutation-heavy agent can cause. Works headless and in the editor
(plain file/ResourceLoader access, no editor state). Three
checks per file:

- `script_parse_error`: .gd fails a fresh detached parse AND
  the editor's own load also rejects it (a fresh parse of a
  script whose `class_name` is already registered in the
  running editor fails spuriously — duplicate global class —
  so parse failure alone is never reported).
- `scene_load_failed`: .tscn does not load as a PackedScene.
- `missing_dependency`: a scene dependency whose res:// path
  does not exist on disk. uid-form dependency strings like
  `uid://abc::::res://x.gd` are normalized to their res:// path
  first; a uid-only dependency with no res:// part cannot be
  verified and is skipped rather than falsely reported.

## Parameters

- `prefix` (optional): res:// sub-path; defaults to the whole
  project. A prefix that does not exist is a structured failure
  (same semantics as `list_project_files`).
- `limit` (optional, 1-100, default 50): bounds the reported
  issue list.

## Successful Result

`issues` (each with `issue_kind`, `file_path`, `detail`),
`total_matches`, `truncated`, `scanned_files`, `scan_cap` (500),
`walked_files`, `walk_truncated`. Check `truncated` and
`scanned_files` before assuming a short issue list means the
whole project was scanned.

Read-only; works headless and in the editor. Batchable.

---

# Tool: rename_script

## Purpose

Renames or moves an existing GDScript file and updates every
textual reference to its res:// path across project text files
(.gd, .tscn, .tres, .cfg, project.godot) in one deterministic
operation. Phased: (1) compute all replacements; (2) MOVE the
script file and its `.uid` sidecar first (GDScript `preload()`
resolves at parse time, so the target must exist before
parse-checking); (3) parse-gate affected .gd files
(regression-only: a file whose ORIGINAL content already failed
to parse is never made worse and does not block); (4) write all
reference updates with read-back verification. On any parse
regression the move is rolled back and nothing is written.

## Parameters

- `script_path` (required): existing res:// path ending in .gd.
- `new_script_path` (required): non-existing res:// path ending
  in .gd; missing parent directories are created.

## Successful Result

`old_path`, `new_path`, `changed_files` (per-file
`replacement_count` + `verified_write`), `total_reference_updates`,
`uid_renamed`, `verified_move`, `verified_load`,
`remaining_old_references`,
`verified_no_leftover_references`, and
`edited_scene_stale_script_nodes` (live nodes in the currently
edited scene still holding the OLD script attached — a disk
rename does not rewire live nodes; re-attach via attach_script
or reopen the scene). The project file walk is capped at 5000
files; a truncated walk refuses the rename rather than renaming
without seeing all references. `undoable: false`.

---

# Tool: find_replace_across_files

## Purpose

Replaces every occurrence of `old_string` with `new_string`
across multiple project text files in one deterministic,
parse-gated operation. Two-phase: all new content is computed
and parse-gated (regression-only, same rule as `rename_script`)
BEFORE any write; any parse regression or over-bound match set
refuses the WHOLE request with nothing written. Verified by
reading every file back and comparing against the exact
computed replacement — not a substring check, which false-alarms
when `new_string` contains `old_string` (e.g. "Node" →
"Node2D").

## Parameters

- `old_string` (required, non-empty), `new_string` (required,
  may be empty to delete occurrences; must differ from
  `old_string`).
- `extensions` (optional, default `["gd", "tscn", "tres"]`).
- `prefix` (optional): res:// sub-path.
- `max_files` (optional, 1-50, default 20): a request matching
  more files is refused entirely, never partially applied.

## Successful Result

`changed_files` (per-file `replacement_count` +
`verified_write`), `total_replacements`, `scanned_files`,
`skipped_large_files` (files over the 1 MiB scan cap),
`verified_no_leftover_matches`, and `open_scene_overlap` (files
currently open in the editor — modified on disk; the editor's
in-memory copies are not reloaded by this call). Not-found
anywhere is a structured failure pointing at `search_in_files`.
`undoable: false`.

---

---

# UI Observability Routes (plugin-internal)

These routes serve the agent observability UI (the "AI Agent"
bottom panel). They are NOT model-facing actions: they appear in
no AgentDecision schema, registry, or system prompt, and Python
calls them fire-and-forget from `agent/ui_reporter.py`. Unknown
event types are stored as generic rows so the two sides evolve
independently.

## POST /agent_event

Pushes one flat event to the plugin's state store. Requires a
non-empty string `event` field; anything else is a structured
failure. Recognized event types (all fields besides `event`
optional; `ts` unix seconds is added by the reporter):

| Event | Meaning / fields |
| --- | --- |
| `session_started` | resets timeline/metrics/chat; `session_id`, `model`. The mutation LEDGER survives (project-level audit trail: each agent CLI process emits session_started at startup) |
| `turn_started` | `turn`, `request_preview`, `mode` ("plan"/"act"); opens the turn's chat transcript (turn 1 announces itself at the module-level input, turns 2+ in begin_next_turn) |
| `request_sent` | status -> thinking; `turn`, `step`, `model` |
| `model_response` | usage + metrics only (no timeline row); `prompt_tokens`, `output_tokens`, `duration_ms` (null = unavailable, never fabricated) |
| `thinking` | the validated decision's `reason` (<=300 chars) + `action` + usage; feeds the activity timeline AND the turn's chat thinking stream |
| `tool_started` | `action`; `run_scene_offline` gets its own status; batch items carry `batch_index`/`batch_size` |
| `tool_finished` | `success`, `duration_ms`, `detail`; batch fields as above; mutations carry `verification`, `undoable`, `target`, `target_path` into the ledger (create_node synthesizes its target from parent_path/node_name) |
| `batch_started` / `batch_finished` | `batch_size`, `success` |
| `compaction` | `original_chars`, `summary_chars` |
| `blocked_action` / `validation_rejected` | attention rows with `action` + `reason`/`error` |
| `error` | fatal paths; `context`, `error` |
| `max_steps_reached` | attention row |
| `turn_completed` | `final_answer` completes the turn's Chat transcript |
| `session_ended` | `reason`; status -> session_ended |

## GET /agent_state

Read-only snapshot of the store: status, token totals, counters,
control-channel fields, and the bounded histories (events tail
of 50, ledger, chat turns, metrics). Used for live validation
and debugging; the panel reads the store directly, not this
route.

## Control channel: POST/GET /agent_input (UI-only)

Turns carry a user-chosen MODE: `plan` (the agent may only
inspect and plan; mutations and file creation are refused
deterministically before execution and the plan is returned
via final_answer) or `act` (normal execution). The panel's
Plan toggle sets it per submission; stdin mode accepts a
leading `/plan ` prefix. The chat transcript tags plan turns.

The panel's chat input box POSTs `{"text": "..."}` here; the
plugin queues the newest request in a single slot (a newer
submission displaces an older unconsumed one and the response
reports `"queued": true`). GET /agent_input is CONSUME-ON-READ:
the agent — running with `AGENT_INPUT_MODE=bridge` — polls it
every ~0.4 s as
`GET /agent_input?session_id=<its session id>` and receives
`{"pending", "text", "selected_provider", "selected_model",
"superseded"}`. The GET doubles as the agent-alive heartbeat the
panel's connection dot renders (green while polling or busy, red
when the idle heartbeat goes stale, gray when the agent runs in
classic stdin mode and never polls).
Model selections from the panel's dropdown travel the same
channel as `model_selected` events and apply to the NEXT turn.

### Session supersede (one live session, ever)

Every poll identifies its session. When the bridge considers a
DIFFERENT session active, it answers `superseded: true` and the
polling process raises `SessionSuperseded` in Python and
terminates itself (telemetry `termination=superseded_by_new_
session`) instead of racing the live session for requests. This
makes every session start authoritative — START SESSION, New
Session, or a manual spawn — so no stale process can ever serve
a new session with old context or old turn numbers. Two extra
guards close the handover window: `mark_session_starting()`
clears the pending-request FIFO (a stale `/exit` or unsent
request can never leak into the new session), and while
`session_starting` is true NO poller is served input (the old
process cannot start new work; the fresh process re-polls until
its own `session_started` lands, which resets chat, turn
numbers, metrics, and events). Events carry the emitting
process's `session_id`; the store drops any event whose session
does not match the active one. The FIRST turn also mirrors the
`/exit`/empty guards of `begin_next_turn`, so a session can
never hold a conversational "turn" about a stale `/exit`.

## Model selector (per-turn override)

The panel's dropdown lists every provider's configured model
(delivered in the `session_started` event's `available_models`
field; the right dock was removed — the bottom panel is the
only UI surface). A selection is stored in the plugin and picked up by the
agent on its next input poll; `ask_model` then overrides BOTH
provider and model for that turn (all provider adapters share
the `(conversation, schema)` contract, so per-turn switching is
structurally safe). `None` selection falls back to the
configured `MODEL_PROVIDER`.

## Panel (phase 1, monitor-only)

The plugin registers an "AI Agent" bottom panel
(`ui/ai_agent_panel.gd`): a header strip (status pill, turn/step,
elapsed clock, model, token totals, reserved approval-gate slot)
and four tabs — Activity (turn-grouped event timeline),
Mutations (verification ledger, double-click navigates to the
changed file when a path target exists), Chat (chat-LLM style
per turn: user request bubble, ONE in-place dim thinking line
showing the latest decision reason while the turn is in
flight — removed entirely once the turn completes — then the
bright answer bubble), Metrics (per-model-call
token/duration table with totals). THINKING renders as a warm
orange pulse (animated background + border); red stays reserved
for errors. All widgets are native editor-theme widgets.

---

# Documentation Maintenance

Update this document when:

- a new tool is added,
- a tool input schema changes,
- a result payload changes,
- path semantics change,
- validation behavior changes,
- recovery semantics change.

Do not update this document merely because a test succeeded.

Verified test outcomes belong in:

    docs/TEST_HISTORY.md

Current implementation details belong in:

    docs/CURRENT_STATE.md

Future priorities belong in:

    docs/ROADMAP.md

This file defines the communication contract between the reasoning layer and the Godot editor bridge.
