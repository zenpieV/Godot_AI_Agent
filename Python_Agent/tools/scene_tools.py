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
