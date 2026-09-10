@tool
extends RefCounted

class_name AIAgentPropertyTools


var scene_helpers: AIAgentSceneHelpers
var variant_serializer: AIAgentVariantSerializer
var undo_redo: EditorUndoRedoManager


func _init(
	p_scene_helpers: AIAgentSceneHelpers,
	p_variant_serializer: AIAgentVariantSerializer,
	p_undo_redo: EditorUndoRedoManager
) -> void:

	scene_helpers = p_scene_helpers

	variant_serializer = p_variant_serializer

	undo_redo = p_undo_redo


# ==========================================
# get_node_properties
# ==========================================


func get_node_properties_from_request(
	data: Dictionary
) -> Dictionary:

	if not data.has("node_path"):

		return {
			"success": false,
			"error": (
				"get_node_properties requires "
				+ "node_path."
			)
		}

	var node_path: String = (
		str(data["node_path"])
	)

	var node_result := (
		scene_helpers
		.resolve_node_or_error(
			node_path
		)
	)

	if not node_result["success"]:
		return node_result

	var edited_scene_root: Node = (
		node_result["scene_root"]
	)

	var target_node: Node = (
		node_result["node"]
	)

	var properties := []

	var property_list := (
		target_node
		.get_property_list()
	)

	for property_info in property_list:

		var property_name := (
			str(
				property_info.get(
					"name",
					""
				)
			)
		)

		var usage := int(
			property_info.get(
				"usage",
				0
			)
		)

		var property_type := int(
			property_info.get(
				"type",
				TYPE_NIL
			)
		)

		if (
			usage
			& PROPERTY_USAGE_EDITOR
		) == 0:

			continue

		var current_value = (
			target_node.get(
				property_name
			)
		)

		var is_read_only := (
			usage
			& PROPERTY_USAGE_READ_ONLY
		) != 0

		properties.append(
			{
				"name": property_name,
				"type": (
					type_string(
						property_type
					)
				),
				"type_id": property_type,
				"editable": (
					not is_read_only
				),
				"value": (
					variant_serializer
					.serialize_property_value(
						current_value
					)
				)
			}
		)

	return {
		"success": true,
		"action": "get_node_properties",
		"node_path": (
			scene_helpers
			.get_relative_node_path(
				edited_scene_root,
				target_node
			)
		),
		"node_name": (
			str(target_node.name)
		),
		"node_type": (
			target_node.get_class()
		),
		"property_count": (
			properties.size()
		),
		"properties": properties
	}


# ==========================================
# get_node_property
# ==========================================


func get_node_property_from_request(
	data: Dictionary
) -> Dictionary:

	if not data.has("node_path"):

		return {
			"success": false,
			"error": (
				"get_node_property requires "
				+ "node_path."
			)
		}

	if not data.has("property_name"):

		return {
			"success": false,
			"error": (
				"get_node_property requires "
				+ "property_name."
			)
		}

	var node_path: String = (
		str(data["node_path"]).strip_edges()
	)

	if node_path.is_empty():

		return {
			"success": false,
			"error": (
				"get_node_property requires a "
				+ "non-empty node_path (use \".\" "
				+ "for the edited scene root)."
			)
		}

	var property_name: String = (
		str(data["property_name"]).strip_edges()
	)

	if property_name.is_empty():

		return {
			"success": false,
			"error": (
				"get_node_property requires a "
				+ "non-empty property_name."
			)
		}

	var node_result := (
		scene_helpers
		.resolve_node_or_error(
			node_path
		)
	)

	if not node_result["success"]:
		return node_result

	var edited_scene_root: Node = (
		node_result["scene_root"]
	)

	var target_node: Node = (
		node_result["node"]
	)

	# Locate the requested property in the
	# node's actual property list. Only
	# editor-visible properties are exposed
	# through this tool, matching the property
	# set returned by get_node_properties.
	#
	# Node.name is the one intentional exception:
	# it is editor-visible in the scene tree and
	# readable on every Node, but Godot does not
	# mark it with PROPERTY_USAGE_EDITOR. Keep it
	# read-only here because name changes must use
	# the dedicated, undoable rename_node action.
	var property_info := {}

	var found := false

	if property_name == "name":

		property_info = {
			"type": TYPE_STRING_NAME,
			"usage": PROPERTY_USAGE_READ_ONLY
		}

		found = true

	else:

		for entry in (
			target_node
			.get_property_list()
		):

			if (
				str(
					entry.get(
						"name",
						""
					)
				)
				== property_name
			):

				var usage := int(
					entry.get(
						"usage",
						0
					)
				)

				if (
					usage
					& PROPERTY_USAGE_EDITOR
				) != 0:

					property_info = entry

					found = true

					break

	if not found:

		return {
			"success": false,
			"error": (
				"Property not found: "
				+ property_name
				+ " on node "
				+ str(target_node.name)
				+ "."
			)
		}

	var property_type := int(
		property_info.get(
			"type",
			TYPE_NIL
		)
	)

	var is_read_only := (
		int(
			property_info.get(
				"usage",
				0
			)
		)
		& PROPERTY_USAGE_READ_ONLY
	) != 0

	# Read the actual current value from the
	# node. Never fabricated.
	var current_value

	if property_name == "name":
		current_value = target_node.name
	else:
		current_value = target_node.get(property_name)

	return {
		"success": true,
		"action": "get_node_property",
		"node_path": (
			scene_helpers
			.get_relative_node_path(
				edited_scene_root,
				target_node
			)
		),
		"node_name": (
			str(target_node.name)
		),
		"node_type": (
			target_node.get_class()
		),
		"property_name": property_name,
		"property_type": (
			type_string(
				property_type
			)
		),
		"property_type_id": property_type,
		"editable": (
			not is_read_only
		),
		"value": (
			variant_serializer
			.serialize_property_value(
				current_value
			)
		)
	}


