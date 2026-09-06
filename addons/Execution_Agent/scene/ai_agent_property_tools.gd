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
