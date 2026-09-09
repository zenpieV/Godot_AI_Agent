import json
import urllib.error
import urllib.request


# ==========================================
# Godot editor bridge
# ==========================================


GODOT_BRIDGE_URL = "http://127.0.0.1:8081"


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
            timeout=5
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


def get_scene_tree():
    """
    Request scene information from the
    local Godot editor bridge.
    """

    return _request_json(
        endpoint="/scene_tree",
        method="GET"
    )


def find_nodes(
    node_name=None,
    node_type=None,
    parent_path=None,
    name_match="exact",
    include_root=False
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
    """

    payload = {
        "node_name": node_name,
        "node_type": node_type,
        "parent_path": parent_path,
        "name_match": name_match,
        "include_root": include_root
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
):
    """
    Count the nodes in the currently edited Godot
    scene matching the same filter semantics as
    find_nodes, without returning the node list.

    Use this instead of find_nodes when only the
    number of matching nodes is needed, e.g.
    "how many enemies exist?" or "are there at
    least 5 triggers?".

    The bridge is authoritative: the count comes
    from a real traversal of the currently edited
    scene.
    """

    payload = {
        "node_name": node_name,
        "node_type": node_type,
        "parent_path": parent_path,
        "name_match": name_match
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
    node_path
):
    """
    Retrieve editor-visible readable properties
    for a node in the currently edited scene.

    node_path must be relative to the edited
    scene root.

    Use "." for the scene root.
    """

    payload = {
        "node_path": node_path
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
    script_path
):
    """
    Read the full source of a GDScript file from the
    project.

    The result is authoritative: the bridge reads the
    real file from disk. Paths without a res:// prefix
    are normalized by prepending it.
    """

    payload = {
        "script_path": script_path
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
