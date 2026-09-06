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