# ==========================================
# set_properties
# ==========================================


func set_properties_from_request(
	data: Dictionary
) -> Dictionary:

	if not data.has("node_path"):

		return {
			"success": false,
			"error": (
				"set_properties requires "
				+ "node_path."
			)
		}

	if not data.has("properties"):

		return {
			"success": false,
			"error": (
				"set_properties requires "
				+ "properties."
			)
		}

	if (
		not data["properties"]
		is Dictionary
	):

		return {
			"success": false,
			"error": (
				"set_properties properties "
				+ "must be an object."
			)
		}

	var node_path: String = (
		str(data["node_path"])
	)

	var requested_properties: Dictionary = (
		data["properties"]
	)

	if requested_properties.is_empty():

		return {
			"success": false,
			"error": (
				"set_properties requires at least "
				+ "one property."
			)
		}

	var node_result := (
		scene_helpers
		.resolve_node_or_error(
			node_path
		)
	)

	if not node_result["success"]:
		return node_result

	var edited_scene_root: Node = (
		node_result["scene_root"]
	)

	var target_node: Node = (
		node_result["node"]
	)

	var property_metadata := (
		build_property_metadata(
			target_node
		)
	)

	var prepared_changes := []

	for property_name_variant in (
		requested_properties
	):

		var property_name := (
			str(
				property_name_variant
			)
		)

		if (
			not property_metadata
			.has(property_name)
		):

			return {
				"success": false,
				"error": (
					"Property not found on node: "
					+ property_name
				)
			}

		var metadata: Dictionary = (
			property_metadata[
				property_name
			]
		)

		if not metadata["editable"]:

			return {
				"success": false,
				"error": (
					"Property is read-only: "
					+ property_name
				)
			}

		var deserialize_result := (
			variant_serializer
			.deserialize_property_value(
				requested_properties[
					property_name_variant
				],
				metadata["type_id"]
			)
		)

		if not deserialize_result["success"]:

			return {
				"success": false,
				"error": (
					"Invalid value for property "
					+ property_name
					+ ": "
					+ str(
						deserialize_result[
							"error"
						]
					)
				)
			}

		var old_value = (
			target_node.get(
				property_name
			)
		)

		var new_value = (
			deserialize_result[
				"value"
			]
		)

		prepared_changes.append(
			{
				"name": property_name,
				"old_value": old_value,
				"new_value": new_value
			}
		)

	var action_name := (
		"AI Agent: Set Properties on "
		+ str(target_node.name)
	)

	undo_redo.create_action(
		action_name
	)

	for change in prepared_changes:

		undo_redo.add_do_property(
			target_node,
			change["name"],
			change["new_value"]
		)

	for change in prepared_changes:

		undo_redo.add_undo_property(
			target_node,
			change["name"],
			change["old_value"]
		)

	undo_redo.commit_action()

	var response_properties := []

	for change in prepared_changes:

		response_properties.append(
			{
				"name": change["name"],
				"old_value": (
					variant_serializer
					.serialize_property_value(
						change["old_value"]
					)
				),
				"new_value": (
					variant_serializer
					.serialize_property_value(
						change["new_value"]
					)
				)
			}
		)

	return {
		"success": true,
		"action": "set_properties",
		"message": (
			"Node properties updated successfully "
			+ "in the Godot editor."
		),
		"node_path": (
			scene_helpers
			.get_relative_node_path(
				edited_scene_root,
				target_node
			)
		),
		"node_name": (
			str(target_node.name)
		),
		"node_type": (
			target_node.get_class()
		),
		"property_count": (
			response_properties.size()
		),
		"properties": response_properties,
		"undoable": true
	}


