import json
import os
import urllib.error
import urllib.request

from config.settings import BRIDGE_TIMEOUT_SECONDS


# ==========================================
# Godot editor bridge
# ==========================================
# Overridable via GODOT_BRIDGE_URL so the Python
# agent (and its UI event reporter) can target an
# isolated editor instance during live validation
# without code edits. The per-request timeout comes
# from settings (GODOT_BRIDGE_TIMEOUT).

GODOT_BRIDGE_URL = os.environ.get(
    "GODOT_BRIDGE_URL",
    "http://127.0.0.1:8081",
)


# ==========================================
# HTTP helper
# ==========================================


def _request_json(
    endpoint,
    method="GET",
    payload=None
):
    """
    Send an HTTP request to the local Godot
    editor bridge and return decoded JSON.
    """

    url = (
        GODOT_BRIDGE_URL
        + endpoint
    )

    data = None

    headers = {
        "Content-Type": "application/json"
    }

    if payload is not None:

        data = json.dumps(
            payload
        ).encode(
            "utf-8"
        )

    request = urllib.request.Request(
        url=url,
        data=data,
        headers=headers,
        method=method
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=BRIDGE_TIMEOUT_SECONDS
        ) as response:

            body = (
                response.read()
                .decode("utf-8")
            )

            return json.loads(
                body
            )

    except urllib.error.HTTPError as error:

        try:

            body = (
                error.read()
                .decode("utf-8")
            )

            return json.loads(
                body
            )

        except Exception:

            return {
                "success": False,
                "error": (
                    "Godot bridge HTTP error: "
                    + str(error)
                )
            }

    except Exception as error:

        return {
            "success": False,
            "error": str(error)
        }


# ==========================================
# Scene inspection
# ==========================================


def get_scene_tree(
    max_depth=None,
):
    """
    Request scene information from the
    local Godot editor bridge.

    Optional max_depth bounds how deep the
    tree is serialized; deeper nodes are cut
    and reported as children_truncated so a
    huge scene never floods the context. Drill
    into truncated nodes with
    get_node_children_summary.
    """

    payload = {
        "max_depth": max_depth
    }

    return _request_json(
        endpoint="/scene_tree",
        method="POST",
        payload=payload
    )


def find_nodes(
    node_name=None,
    node_type=None,
    parent_path=None,
    name_match="exact",
    include_root=False,
    include_subclasses=False
):
    """
    Search the currently edited Godot scene.

    Parameters:

        node_name:
            Optional node name filter.

        node_type:
            Optional Godot class name filter.

        parent_path:
            Optional path restricting the search
            to descendants of a particular node.

        name_match:
            Name matching mode:

            exact
            contains
            starts_with
            ends_with

        include_root:
            Whether the edited scene root may be
            included in the results.

        include_subclasses:
            When true, the node_type filter also
            matches subclasses (e.g. node_type
            "Node2D" finds CharacterBody2D).
            Defaults to exact-class matching.

    Results are bounded (see limit/truncated in the
    response); check total_matches before assuming an
    exhaustive list.
    """

    payload = {
        "node_name": node_name,
        "node_type": node_type,
        "parent_path": parent_path,
        "name_match": name_match,
        "include_root": include_root,
        "include_subclasses": include_subclasses
    }

    return _request_json(
        endpoint="/find_nodes",
        method="POST",
        payload=payload
    )


def count_nodes(
    node_name=None,
    node_type=None,
    parent_path=None,
    name_match="exact",
    include_subclasses=False
):
    """
    Count the nodes in the currently edited Godot
    scene matching the same filter semantics as
    find_nodes (including include_subclasses),
    without returning the node list.
    """

    payload = {
        "node_name": node_name,
        "node_type": node_type,
        "parent_path": parent_path,
        "name_match": name_match,
        "include_subclasses": include_subclasses
    }

    return _request_json(
        endpoint="/count_nodes",
        method="POST",
        payload=payload
    )


