@tool
extends RefCounted

class_name AIAgentSceneHelpers


var editor_interface: EditorInterface


func _init(
	p_editor_interface: EditorInterface
) -> void:

	editor_interface = (
		p_editor_interface
	)


# ==========================================
# Edited scene
# ==========================================


func get_edited_scene_root_or_error() -> Dictionary:

	var edited_scene_root := (
		editor_interface
		.get_edited_scene_root()
	)

	if edited_scene_root == null:

		return {
			"success": false,
			"error": (
				"No edited scene is currently open."
			)
		}

	return {
		"success": true,
		"scene_root": edited_scene_root
	}


# ==========================================
# Node paths
# ==========================================


func normalize_scene_relative_path(
	node_path: String
) -> String:

	var normalized_path := (
		node_path.strip_edges()
	)

	# Empty paths and "." both refer to the
	# currently edited scene root.
	if (
		normalized_path.is_empty()
		or normalized_path == "."
	):

		return "."

	# The AI may occasionally use Godot's
	# SceneTree-style "/root" path when it means
	# the root of the currently edited scene.
	#
	# Never allow that absolute path to escape
	# into the SceneTree root. Convert it into
	# this plugin's scene-relative path contract.
	if normalized_path == "/root":

		return "."

	if normalized_path.begins_with(
		"/root/"
	):

		normalized_path = (
			normalized_path.substr(
				6
			)
		)

	# This bridge operates only inside the
	# currently edited scene. No other absolute
	# NodePath is valid through the public API.
	if normalized_path.begins_with(
		"/"
	):

		return ""

	return normalized_path


func get_relative_node_path(
	edited_scene_root: Node,
	target_node: Node
) -> String:

	if target_node == edited_scene_root:
		return "."

	return str(
		edited_scene_root.get_path_to(
			target_node
		)
	)


func resolve_node_or_error(
	node_path: String
) -> Dictionary:

	var scene_result := (
		get_edited_scene_root_or_error()
	)

	if not scene_result["success"]:
		return scene_result

	var edited_scene_root: Node = (
		scene_result["scene_root"]
	)

	var normalized_path := (
		normalize_scene_relative_path(
			node_path
		)
	)

	if normalized_path.is_empty():

		return {
			"success": false,
			"error": (
				"Absolute node paths are not "
				+ "allowed. Paths must be relative "
				+ "to the currently edited scene."
			)
		}

	var target_node: Node = null

	if normalized_path == ".":

		target_node = edited_scene_root

	else:

		target_node = (
			edited_scene_root
			.get_node_or_null(
				NodePath(
					normalized_path
				)
			)
		)

	if target_node == null:

		return {
			"success": false,
			"error": (
				"Node not found: "
				+ normalized_path
			)
		}

	return {
		"success": true,
		"scene_root": edited_scene_root,
		"node": target_node,
		"normalized_path": normalized_path
	}