# ==========================================
# Property metadata
# ==========================================


func build_property_metadata(
	target_node: Node
) -> Dictionary:

	var metadata := {}

	var property_list := (
		target_node
		.get_property_list()
	)

	for property_info in property_list:

		var property_name := (
			str(
				property_info.get(
					"name",
					""
				)
			)
		)

		var usage := int(
			property_info.get(
				"usage",
				0
			)
		)

		var property_type := int(
			property_info.get(
				"type",
				TYPE_NIL
			)
		)

		if (
			usage
			& PROPERTY_USAGE_EDITOR
		) == 0:

			continue

		var is_read_only := (
			usage
			& PROPERTY_USAGE_READ_ONLY
		) != 0

		metadata[property_name] = {
			"type_id": property_type,
			"editable": (
				not is_read_only
			)
		}

	return metadata


# ==========================================
# get_property_info
# ==========================================
# Deep introspection for ONE property: real reflection
# type/hint/usage from get_property_list, the current
# value serialized JSON-safely, and the class default
# from ClassDB. Lets the model construct valid
# set_properties payloads instead of guessing schemas.


func get_property_info_from_request(
	data: Dictionary
) -> Dictionary:

	if not data.has("node_path"):

		return {
			"success": false,
			"error": (
				"get_property_info requires "
				+ "node_path."
			)
		}

	if not data.has("property_name"):

		return {
			"success": false,
			"error": (
				"get_property_info requires "
				+ "property_name."
			)
		}

	var node_path: String = (
		str(data["node_path"]).strip_edges()
	)

	var property_name: String = (
		str(data["property_name"]).strip_edges()
	)

	if property_name.is_empty():

		return {
			"success": false,
			"error": (
				"get_property_info requires a "
				+ "non-empty property_name."
			)
		}

	var node_result := (
		scene_helpers
		.resolve_node_or_error(
			node_path
		)
	)

	if not node_result["success"]:
		return node_result

	var edited_scene_root: Node = (
		node_result["scene_root"]
	)

	var target_node: Node = (
		node_result["node"]
	)

	var found: Dictionary = {}

	for property_info in (
		target_node.get_property_list()
	):

		if str(
			property_info.get("name", "")
		) == property_name:

			found = property_info

			break

	if found.is_empty():

		return {
			"success": false,
			"error": (
				"Property not found on node: "
				+ property_name
			)
		}

	var usage: int = int(
		found.get("usage", 0)
	)

	var type_id: int = int(
		found.get("type", TYPE_NIL)
	)

	var current_value = (
		target_node.get(property_name)
	)

	var class_default: Variant = (
		ClassDB.class_get_property_default_value(
			target_node.get_class(),
			property_name
		)
	)

	return {
		"success": true,
		"action": "get_property_info",
		"node_path": (
			scene_helpers
			.get_relative_node_path(
				edited_scene_root,
				target_node
			)
		),
		"node_name": str(target_node.name),
		"node_type": target_node.get_class(),
		"property_name": property_name,
		"type": type_string(type_id),
		"type_id": type_id,
		"hint": int(found.get("hint", 0)),
		"hint_string": str(
			found.get("hint_string", "")
		),
		"usage": usage,
		"editable": (
			usage & PROPERTY_USAGE_READ_ONLY
		) == 0,
		"current_value": (
			variant_serializer
			.serialize_property_value(
				current_value
			)
		),
		"class_default": (
			variant_serializer
			.serialize_property_value(
				class_default
			)
		),
	}


# ==========================================
# Resource path handling
# ==========================================
# Shared strict path normalization for resource files:
# res:// scheme (auto-prefixed), forward slashes only,
# no directory traversal, non-empty file name. Unlike
# scripts/scenes, any resource extension is accepted.