def find_nodes_by_script(
    script_path
):
    """
    Find the nodes in the currently edited Godot
    scene whose attached script matches the
    requested script resource path.

    The result is authoritative: the bridge inspects
    each node's live attached script (get_script)
    during a real traversal of the edited scene.
    Paths without a res:// prefix are normalized by
    prepending it; matching is exact, with no fuzzy
    matching.

    Example script_path: "res://scripts/player.gd"
    """

    payload = {
        "script_path": script_path
    }

    return _request_json(
        endpoint="/find_nodes_by_script",
        method="POST",
        payload=payload
    )


def find_nodes_by_group(
    group_name
):
    """
    Find the nodes in the currently edited Godot
    scene that are members of the requested group.

    The result is authoritative: the bridge inspects
    each node's live group membership (is_in_group)
    during a real traversal of the edited scene.
    Matching is exact and case-sensitive.

    Example group_name: "enemies"
    """

    payload = {
        "group_name": group_name
    }

    return _request_json(
        endpoint="/find_nodes_by_group",
        method="POST",
        payload=payload
    )


def get_project_settings(
    setting_names=None,
    prefix=None,
    limit=None,
):
    """
    Inspect specific project settings from the live
    Godot ProjectSettings state, without dumping the
    whole database.


    Pass exact `setting_names` (a list of canonical
    setting keys,) and/or a `prefix` (return settings whose
    keys begin with it,) plus an optional `limit` on the
    prefix portion (1-100, default 50). At least one
    of setting_names/prefix must be provided; an unfiltered
    request that returns every setting is rejected by Godot.

    Values are serialized with the project's shared Variant
    serializer; setting names matching a sensitive token
    (password, token, secret, api_key, credential,
    private_key) are excluded from the response (names only).

    Examples:
### get_project_settings(
###     setting_names=[
###         "display/window/size/viewport_width",
###         "display/window/size/viewport_height"
###     ]
### )
### get_project_settings(prefix="display/window/size/")
    """

    payload = {
        "setting_names": setting_names,
        "prefix": prefix,
        "limit": limit
    }

    return _request_json(
        endpoint="/get_project_settings",
        method="POST",
        payload=payload
    )

def list_autoloads():
    """Return the project's configured autoload names and targets."""

    return _request_json(
        endpoint="/list_autoloads",
        method="GET",
    )

def get_editor_state():
    """Return bounded, deterministic state from the Godot editor."""

    return _request_json(
        endpoint="/get_editor_state",
        method="GET",
    )

def list_scenes_in_project():
    """Return scene resources known to the Godot editor filesystem."""

    return _request_json(
        endpoint="/list_scenes_in_project",
        method="GET",
    )

def get_undo_history_summary():
    """Return a read-only summary of available editor undo/redo state."""

    return _request_json(
        endpoint="/get_undo_history_summary",
        method="GET",
    )


def get_node_properties(
    node_path,
    property_names=None
):
    """
    Retrieve editor-visible readable properties
    for a node in the currently edited scene.

    node_path must be relative to the edited
    scene root.

    Use "." for the scene root.

    Optional property_names restricts the result
    to the named properties (each is reported as
    not_found when absent); prefer it over a full
    dump when only a few values matter.
    """

    payload = {
        "node_path": node_path,
        "property_names": property_names
    }

    return _request_json(
        endpoint="/get_node_properties",
        method="POST",
        payload=payload
    )


def get_node_property(
    node_path,
    property_name
):
    """
    Retrieve ONE editor-visible readable
    property value from a node in the
    currently edited scene.

    Preferred over get_node_properties when
    only a single property value is needed.

    node_path must be relative to the edited
    scene root.

    Use "." for the scene root.
    """

    payload = {
        "node_path": node_path,
        "property_name": property_name
    }

    return _request_json(
        endpoint="/get_node_property",
        method="POST",
        payload=payload
    )


def validate_node_type(
    node_type
):
    """
    Ask the Godot editor bridge whether the
    given class name is a valid, instantiable
    Godot node type usable for scene node
    creation.

    The result is authoritative: the bridge
    checks the real ClassDB of the running
    editor.
    """

    payload = {
        "node_type": node_type
    }

    return _request_json(
        endpoint="/validate_node_type",
        method="POST",
        payload=payload
    )


