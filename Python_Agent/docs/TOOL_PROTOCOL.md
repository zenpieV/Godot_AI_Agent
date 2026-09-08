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