func _normalize_resource_file_path(
	raw_path,
	action_name: String
) -> Dictionary:

	if typeof(raw_path) != TYPE_STRING:

		return {
			"success": false,
			"error": (
				action_name
				+ " requires a resource path."
			)
		}

	var resource_path: String = (
		str(raw_path).strip_edges()
	)

	if resource_path.is_empty():

		return {
			"success": false,
			"error": (
				action_name
				+ " requires a non-empty "
				+ "resource path."
			)
		}

	if not resource_path.begins_with("res://"):

		resource_path = (
			"res://"
			+ resource_path
		)

	if resource_path.contains("\\"):

		return {
			"success": false,
			"error": (
				action_name
				+ " resource path must use "
				+ "forward slashes."
			)
		}

	if resource_path.contains(".."):

		return {
			"success": false,
			"error": (
				action_name
				+ " resource path must not "
				+ "contain directory traversal."
			)
		}

	if resource_path.length() <= len("res://"):

		return {
			"success": false,
			"error": (
				action_name
				+ " requires a resource file name."
			)
		}

	return {
		"ok": true,
		"resource_path": resource_path
	}


# ==========================================
# assign_resource_to_property
# ==========================================
# Loads a res:// resource and assigns it to one property
# as a single undoable EditorUndoRedoManager property
# action. Refuses read-only properties and non-resource
# values; verifies by reading the property back and
# comparing resource paths.


func assign_resource_to_property_from_request(
	data: Dictionary
) -> Dictionary:

	if not data.has("node_path"):

		return {
			"success": false,
			"error": (
				"assign_resource_to_property "
				+ "requires node_path."
			)
		}

	if not data.has("property_name"):

		return {
			"success": false,
			"error": (
				"assign_resource_to_property "
				+ "requires property_name."
			)
		}

	var node_path: String = (
		str(data["node_path"]).strip_edges()
	)

	var property_name: String = (
		str(data["property_name"]).strip_edges()
	)

	if property_name.is_empty():

		return {
			"success": false,
			"error": (
				"assign_resource_to_property "
				+ "requires a non-empty "
				+ "property_name."
			)
		}

	var path_check := (
		_normalize_resource_file_path(
			data.get("resource_path"),
			"assign_resource_to_property"
		)
	)

	if not path_check.get("ok", false):
		return path_check

	var resource_path: String = (
		path_check["resource_path"]
	)

	var node_result := (
		scene_helpers
		.resolve_node_or_error(
			node_path
		)
	)

	if not node_result["success"]:
		return node_result

	var edited_scene_root: Node = (
		node_result["scene_root"]
	)

	var target_node: Node = (
		node_result["node"]
	)

	var property_metadata := (
		build_property_metadata(
			target_node
		)
	)

	if not property_metadata.has(property_name):

		return {
			"success": false,
			"error": (
				"Property not found on node: "
				+ property_name
			)
		}

	var metadata: Dictionary = (
		property_metadata[property_name]
	)

	if not metadata["editable"]:

		return {
			"success": false,
			"error": (
				"Property is read-only: "
				+ property_name
			)
		}

	if not FileAccess.file_exists(resource_path):

		return {
			"success": false,
			"error": (
				"assign_resource_to_property: "
				+ "resource not found: "
				+ resource_path
			)
		}

	var loaded: Variant = load(resource_path)

	if loaded == null:

		return {
			"success": false,
			"error": (
				"assign_resource_to_property: "
				+ "resource could not be loaded: "
				+ resource_path
			)
		}

	if not (loaded is Resource):

		return {
			"success": false,
			"error": (
				"assign_resource_to_property: "
				+ "resource is not a Resource: "
				+ resource_path
			)
		}

	var old_value: Variant = (
		target_node.get(property_name)
	)

	var old_resource_path: String = ""

	if old_value is Resource:

		old_resource_path = (
			old_value.resource_path
		)

	# Deterministic idempotent case: the same resource is
	# already assigned.

	if old_resource_path == resource_path:

		return {
			"success": true,
			"action": "assign_resource_to_property",
			"message": (
				"Resource is already assigned; no "
				+ "change was made."
			),
			"node_path": (
				scene_helpers
				.get_relative_node_path(
					edited_scene_root,
					target_node
				)
			),
			"node_name": str(target_node.name),
			"property_name": property_name,
			"resource_path": resource_path,
			"previous_resource_path": old_resource_path,
			"changed": false,
			"verified_assignment": true,
			"undoable": false
		}

	if undo_redo == null:

		return {
			"success": false,
			"action": "assign_resource_to_property",
			"error": (
				"assign_resource_to_property requires "
				+ "the plugin-owned "
				+ "EditorUndoRedoManager, which is only "
				+ "available inside the running Godot "
				+ "editor."
			)
		}

	undo_redo.create_action(
		"AI Agent: Assign "
		+ resource_path.get_file()
		+ " to "
		+ str(target_node.name)
		+ "."
		+ property_name
	)

	undo_redo.add_do_property(
		target_node,
		property_name,
		loaded
	)

	undo_redo.add_undo_property(
		target_node,
		property_name,
		old_value
	)

	undo_redo.commit_action()

	# Post-mutation verification: read the real property
	# back and compare resource paths.

	var assigned: Variant = (
		target_node.get(property_name)
	)

	var assigned_path: String = ""

	if assigned is Resource:

		assigned_path = (
			assigned.resource_path
		)

	var verified: bool = (
		assigned_path == resource_path
	)

	return {
		"success": true,
		"action": "assign_resource_to_property",
		"message": (
			"Resource assigned successfully in "
			+ "the Godot editor."
		),
		"node_path": (
			scene_helpers
			.get_relative_node_path(
				edited_scene_root,
				target_node
			)
		),
		"node_name": str(target_node.name),
		"property_name": property_name,
		"resource_path": resource_path,
		"previous_resource_path": old_resource_path,
		"changed": true,
		"verified_assignment": verified,
		"undoable": true
	}