def list_available_node_types(
    inherits_from=None,
    name_contains=None,
    limit=None,
):
    """
    Return a bounded, deterministic list of native,
    instantiable Godot Node class names from the
    running editor's ClassDB.

    Optional filters restrict results by parent class
    and case-insensitive name substring. The bridge
    reports total_matches and truncated so callers do
    not mistake a bounded result for a full class list.
    """

    payload = {
        "inherits_from": inherits_from,
        "name_contains": name_contains,
        "limit": limit,
    }

    return _request_json(
        endpoint="/list_available_node_types",
        method="POST",
        payload=payload,
    )


def get_node_class_info(
    class_name,
):
    """
    Ask the Godot editor bridge for ClassDB information
    about a specific Godot class.

    The result is authoritative: the bridge answers from
    the real ClassDB of the running editor. Returns the
    class name, its base class, and whether it can be
    instantiated directly.
    """

    payload = {
        "class_name": class_name,
    }

    return _request_json(
        endpoint="/get_node_class_info",
        method="POST",
        payload=payload,
    )


def list_node_signals(
    node_path,
):
    """
    List the signals actually available on a node in
    the currently edited scene.

    The result is authoritative: the bridge answers from
    the node's real reflection data (get_signal_list),
    including built-in and inherited signals, sorted by
    signal name.

    node_path must be relative to the edited scene root.

    Use "." for the scene root.
    """

    payload = {
        "node_path": node_path,
    }

    return _request_json(
        endpoint="/list_node_signals",
        method="POST",
        payload=payload,
    )


def list_node_groups(
    node_path,
):
    """
    List the groups a node in the currently edited
    scene is actually a member of.

    The result is authoritative: the bridge answers
    from the node's real instance state (get_groups),
    sorted alphabetically for deterministic output.

    node_path must be relative to the edited scene root.

    Use "." for the scene root.
    """

    payload = {
        "node_path": node_path,
    }

    return _request_json(
        endpoint="/list_node_groups",
        method="POST",
        payload=payload,
    )


def list_node_connections(
    node_path,
):
    """
    List the signal connections of a node in the
    currently edited scene, in both directions.

    The result is authoritative: the bridge answers
    from the node's real connection state
    (get_incoming_connections and
    get_signal_connection_list), reporting incoming
    and outgoing connections separately, each with
    its peer node path, signal name, method name,
    and connection flags (deferred, persistent,
    one_shot). Results are sorted for deterministic
    output.

    node_path must be relative to the edited scene root.

    Use "." for the scene root.
    """

    payload = {
        "node_path": node_path,
    }

    return _request_json(
        endpoint="/list_node_connections",
        method="POST",
        payload=payload,
    )


# ==========================================
# Scene modification
# ==========================================


def create_node(
    parent_path,
    node_type,
    node_name
):
    """
    Ask the Godot editor bridge to create
    a node in the currently edited scene.
    """

    payload = {
        "parent_path": parent_path,
        "node_type": node_type,
        "node_name": node_name
    }

    return _request_json(
        endpoint="/create_node",
        method="POST",
        payload=payload
    )


def rename_node(
    node_path,
    new_name
):
    """
    Ask the Godot editor bridge to rename
    an existing node.
    """

    payload = {
        "node_path": node_path,
        "new_name": new_name
    }

    return _request_json(
        endpoint="/rename_node",
        method="POST",
        payload=payload
    )


def delete_node(
    node_path
):
    """
    Ask the Godot editor bridge to delete
    an existing node.

    The Godot editor handles this as an
    undoable EditorUndoRedoManager action.
    """

    payload = {
        "node_path": node_path
    }

    return _request_json(
        endpoint="/delete_node",
        method="POST",
        payload=payload
    )


def reparent_node(
    node_path,
    new_parent_path
):
    """
    Ask the Godot editor bridge to move
    an existing node under a new parent.

    Both paths are relative to the current
    edited scene root.
    """

    payload = {
        "node_path": node_path,
        "new_parent_path": new_parent_path
    }

    return _request_json(
        endpoint="/reparent_node",
        method="POST",
        payload=payload
    )


def duplicate_node(
    node_path,
    new_parent_path,
    new_name
):
    """
    Ask the Godot editor bridge to duplicate
    an existing node including its subtree,
    placing the copy under a new parent with
    the specified name.

    The operation is editor-native and undoable.
    """

    payload = {
        "node_path": node_path,
        "new_parent_path": new_parent_path,
        "new_name": new_name
    }

    return _request_json(
        endpoint="/duplicate_node",
        method="POST",
        payload=payload
    )


def set_properties(
    node_path,
    properties
):
    """
    Set one or more editable properties on a
    node in the currently edited Godot scene.

    properties must be a dictionary mapping
    property names to their requested values.

    Example:

        {
            "position": {
                "type": "Vector2",
                "x": 100,
                "y": 200
            },
            "visible": True
        }

    The Godot editor bridge validates all
    requested properties before applying the
    batch as one undoable operation.
    """

    payload = {
        "node_path": node_path,
        "properties": properties
    }

    return _request_json(
        endpoint="/set_properties",
        method="POST",
        payload=payload
    )


def move_child(
    node_path,
    new_index
):
    """
    Move an existing child node within its
    parent to the requested sibling index in
    the currently edited Godot scene.

    new_index must be an integer between 0 and
    (number of siblings - 1). The Godot editor
    bridge validates the node, the parent, and
    the index, then performs the move as one
    undoable EditorUndoRedoManager action and
    reports the verified sibling order back.
    """

    payload = {
        "node_path": node_path,
        "new_index": new_index
    }

    return _request_json(
        endpoint="/move_child",
        method="POST",
        payload=payload
    )


def add_to_group(
    node_path,
    group_name
):
    """
    Add an existing node in the currently edited
    Godot scene to a persistent group.

    Adding a node that is already in the group is a
    deterministic no-op success. The Godot editor
    bridge performs an actual change as one undoable
    EditorUndoRedoManager action and verifies the
    resulting membership.
    """

    payload = {
        "node_path": node_path,
        "group_name": group_name
    }

    return _request_json(
        endpoint="/add_to_group",
        method="POST",
        payload=payload
    )


def remove_from_group(
    node_path,
    group_name
):
    """
    Remove an existing node in the currently edited
    Godot scene from a persistent group.

    Removing a node that is not in the group is a
    deterministic no-op success. The Godot editor
    bridge performs an actual change as one undoable
    EditorUndoRedoManager action and verifies the
    resulting membership.
    """

    payload = {
        "node_path": node_path,
        "group_name": group_name
    }

    return _request_json(
        endpoint="/remove_from_group",
        method="POST",
        payload=payload
    )


def connect_signal(
    node_path,
    signal_name,
    target_path,
    method_name,
    deferred=False
):
    """
    Connect a signal on an existing node in the
    currently edited Godot scene to a method on
    another node.

    The connection is addressed exactly like the
    editor's Connect dialog: node_path is the signal
    emitter, target_path is the node owning the
    method. Callable expressions are not supported.

    The bridge verifies that the signal exists on the
    emitter and the method exists on the target before
    connecting. Connecting an already-connected pair is
    a deterministic no-op success. An actual change is
    performed as one undoable EditorUndoRedoManager
    action (persistent, so it survives scene saves) and
    the resulting connection is verified.
    """

    payload = {
        "node_path": node_path,
        "signal_name": signal_name,
        "target_path": target_path,
        "method_name": method_name,
        "deferred": deferred
    }

    return _request_json(
        endpoint="/connect_signal",
        method="POST",
        payload=payload
    )


def disconnect_signal(
    node_path,
    signal_name,
    target_path,
    method_name
):
    """
    Disconnect a signal on an existing node in the
    currently edited Godot scene from a method on
    another node.

    Disconnecting a pair that is not connected is a
    deterministic no-op success. An actual change is
    performed as one undoable EditorUndoRedoManager
    action (the undo restores the original connection
    flags) and the resulting state is verified.
    """

    payload = {
        "node_path": node_path,
        "signal_name": signal_name,
        "target_path": target_path,
        "method_name": method_name
    }

    return _request_json(
        endpoint="/disconnect_signal",
        method="POST",
        payload=payload
    )