# ==========================================
# get_resource_info
# ==========================================
# Read-only identity check for one resource file,
# answered from the real loaded resource.


func get_resource_info_from_request(
	data: Dictionary
) -> Dictionary:

	var path_check := (
		_normalize_resource_file_path(
			data.get("resource_path"),
			"get_resource_info"
		)
	)

	if not path_check.get("ok", false):
		return path_check

	var resource_path: String = (
		path_check["resource_path"]
	)

	if not FileAccess.file_exists(resource_path):

		return {
			"success": false,
			"error": (
				"get_resource_info: resource not "
				+ "found: "
				+ resource_path
			)
		}

	var loaded: Variant = load(resource_path)

	if loaded == null:

		return {
			"success": false,
			"error": (
				"get_resource_info: resource could "
				+ "not be loaded: "
				+ resource_path
			)
		}

	if not (loaded is Resource):

		return {
			"success": false,
			"error": (
				"get_resource_info: resource is "
				+ "not a Resource: "
				+ resource_path
			)
		}

	var resource: Resource = loaded

	return {
		"success": true,
		"action": "get_resource_info",
		"resource_path": resource_path,
		"resource_class": resource.get_class(),
		"resource_name": resource.resource_name,
		# Some Resource subclasses (e.g. CompressedTexture2D) do
		# not expose local_to_scene through their property list,
		# so read it defensively instead of via member access.
		"local_to_scene": resource.get("local_to_scene"),
	}


# ==========================================
# set_project_settings
# ==========================================
# Project-level configuration mutation (e.g. display
# resolution, window flags, physics values). Works
# headless and in the editor. Not undoable: the result
# reports every key's previous value so the human can
# revert, and the values persist to project.godot when
# the editor saves the project. Sensitive keys are
# rejected outright.

const SENSITIVE_SETTING_TOKENS := [
	"password",
	"token",
	"secret",
	"api_key",
	"credential",
	"private_key",
]

const MAX_SETTINGS_PER_CALL := 10