def create_script(
    script_path,
    content
):
    """
    Create a new GDScript file in the project with the
    given full content.

    The bridge enforces a res:// path ending in .gd with
    no directory traversal, refuses to overwrite an
    existing file, and parse-checks the content BEFORE
    writing: a script that does not parse is never
    written to disk.

    File creation is not undoable through the editor's
    undo system; the result reports undoable: false and
    verifies the write by reading the file back.
    """

    payload = {
        "script_path": script_path,
        "content": content
    }

    return _request_json(
        endpoint="/create_script",
        method="POST",
        payload=payload
    )


def attach_script(
    node_path,
    script_path
):
    """
    Attach an existing GDScript resource to a node in
    the currently edited Godot scene.

    Attaching a script the node already has is a
    deterministic no-op success. If the node has a
    DIFFERENT script attached, the request is refused
    deterministically (detach_script first). The change
    is performed as one undoable EditorUndoRedoManager
    action and the resulting attachment is verified by
    reading the node's script back.
    """

    payload = {
        "node_path": node_path,
        "script_path": script_path
    }

    return _request_json(
        endpoint="/attach_script",
        method="POST",
        payload=payload
    )


def detach_script(
    node_path
):
    """
    Remove the script attached to a node in the
    currently edited Godot scene.

    Detaching a node without a script is a
    deterministic no-op success. The change is
    performed as one undoable EditorUndoRedoManager
    action whose undo restores the previous script;
    the resulting state is verified by reading the
    node's script back.
    """

    payload = {
        "node_path": node_path
    }

    return _request_json(
        endpoint="/detach_script",
        method="POST",
        payload=payload
    )


def get_script_content(
    script_path,
    start_line=None,
    line_count=None
):
    """
    Read the source of a GDScript file from the
    project.

    The result is authoritative: the bridge reads the
    real file from disk. Paths without a res:// prefix
    are normalized by prepending it.

    Optional start_line and line_count page through
    large scripts in bounded chunks (1-based, line
    inclusive); with them the result reports
    total_lines and truncated so a bounded read is
    never mistaken for the whole file. Without them
    the full source is returned.
    """

    payload = {
        "script_path": script_path,
        "start_line": start_line,
        "line_count": line_count
    }

    return _request_json(
        endpoint="/get_script_content",
        method="POST",
        payload=payload
    )


def list_script_diagnostics(
    script_path
):
    """
    Parse-check a GDScript file and report the result.

    The bridge performs a fresh parse of the current
    file content and reports parse_ok plus the Godot
    error code when parsing fails, alongside basic
    file metadata. This works both headless and inside
    the running editor.
    """

    payload = {
        "script_path": script_path
    }

    return _request_json(
        endpoint="/list_script_diagnostics",
        method="POST",
        payload=payload
    )


def edit_script(
    script_path,
    content
):
    """
    Replace the ENTIRE content of an existing GDScript
    file with new source.

    The bridge parse-checks the new content BEFORE
    writing: content that does not parse is never
    written, so the file on disk stays in its previous,
    working state. Replacing with byte-identical content
    is a deterministic no-op success. The change is not
    undoable through the editor's undo system; the result
    reports undoable: false and verifies the write by
    reading the file back.
    """

    payload = {
        "script_path": script_path,
        "content": content
    }

    return _request_json(
        endpoint="/edit_script",
        method="POST",
        payload=payload
    )


def replace_in_script(
    script_path,
    old_string,
    new_string
):
    """
    Perform a deterministic anchored edit inside an
    existing GDScript file: old_string must occur
    EXACTLY ONCE in the current content and is replaced
    by new_string.

    If old_string is absent but new_string is already
    present, the edit is treated as already applied (a
    deterministic no-op success). Ambiguous matches are
    refused. The result is parse-checked before writing;
    a failed parse leaves the file untouched.
    """

    payload = {
        "script_path": script_path,
        "old_string": old_string,
        "new_string": new_string
    }

    return _request_json(
        endpoint="/replace_in_script",
        method="POST",
        payload=payload
    )


def save_scene():
    """
    Save the currently edited scene in the running Godot
    editor to its own file on disk.

    Requires the running editor (unavailable headless).
    The result verifies the save by checking that the
    scene file exists and was modified by this call.
    """

    return _request_json(
        endpoint="/save_scene",
        method="POST",
        payload={}
    )


def create_scene(
    scene_path,
    root_node_type
):
    """
    Create a NEW scene file with a root node of the
    requested type. The file is created on disk but NOT
    opened in the editor: opening a scene changes the
    edited-scene context and is deliberately out of scope
    for this tool.

    Existing files are never overwritten. File creation
    is not undoable; the result verifies the created
    scene by loading it back and reporting the root node.
    """

    payload = {
        "scene_path": scene_path,
        "root_node_type": root_node_type
    }

    return _request_json(
        endpoint="/create_scene",
        method="POST",
        payload=payload
    )


def instantiate_scene(
    parent_path,
    scene_path,
    new_name=None
):
    """
    Instance an existing scene file as a child of a node
    in the currently edited scene, as one undoable
    EditorUndoRedoManager action.

    The parent must exist; the scene file must exist and
    load as a PackedScene. The result verifies the
    instanced child (its scene_file_path) after the
    change.
    """

    payload = {
        "parent_path": parent_path,
        "scene_path": scene_path,
        "new_name": new_name
    }

    return _request_json(
        endpoint="/instantiate_scene",
        method="POST",
        payload=payload
    )


def get_scene_dependencies(
    scene_path
):
    """
    Report the external resources and sub-scenes a scene
    file depends on, answered from the loaded PackedScene
    state (never by parsing the file text).

    The scene is loaded without being opened in the
    editor and without touching the currently edited
    scene.
    """

    payload = {
        "scene_path": scene_path
    }

    return _request_json(
        endpoint="/get_scene_dependencies",
        method="POST",
        payload=payload
    )


def get_scene_tree_of(
    scene_path,
    max_depth=None
):
    """
    Serialize the node tree of any scene file in the
    project without opening it in the editor. The result
    uses the same node serialization as get_scene_tree,
    scoped to the requested file.

    Optional max_depth bounds the serialization depth
    exactly like get_scene_tree.

    Use this for multi-scene reasoning; the currently
    edited scene remains untouched.
    """

    payload = {
        "scene_path": scene_path,
        "max_depth": max_depth
    }

    return _request_json(
        endpoint="/get_scene_tree_of",
        method="POST",
        payload=payload
    )


def list_open_scenes():
    """
    List the scenes currently open in the running Godot
    editor, with the actively edited scene marked.

    Requires the running editor (unavailable headless).
    """

    return _request_json(
        endpoint="/list_open_scenes",
        method="POST",
        payload={}
    )


def get_property_info(
    node_path,
    property_name
):
    """
    Report the type, hint, usage flags, current value,
    and class default for ONE property of a node, from
    real reflection.

    Use this before set_properties to learn the expected
    value shape instead of guessing the property schema.
    """

    payload = {
        "node_path": node_path,
        "property_name": property_name
    }

    return _request_json(
        endpoint="/get_property_info",
        method="POST",
        payload=payload
    )


def get_node_children_summary(
    node_path
):
    """
    Lightweight child listing for one node: name, type,
    sibling index, and child count, without full tree
    serialization.

    Preferred over get_scene_tree for large scenes when
    only the immediate children are needed.
    """

    payload = {
        "node_path": node_path
    }

    return _request_json(
        endpoint="/get_node_children_summary",
        method="POST",
        payload=payload
    )