func set_project_settings_from_request(
	data: Dictionary
) -> Dictionary:

	if not data.has("settings"):

		return {
			"success": false,
			"error": (
				"set_project_settings requires "
				+ "settings."
			)
		}

	if not (data["settings"] is Dictionary):

		return {
			"success": false,
			"error": (
				"set_project_settings settings "
				+ "must be an object."
			)
		}

	var requested: Dictionary = data["settings"]

	if requested.is_empty():

		return {
			"success": false,
			"error": (
				"set_project_settings requires at "
				+ "least one setting."
			)
		}

	if requested.size() > MAX_SETTINGS_PER_CALL:

		return {
			"success": false,
			"error": (
				"set_project_settings accepts at "
				+ "most "
				+ str(MAX_SETTINGS_PER_CALL)
				+ " settings per call."
			)
		}

	# Sensitive settings are rejected before anything is
	# touched - names only are ever surfaced.

	for setting_name in requested:

		var lower_name := str(setting_name).to_lower()

		for token in SENSITIVE_SETTING_TOKENS:

			if token in lower_name:

				return {
					"success": false,
					"error": (
						"set_project_settings refuses "
						+ "sensitive setting keys ("
						+ "matched: "
						+ token
						+ ")."
					)
				}

	# Validate and prepare every change BEFORE applying
	# any of them, mirroring set_properties.

	var prepared: Array = []

	for setting_name in requested:

		var key := str(setting_name).strip_edges()

		if key.is_empty():

			return {
				"success": false,
				"error": (
					"set_project_settings requires "
					+ "non-empty setting names."
				)
			}

		var had_previous: bool = (
			ProjectSettings.has_setting(key)
		)

		var previous_value: Variant = null

		var type_id: int = TYPE_NIL

		if had_previous:

			previous_value = (
				ProjectSettings.get_setting(key)
			)

			type_id = typeof(previous_value)

		var deserialize_result := (
			variant_serializer
			.deserialize_property_value(
				requested[setting_name],
				type_id
			)
		)

		if not deserialize_result["success"]:

			return {
				"success": false,
				"error": (
					"Invalid value for setting "
					+ key
					+ ": "
					+ str(deserialize_result["error"])
				)
			}

		prepared.append(
			{
				"key": key,
				"had_previous": had_previous,
				"previous_value": previous_value,
				"new_value": deserialize_result[
					"value"
				],
			}
		)

	# Apply all changes, then verify each by reading back.

	var results: Array = []

	var all_verified := true

	for change in prepared:

		ProjectSettings.set_setting(
			change["key"],
			change["new_value"]
		)

		var read_back: Variant = (
			ProjectSettings.get_setting(
				change["key"]
			)
		)

		var verified: bool = (
			read_back == change["new_value"]
		)

		if not verified:
			all_verified = false

		results.append(
			{
				"key": change["key"],
				"previous_value": (
					variant_serializer
					.serialize_property_value(
						change["previous_value"]
					)
					if change["had_previous"]
					else null
				),
				"had_previous": change[
					"had_previous"
				],
				"new_value": (
					variant_serializer
					.serialize_property_value(
						change["new_value"]
					)
				),
				"verified": verified,
			}
		)

	return {
		"success": true,
		"action": "set_project_settings",
		"message": (
			"Project settings updated. Values persist "
			+ "to project.godot when the editor saves "
			+ "the project. Previous values are "
			+ "reported for manual revert."
		),
		"setting_count": results.size(),
		"settings": results,
		"changed": true,
		"verified_settings": all_verified,
		"undoable": false
	}


# ==========================================
# create_resource
# ==========================================
# File-backed .tres resource creation with type-aware
# property application. Complements
# assign_resource_to_property: create, then assign.
# Never overwrites; verified by loading the file back.


func _normalize_tres_path(
	raw_path,
	action_name: String
) -> Dictionary:

	var path_check := (
		_normalize_resource_file_path(
			raw_path,
			action_name
		)
	)

	if not path_check.get("ok", false):
		return path_check

	var resource_path: String = (
		path_check["resource_path"]
	)

	if not resource_path.ends_with(".tres"):

		return {
			"success": false,
			"error": (
				action_name
				+ " requires a resource_path "
				+ "ending in .tres."
			)
		}

	return {
		"ok": true,
		"resource_path": resource_path
	}