def assign_resource_to_property(
    node_path,
    property_name,
    resource_path
):
    """
    Load a res:// resource and assign it to one property
    of a node as a single undoable
    EditorUndoRedoManager action.

    The bridge verifies that the resource loads and that
    the property exists before assigning, and verifies
    the assignment by reading the property back and
    comparing its resource path.
    """

    payload = {
        "node_path": node_path,
        "property_name": property_name,
        "resource_path": resource_path
    }

    return _request_json(
        endpoint="/assign_resource_to_property",
        method="POST",
        payload=payload
    )


def get_resource_info(
    resource_path
):
    """
    Report the type and identity of a resource file
    (class, resource path, resource name) answered from
    the real loaded resource.
    """

    payload = {
        "resource_path": resource_path
    }

    return _request_json(
        endpoint="/get_resource_info",
        method="POST",
        payload=payload
    )


def list_project_files(
    prefix=None,
    extensions=None,
    limit=None
):
    """
    Bounded, filterable listing of project files under a
    res:// prefix, optionally restricted to extensions
    (e.g. ["gd", "tscn"]). Editor-internal directories
    (.godot, .git) are excluded.

    The result reports total_matches and truncated so a
    bounded result is never mistaken for a full listing.
    """

    payload = {
        "prefix": prefix,
        "extensions": extensions,
        "limit": limit
    }

    return _request_json(
        endpoint="/list_project_files",
        method="POST",
        payload=payload
    )


def search_in_files(
    query,
    extensions=None,
    limit=None
):
    """
    Bounded case-insensitive text search across project
    text files, optionally restricted to extensions.

    Scanning is bounded (file count and match count);
    results report total_matches and truncated, and
    include file path, line number, and a bounded line
    snippet per match.
    """

    payload = {
        "query": query,
        "extensions": extensions,
        "limit": limit
    }

    return _request_json(
        endpoint="/search_in_files",
        method="POST",
        payload=payload
    )


def get_global_class_list():
    """
    List the project's class_name globals (ScriptServer
    global class list): the class name and the script
    path that declares it.
    """

    return _request_json(
        endpoint="/get_global_class_list",
        method="POST",
        payload={}
    )


def get_input_map():
    """
    Report the project's configured input actions with
    their event descriptions, answered from the live
    InputMap.
    """

    return _request_json(
        endpoint="/get_input_map",
        method="POST",
        payload={}
    )


def run_scene(
    scene_path=None
):
    """
    Run the game from the running Godot editor so the
    agent can observe real behavior.

    Without a scene_path the project's MAIN scene is run;
    with a scene_path that scene is run instead. Requires
    the running editor. The result reports the playing
    scene path; combine with get_runtime_output to read
    the game's errors and output, and stop_run to end it.
    """

    payload = {
        "scene_path": scene_path
    }

    return _request_json(
        endpoint="/run_scene",
        method="POST",
        payload=payload
    )


def stop_run():
    """
    Stop the game currently run from the Godot editor.

    Requires the running editor. The result verifies that
    the editor reports no playing scene afterwards.
    """

    return _request_json(
        endpoint="/stop_run",
        method="POST",
        payload={}
    )


def get_runtime_output(
    clear=False
):
    """
    Read the output and error messages captured from the
    game running via run_scene, oldest first.

    Entries carry a kind ("output" or "error") and text.
    With clear=True the buffer is emptied after the read
    so the next call only reports new entries; with the
    default clear=False the buffer is left intact. The
    buffer is bounded; dropped counts are reported.
    Requires the running editor.
    """

    payload = {
        "clear": clear
    }

    return _request_json(
        endpoint="/get_runtime_output",
        method="POST",
        payload=payload
    )


def open_scene(
    scene_path
):
    """
    Open a scene file in the Godot editor, making it the
    edited scene.

    CONTEXT SWITCH WARNING: after opening, all node paths
    from the previously edited scene are invalid. The
    bridge refuses to open while the current scene has
    unsaved changes (save_scene first). Requires the
    running editor.
    """

    payload = {
        "scene_path": scene_path
    }

    return _request_json(
        endpoint="/open_scene",
        method="POST",
        payload=payload
    )


def save_scene_as(
    scene_path
):
    """
    Save the currently edited scene to a NEW res:// path
    (editor-native save-as). The scene's file path
    changes to the new location; the result verifies the
    write. Requires the running editor.
    """

    payload = {
        "scene_path": scene_path
    }

    return _request_json(
        endpoint="/save_scene_as",
        method="POST",
        payload=payload
    )


def set_project_settings(
    settings
):
    """
    Set one or more project settings (e.g. display
    resolution, window flags, physics values) in the
    live ProjectSettings.

    settings must be a dictionary mapping canonical
    setting keys to values. Sensitive keys (password,
    token, secret, api_key, credential, private_key) are
    rejected. The result reports the previous value of
    every changed key so the human can revert, and
    verifies each value by reading it back. Values are
    persisted to project.godot when the editor saves the
    project.
    """

    payload = {
        "settings": settings
    }

    return _request_json(
        endpoint="/set_project_settings",
        method="POST",
        payload=payload
    )


def create_resource(
    resource_path,
    resource_type,
    properties
):
    """
    Create a NEW file-backed resource (.tres) of the
    requested Resource type with the given properties.

    The bridge validates that the type exists and is an
    instantiable Resource, applies the properties with
    type-aware deserialization, saves the file, and
    verifies by loading it back. Existing files are never
    overwritten. File creation is not undoable.
    """

    payload = {
        "resource_path": resource_path,
        "resource_type": resource_type,
        "properties": properties
    }

    return _request_json(
        endpoint="/create_resource",
        method="POST",
        payload=payload
    )


def scan_project_issues(
    prefix=None,
    limit=None
):
    """
    Scan project files for mechanical problems and
    report them as a bounded, structured issue list.

    Checks performed:

    - script_parse_error: a .gd file that fails a
      fresh GDScript parse.
    - scene_load_failed: a .tscn file that does not
      load as a PackedScene.
    - missing_dependency: a scene dependency whose
      res:// path does not exist on disk.

    Optional prefix restricts the scan to a res://
    sub-path; limit (1-100, default 50) bounds the
    reported issues. The result reports scanned_files,
    total_matches and truncated so a bounded result is
    never mistaken for a clean bill of health. Use this
    after large refactors or before final_answer to
    verify the project is still coherent.
    """

    payload = {
        "prefix": prefix,
        "limit": limit
    }

    return _request_json(
        endpoint="/scan_project_issues",
        method="POST",
        payload=payload
    )


def rename_script(
    script_path,
    new_script_path
):
    """
    Rename or move an existing GDScript file, updating
    every textual reference to its res:// path across
    project files (.gd, .tscn, .tres, .cfg, and
    project.godot) in one deterministic operation.

    Two-phase and parse-gated: new content is computed
    and parse-checked for every affected .gd file BEFORE
    anything is written, so a failed parse leaves every
    file untouched. The target path must not exist; the
    script's .uid sidecar is renamed alongside when
    present. The result lists the changed files and
    verifies by re-scanning for leftover references.
    Not undoable through the editor's undo system.
    """

    payload = {
        "script_path": script_path,
        "new_script_path": new_script_path
    }

    return _request_json(
        endpoint="/rename_script",
        method="POST",
        payload=payload
    )


def find_replace_across_files(
    old_string,
    new_string,
    extensions=None,
    prefix=None,
    max_files=None
):
    """
    Replace every occurrence of old_string with
    new_string across multiple project text files in one
    deterministic, parse-gated operation.

    Files are selected by extensions (default
    ["gd", "tscn", "tres"]) and an optional res://
    prefix. max_files (1-50, default 20) bounds how many
    files may be modified per call; a request whose
    match set exceeds the bound is refused entirely
    rather than partially applied. Affected .gd files
    are parse-checked BEFORE any write; any parse
    failure aborts the whole operation with nothing
    written. The result lists each modified file with
    its replacement count and verifies by reading the
    files back. Not undoable.
    """

    payload = {
        "old_string": old_string,
        "new_string": new_string,
        "extensions": extensions,
        "prefix": prefix,
        "max_files": max_files
    }

    return _request_json(
        endpoint="/find_replace_across_files",
        method="POST",
        payload=payload
    )