func create_resource_from_request(
	data: Dictionary
) -> Dictionary:

	var path_check := (
		_normalize_tres_path(
			data.get("resource_path"),
			"create_resource"
		)
	)

	if not path_check.get("ok", false):
		return path_check

	var resource_path: String = (
		path_check["resource_path"]
	)

	if not data.has("resource_type"):

		return {
			"success": false,
			"error": (
				"create_resource requires "
				+ "resource_type."
			)
		}

	if typeof(data["resource_type"]) != TYPE_STRING:

		return {
			"success": false,
			"error": (
				"create_resource resource_type "
				+ "must be a string."
			)
		}

	var resource_type: String = (
		str(data["resource_type"]).strip_edges()
	)

	if resource_type.is_empty():

		return {
			"success": false,
			"error": (
				"create_resource requires a "
				+ "non-empty resource_type."
			)
		}

	# The bridge is authoritative over the class
	# namespace: only instantiable Resource types are
	# accepted (never Nodes, never abstract classes).

	if not ClassDB.class_exists(resource_type):

		return {
			"success": false,
			"error": (
				"create_resource: unknown class "
				+ "name: "
				+ resource_type
			)
		}

	if not ClassDB.can_instantiate(resource_type):

		return {
			"success": false,
			"error": (
				"create_resource: class cannot be "
				+ "instantiated directly: "
				+ resource_type
			)
		}

	var new_resource: Variant = ClassDB.instantiate(
		resource_type
	)

	if not (new_resource is Resource):

		return {
			"success": false,
			"error": (
				"create_resource: "
				+ resource_type
				+ " is not a Resource type."
			)
		}

	var resource: Resource = new_resource

	if FileAccess.file_exists(resource_path):

		return {
			"success": false,
			"error": (
				"create_resource: resource already "
				+ "exists: "
				+ resource_path
				+ ". Existing resources are never "
				+ "overwritten."
			)
		}

	if not data.has("properties"):

		return {
			"success": false,
			"error": (
				"create_resource requires "
				+ "properties."
			)
		}

	if not (data["properties"] is Dictionary):

		return {
			"success": false,
			"error": (
				"create_resource properties must "
				+ "be an object."
			)
		}

	var requested: Dictionary = data["properties"]

	if requested.size() > MAX_SETTINGS_PER_CALL:

		return {
			"success": false,
			"error": (
				"create_resource accepts at most "
				+ str(MAX_SETTINGS_PER_CALL)
				+ " properties per call."
			)
		}

	# Validate and prepare all properties before applying
	# any, mirroring set_properties.

	var prepared: Array = []

	for property_name in requested:

		var key := str(property_name).strip_edges()

		if key.is_empty():

			return {
				"success": false,
				"error": (
					"create_resource requires "
					+ "non-empty property names."
				)
			}

		# Unknown properties are rejected explicitly:
		# Object.set() silently ignores them, which would
		# make a "created" resource silently wrong.

		if not (key in resource):

			return {
				"success": false,
				"error": (
					"Property not found on resource "
					+ "type "
					+ resource_type
					+ ": "
					+ key
				)
			}

		var current_value: Variant = (
			resource.get(key)
		)

		var type_id: int = typeof(current_value)

		var deserialize_result := (
			variant_serializer
			.deserialize_property_value(
				requested[property_name],
				type_id
			)
		)

		if not deserialize_result["success"]:

			return {
				"success": false,
				"error": (
					"Invalid value for property "
					+ key
					+ ": "
					+ str(deserialize_result["error"])
				)
			}

		prepared.append(
			{
				"key": key,
				"value": deserialize_result["value"],
			}
		)

	for change in prepared:

		resource.set(
			change["key"],
			change["value"]
		)

	# Create missing parent directories, mirroring
	# create_script.

	var target_dir: String = resource_path.get_base_dir()

	var needs_dir: bool = (
		target_dir.length() > len("res://")
		and not DirAccess.dir_exists_absolute(target_dir)
	)

	if needs_dir:

		var mkdir_error := (
			DirAccess.make_dir_recursive_absolute(
				target_dir
			)
		)

		if mkdir_error != OK:

			return {
				"success": false,
				"error": (
					"create_resource: could not "
					+ "create directory "
					+ target_dir
					+ ". Error: "
					+ error_string(mkdir_error)
				)
			}

	var save_error := ResourceSaver.save(
		resource,
		resource_path
	)

	if save_error != OK:

		return {
			"success": false,
			"error": (
				"create_resource: could not save "
				+ "the resource. Error: "
				+ error_string(save_error)
			)
		}

	# Post-create verification: load the file back and
	# confirm the resource type.

	var verify_load: Variant = load(resource_path)

	var verified_write: bool = (
		verify_load is Resource
		and verify_load.get_class() == resource_type
	)

	return {
		"success": true,
		"action": "create_resource",
		"message": (
			"Resource created successfully in the "
			+ "project."
		),
		"resource_path": resource_path,
		"resource_type": resource_type,
		"property_count": prepared.size(),
		"changed": true,
		"verified_write": verified_write,
		"undoable": false
	}
