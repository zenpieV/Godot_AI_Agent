@tool
extends RefCounted

class_name AIAgentSceneFileTools


var scene_helpers: AIAgentSceneHelpers
var editor_interface: EditorInterface
var undo_redo: EditorUndoRedoManager

const MAX_DEPENDENCIES := 200


func _init(
	p_scene_helpers: AIAgentSceneHelpers,
	p_editor_interface: EditorInterface,
	p_undo_redo: EditorUndoRedoManager
) -> void:

	scene_helpers = p_scene_helpers

	editor_interface = p_editor_interface

	undo_redo = p_undo_redo


# ==========================================
# Scene file tools
# ==========================================
# Scene FILE operations for the project: saving the
# edited scene, creating new scene files, instancing
# scenes into the edited scene, and inspecting scene
# files without opening them.
#
# Contract notes:
#
# - save_scene and list_open_scenes require the running
#   editor and report the explicit unavailable error
#   headless (same pattern as the editor tools).
# - create_scene writes a file: not undoable, never
#   overwrites, and deliberately does NOT open the scene
#   (opening changes the edited-scene context and would
#   invalidate the conversation's node paths).
# - instantiate_scene is an editor-native, undoable
#   EditorUndoRedoManager action with read-back
#   verification.
# - Scene path handling is strict: res:// scheme
#   (auto-prefixed), .tscn extension required, no
#   directory traversal, no backslashes.


func _normalize_scene_file_path(
	raw_path,
	action_name: String
) -> Dictionary:

	if typeof(raw_path) != TYPE_STRING:

		return {
			"success": false,
			"error": (
				action_name
				+ " requires scene_path."
			)
		}

	var scene_path: String = (
		str(raw_path).strip_edges()
	)

	if scene_path.is_empty():

		return {
			"success": false,
			"error": (
				action_name
				+ " requires a non-empty "
				+ "scene_path."
			)
		}

	if not scene_path.begins_with("res://"):

		scene_path = (
			"res://"
			+ scene_path
		)

	if scene_path.length() <= len("res://"):

		return {
			"success": false,
			"error": (
				action_name
				+ " requires a scene file name."
			)
		}

	if scene_path.contains("\\"):

		return {
			"success": false,
			"error": (
				action_name
				+ " scene_path must use "
				+ "forward slashes."
			)
		}

	if scene_path.contains(".."):

		return {
			"success": false,
			"error": (
				action_name
				+ " scene_path must not "
				+ "contain directory traversal."
			)
		}

	if not scene_path.ends_with(".tscn"):

		return {
			"success": false,
			"error": (
				action_name
				+ " requires a scene_path "
				+ "ending in .tscn."
			)
		}

	if scene_path.get_file() == ".tscn":

		return {
			"success": false,
			"error": (
				action_name
				+ " requires a non-empty "
				+ "scene file name."
			)
		}

	return {
		"ok": true,
		"scene_path": scene_path
	}


func _load_packed_scene(
	scene_path: String,
	action_name: String
) -> Dictionary:

	if not FileAccess.file_exists(scene_path):

		return {
			"success": false,
			"error": (
				action_name + ": scene not found: "
				+ scene_path
			)
		}

	var packed: Variant = load(scene_path)

	if packed == null:

		return {
			"success": false,
			"error": (
				action_name + ": scene could not "
				+ "be loaded: "
				+ scene_path
			)
		}

	if not (packed is PackedScene):

		return {
			"success": false,
			"error": (
				action_name + ": resource is not a "
				+ "PackedScene: "
				+ scene_path
			)
		}

	return {
		"ok": true,
		"packed": packed
	}


# ==========================================
# save_scene
# ==========================================


func save_scene_from_request(
	_data: Dictionary
) -> Dictionary:

	if editor_interface == null:

		return {
			"success": false,
			"action": "save_scene",
			"error": (
				"save_scene requires the running "
				+ "Godot editor."
			)
		}

	var edited_scene_root: Node = (
		editor_interface.get_edited_scene_root()
	)

	if edited_scene_root == null:

		return {
			"success": false,
			"action": "save_scene",
			"error": (
				"No edited scene is currently open."
			)
		}

	var scene_path: String = (
		edited_scene_root.scene_file_path
	)

	if scene_path.is_empty():

		return {
			"success": false,
			"action": "save_scene",
			"error": (
				"The edited scene has never been "
				+ "saved and has no file path yet. "
				+ "Use create_scene to create a "
				+ "scene file first."
			)
		}

	var save_error := editor_interface.save_scene()

	if save_error != OK:

		return {
			"success": false,
			"action": "save_scene",
			"error": (
				"save_scene failed. Error: "
				+ error_string(save_error)
			)
		}

	# Post-save verification: save_scene's Error return is
	# the authoritative write signal (a failed write
	# returns non-OK and never reaches this point), and
	# the file must exist on disk. The mtime comparison
	# is intentionally NOT load-bearing: it has
	# whole-second granularity, so two saves within one
	# second would false-negative.

	var modified_after: int = (
		FileAccess.get_modified_time(scene_path)
	)

	var verified_write: bool = (
		FileAccess.file_exists(scene_path)
	)

	return {
		"success": verified_write,
		"action": "save_scene",
		"message": (
			"Scene saved successfully in the "
			+ "Godot editor."
			if verified_write
			else "save_scene reported success but "
			+ "the scene file is missing on disk."
		),
		"scene_path": scene_path,
		"scene_name": str(edited_scene_root.name),
		"modified_time": modified_after,
		"changed": true,
		"verified_write": verified_write,
		"undoable": false
	}


# ==========================================
# create_scene
# ==========================================


func create_scene_from_request(
	data: Dictionary
) -> Dictionary:

	var path_check := (
		_normalize_scene_file_path(
			data.get("scene_path"),
			"create_scene"
		)
	)

	if not path_check.get("ok", false):
		return path_check

	var scene_path: String = (
		path_check["scene_path"]
	)

	if not data.has("root_node_type"):

		return {
			"success": false,
			"error": (
				"create_scene requires "
				+ "root_node_type."
			)
		}

	if typeof(data["root_node_type"]) != TYPE_STRING:

		return {
			"success": false,
			"error": (
				"create_scene root_node_type must "
				+ "be a string."
			)
		}

	var root_node_type: String = (
		str(data["root_node_type"]).strip_edges()
	)

	if root_node_type.is_empty():

		return {
			"success": false,
			"error": (
				"create_scene requires a non-empty "
				+ "root_node_type."
			)
		}

	# The bridge is the authoritative environment for
	# validating node types: never create a scene rooted
	# in a type the running engine cannot instantiate.

	if not ClassDB.class_exists(root_node_type):

		return {
			"success": false,
			"error": (
				"create_scene: unknown class name: "
				+ root_node_type
			)
		}

	if not ClassDB.can_instantiate(root_node_type):

		return {
			"success": false,
			"error": (
				"create_scene: class cannot be "
				+ "instantiated directly: "
				+ root_node_type
			)
		}

	var new_node: Variant = ClassDB.instantiate(
		root_node_type
	)

	if not new_node is Node:

		return {
			"success": false,
			"error": (
				"create_scene: "
				+ root_node_type
				+ " is not a Node type."
			)
		}

	if FileAccess.file_exists(scene_path):

		return {
			"success": false,
			"error": (
				"create_scene: scene already "
				+ "exists: "
				+ scene_path
				+ ". Existing scenes are never "
				+ "overwritten."
			)
		}

	var root_name: String = (
		scene_path.get_basename().get_file()
	)

	var typed_root: Node = new_node as Node

	typed_root.name = root_name

	var packed := PackedScene.new()

	var pack_error := packed.pack(typed_root)

	if pack_error != OK:

		typed_root.free()

		return {
			"success": false,
			"error": (
				"create_scene: could not pack the "
				+ "root node. Error: "
				+ error_string(pack_error)
			)
		}

	# Create missing parent directories, mirroring
	# create_script.

	var target_dir: String = scene_path.get_base_dir()

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

			typed_root.free()

			return {
				"success": false,
				"error": (
					"create_scene: could not create "
					+ "directory "
					+ target_dir
					+ ". Error: "
					+ error_string(mkdir_error)
				)
			}

	var save_error := ResourceSaver.save(
		packed,
		scene_path
	)

	typed_root.free()

	if save_error != OK:

		return {
			"success": false,
			"error": (
				"create_scene: could not save the "
				+ "scene. Error: "
				+ error_string(save_error)
			)
		}

	# Post-create verification: load the file back and
	# instantiate the root to confirm type and name.

	var verify_result := (
		_load_packed_scene(
			scene_path,
			"create_scene"
		)
	)

	var verified_write: bool = false

	var verified_root_type: String = ""

	var verified_root_name: String = ""

	if verify_result.get("ok", false):

		var check_scene: PackedScene = (
			verify_result["packed"]
		)

		var check_root: Node = (
			check_scene.instantiate()
		)

		if check_root != null:

			verified_root_type = (
				check_root.get_class()
			)

			verified_root_name = (
				str(check_root.name)
			)

			verified_write = (
				check_root.get_class()
				== root_node_type
				and str(check_root.name) == root_name
			)

			check_root.free()

	# Soft convention nudge: root placement is legal but
	# usually a mistake for scenes.

	var root_hint: bool = (
		scene_path.get_base_dir() == "res://"
	)

	return {
		"success": true,
		"action": "create_scene",
		"message": (
			"Scene created successfully in the "
			+ "project. Note: file placed in the "
			+ "project root; prefer the project's "
			+ "folder conventions (scenes/, ...)."
			if root_hint
			else "Scene created successfully in the "
			+ "project."
		),
		"scene_path": scene_path,
		"root_node_type": root_node_type,
		"root_name": verified_root_name,
		"root_directory_hint": root_hint,
		"changed": true,
		"verified_write": verified_write,
		"undoable": false
	}


# ==========================================
# instantiate_scene
# ==========================================


func instantiate_scene_from_request(
	data: Dictionary
) -> Dictionary:

	if not data.has("parent_path"):

		return {
			"success": false,
			"error": (
				"instantiate_scene requires "
				+ "parent_path."
			)
		}

	var path_check := (
		_normalize_scene_file_path(
			data.get("scene_path"),
			"instantiate_scene"
		)
	)

	if not path_check.get("ok", false):
		return path_check

	var scene_path: String = (
		path_check["scene_path"]
	)

	var parent_path: String = (
		str(data["parent_path"]).strip_edges()
	)

	var parent_result: Dictionary = (
		scene_helpers
		.resolve_node_or_error(
			parent_path
		)
	)

	if not parent_result["success"]:
		return parent_result

	var parent_node: Node = (
		parent_result["node"]
	)

	var edited_scene_root: Node = (
		parent_result["scene_root"]
	)

	var load_result := (
		_load_packed_scene(
			scene_path,
			"instantiate_scene"
		)
	)

	if not load_result.get("ok", false):
		return load_result

	var packed_scene: PackedScene = (
		load_result["packed"]
	)

	var instanced: Node = (
		packed_scene.instantiate()
	)

	if instanced == null:

		return {
			"success": false,
			"error": (
				"instantiate_scene: scene could "
				+ "not be instantiated: "
				+ scene_path
			)
		}

	# Name resolution: explicit new_name wins, then the
	# instanced root's own name, then the scene file name.

	var requested_name: String = ""

	if data.has("new_name"):

		if typeof(data["new_name"]) != TYPE_STRING:

			instanced.free()

			return {
				"success": false,
				"error": (
					"instantiate_scene new_name "
					+ "must be a string."
				)
			}

		requested_name = (
			str(data["new_name"]).strip_edges()
		)

	if requested_name.is_empty():

		requested_name = str(instanced.name)

	if requested_name.is_empty():

		requested_name = (
			scene_path.get_basename().get_file()
		)

	instanced.name = requested_name

	# The editor undo manager is only available inside
	# the running editor; a headless SceneTree process
	# reports an explicit unavailable error instead of
	# mutating without undo support.

	if undo_redo == null:

		instanced.free()

		return {
			"success": false,
			"action": "instantiate_scene",
			"error": (
				"instantiate_scene requires the plugin-owned "
				+ "EditorUndoRedoManager, which is only "
				+ "available inside the running Godot "
				+ "editor."
			)
		}

	undo_redo.create_action(
		"AI Agent: Instance "
		+ scene_path
		+ " under "
		+ str(parent_node.name)
	)

	undo_redo.add_do_method(
		parent_node,
		"add_child",
		instanced
	)

	undo_redo.add_do_method(
		instanced,
		"set_owner",
		edited_scene_root
	)

	undo_redo.add_undo_method(
		parent_node,
		"remove_child",
		instanced
	)

	undo_redo.commit_action()

	# Post-mutation verification: read the real child
	# back. add_child() silently renames on name
	# conflicts, so the actual name is reported.

	var is_child: bool = (
		instanced.get_parent() == parent_node
	)

	var actual_name: String = str(instanced.name)

	var actual_path: String = (
		scene_helpers
		.get_relative_node_path(
			edited_scene_root,
			instanced
		)
	)

	var verified_instance: bool = (
		is_child
		and instanced.scene_file_path == scene_path
	)

	# Success policy: an unverified instance is a failure
	# (the undo already ran with the action; the agent
	# must know the child did not land).

	return {
		"success": verified_instance,
		"action": "instantiate_scene",
		"message": (
			"Scene instanced successfully in the "
			+ "Godot editor."
			if verified_instance
			else "instantiate_scene could not verify "
			+ "the instanced child after the commit."
		),
		"scene_path": scene_path,
		"parent_path": parent_path,
		"node_path": actual_path,
		"node_name": actual_name,
		"requested_name": requested_name,
		"changed": true,
		"verified_instance": verified_instance,
		"undoable": true
	}


# ==========================================
# get_scene_dependencies
# ==========================================
# Read-only dependency inspection answered from the
# loaded PackedScene state - never by parsing the file
# text. The scene is instantiated WITHOUT entering the
# tree and freed immediately; the currently edited scene
# is untouched.


func get_scene_dependencies_from_request(
	data: Dictionary
) -> Dictionary:

	var path_check := (
		_normalize_scene_file_path(
			data.get("scene_path"),
			"get_scene_dependencies"
		)
	)

	if not path_check.get("ok", false):
		return path_check

	var scene_path: String = (
		path_check["scene_path"]
	)

	var load_result := (
		_load_packed_scene(
			scene_path,
			"get_scene_dependencies"
		)
	)

	if not load_result.get("ok", false):
		return load_result

	var packed_scene: PackedScene = (
		load_result["packed"]
	)

	var state := packed_scene.get_state()

	var sub_scenes := {}

	var resources := {}

	var omitted := 0

	for node_index in range(state.get_node_count()):

		var node_name: String = str(
			state.get_node_name(node_index)
		)

		var node_type: String = str(
			state.get_node_type(node_index)
		)

		var instanced_scene: Variant = (
			state.get_node_instance(node_index)
		)

		if instanced_scene is PackedScene:

			var sub_path: String = (
				instanced_scene.resource_path
			)

			if not sub_path.is_empty():

				if sub_scenes.size() < MAX_DEPENDENCIES:
					sub_scenes[sub_path] = node_name
				else:
					omitted += 1

		for property_index in range(
			state.get_node_property_count(
				node_index
			)
		):

			var property_value: Variant = (
				state.get_node_property_value(
					node_index,
					property_index
				)
			)

			if property_value is Resource:

				var resource_path: String = (
					property_value.resource_path
				)

				if resource_path.is_empty():
					continue

				if resources.size() < MAX_DEPENDENCIES:
					resources[resource_path] = (
						node_name
						+ "."
						+ str(
							state.get_node_property_name(
								node_index,
								property_index
							)
						)
					)
				else:
					omitted += 1

	var sub_scene_list: Array = []

	for sub_path in sub_scenes.keys():
		sub_scene_list.append(
			{
				"scene_path": sub_path,
				"used_by_node": sub_scenes[sub_path],
			}
		)

	var resource_list: Array = []

	for resource_path in resources.keys():
		resource_list.append(
			{
				"resource_path": resource_path,
				"used_by": resources[resource_path],
			}
		)

	sub_scene_list.sort_custom(
		func(a, b):
			return a["scene_path"] < b["scene_path"]
	)

	resource_list.sort_custom(
		func(a, b):
			return a["resource_path"] < b["resource_path"]
	)

	return {
		"success": true,
		"action": "get_scene_dependencies",
		"scene_path": scene_path,
		"node_count": state.get_node_count(),
		"total_sub_scenes": sub_scene_list.size(),
		"total_resources": resource_list.size(),
		"sub_scenes": sub_scene_list,
		"resources": resource_list,
		"internal_omitted": omitted,
	}


# ==========================================
# get_scene_tree_of
# ==========================================


func get_scene_tree_of_from_request(
	data: Dictionary
) -> Dictionary:

	var path_check := (
		_normalize_scene_file_path(
			data.get("scene_path"),
			"get_scene_tree_of"
		)
	)

	if not path_check.get("ok", false):
		return path_check

	var scene_path: String = (
		path_check["scene_path"]
	)

	# Optional depth bound, identical semantics to
	# get_scene_tree's max_depth.

	var max_depth := 0

	if data.has("max_depth") and data["max_depth"] != null:

		if (
			typeof(data["max_depth"]) != TYPE_INT
			and typeof(data["max_depth"]) != TYPE_FLOAT
		):

			return {
				"success": false,
				"error": (
					"get_scene_tree_of max_depth "
					+ "must be an integer between "
					+ "1 and 50."
				)
			}

		max_depth = int(data["max_depth"])

		if max_depth < 1 or max_depth > 50:

			return {
				"success": false,
				"error": (
					"get_scene_tree_of max_depth "
					+ "must be an integer between "
					+ "1 and 50."
				)
			}

	var load_result := (
		_load_packed_scene(
			scene_path,
			"get_scene_tree_of"
		)
	)

	if not load_result.get("ok", false):
		return load_result

	var packed_scene: PackedScene = (
		load_result["packed"]
	)

	var instanced: Node = (
		packed_scene.instantiate()
	)

	if instanced == null:

		return {
			"success": false,
			"error": (
				"get_scene_tree_of: scene could "
				+ "not be instantiated: "
				+ scene_path
			)
		}

	# Reuse the shared scene-tree serialization from the
	# node tools via composition; the temporary root is
	# its own relative-path root.

	var node_tools := AIAgentNodeTools.new(
		scene_helpers,
		null
	)

	var serialized := node_tools.serialize_scene_node(
		instanced,
		instanced,
		max_depth
	)

	var truncated := node_tools.tree_has_depth_truncation(
		serialized
	)

	instanced.free()

	return {
		"success": true,
		"action": "get_scene_tree_of",
		"scene_path": scene_path,
		"max_depth": max_depth,
		"truncated": truncated,
		"scene_tree": serialized,
	}


# ==========================================
# open_scene
# ==========================================
# Editor-native scene switching. Deliberately guarded:
# the bridge refuses to open while the current scene has
# unsaved changes (silent loss prevention), and the
# result warns that every node path from the previous
# scene is invalid after the switch.


func open_scene_from_request(
	data: Dictionary
) -> Dictionary:

	if editor_interface == null:

		return {
			"success": false,
			"action": "open_scene",
			"error": (
				"open_scene requires the running "
				+ "Godot editor."
			)
		}

	var path_check := (
		_normalize_scene_file_path(
			data.get("scene_path"),
			"open_scene"
		)
	)

	if not path_check.get("ok", false):
		return path_check

	var scene_path: String = (
		path_check["scene_path"]
	)

	if not FileAccess.file_exists(scene_path):

		return {
			"success": false,
			"error": (
				"open_scene: scene not found: "
				+ scene_path
			)
		}

	var edited_scene_root: Node = (
		editor_interface.get_edited_scene_root()
	)

	if edited_scene_root != null:

		var current_path: String = (
			edited_scene_root.scene_file_path
		)

		# Deterministic context switch guard: never
		# discard unsaved work silently.

		if current_path != "" \
				and editor_interface.get_unsaved_scenes().has(
					current_path
				):

			return {
				"success": false,
				"error": (
					"open_scene: the currently edited "
					+ "scene has unsaved changes ("
					+ current_path
					+ "). Call save_scene first."
				)
			}

	var previous_path: String = ""

	if edited_scene_root != null:

		previous_path = (
			edited_scene_root.scene_file_path
		)

	if scene_path == previous_path:

		return {
			"success": true,
			"action": "open_scene",
			"message": (
				"Scene is already open and edited; "
				+ "no change was made."
			),
			"scene_path": scene_path,
			"previous_scene": previous_path,
			"changed": false,
			"verified_open": true,
			"undoable": false
		}

	editor_interface.open_scene_from_path(scene_path)

	# Post-operation verification: the editor's edited
	# scene root must now be the requested file.

	var new_root: Node = (
		editor_interface.get_edited_scene_root()
	)

	var verified_open: bool = (
		new_root != null
		and new_root.scene_file_path == scene_path
	)

	# Success policy: a context switch that could not be
	# verified is a failure - reporting success while the
	# editor still shows the old scene (or no scene at
	# all) makes every node path the conversation holds
	# silently invalid.

	return {
		"success": verified_open,
		"action": "open_scene",
		"message": (
			"Scene opened successfully. All node paths "
			+ "from the previous scene are invalid; "
			+ "re-inspect before mutating."
			if verified_open
			else "open_scene could not verify the "
			+ "edited scene after the switch; the "
			+ "editor context is unchanged or "
			+ "unknown."
		),
		"scene_path": scene_path,
		"previous_scene": previous_path,
		"root_name": (
			str(new_root.name)
			if new_root != null
			else ""
		),
		"root_type": (
			new_root.get_class()
			if new_root != null
			else ""
		),
		"context_switched": true,
		"changed": true,
		"verified_open": verified_open,
		"undoable": false
	}


# ==========================================
# save_scene_as
# ==========================================
# Editor-native save-as to a NEW res:// path. Existing
# files are never overwritten (the human can do that via
# the editor's own save-as dialog).


func save_scene_as_from_request(
	data: Dictionary
) -> Dictionary:

	if editor_interface == null:

		return {
			"success": false,
			"action": "save_scene_as",
			"error": (
				"save_scene_as requires the running "
				+ "Godot editor."
			)
		}

	var edited_scene_root: Node = (
		editor_interface.get_edited_scene_root()
	)

	if edited_scene_root == null:

		return {
			"success": false,
			"action": "save_scene_as",
			"error": (
				"No edited scene is currently open."
			)
		}

	var path_check := (
		_normalize_scene_file_path(
			data.get("scene_path"),
			"save_scene_as"
		)
	)

	if not path_check.get("ok", false):
		return path_check

	var scene_path: String = (
		path_check["scene_path"]
	)

	if FileAccess.file_exists(scene_path):

		return {
			"success": false,
			"error": (
				"save_scene_as: scene already "
				+ "exists: "
				+ scene_path
				+ ". Existing scenes are never "
				+ "overwritten."
			)
		}

	var previous_path: String = (
		edited_scene_root.scene_file_path
	)

	# EditorInterface.save_scene_as() returns void in Godot
	# 4.7, so there is no error code: the write is verified
	# entirely by the post-save read-back below.

	editor_interface.save_scene_as(scene_path)

	# Post-save verification: the file exists and the
	# edited scene's path now points at the new location.

	var verified_write: bool = (
		FileAccess.file_exists(scene_path)
		and edited_scene_root.scene_file_path
			== scene_path
	)

	if not verified_write:

		return {
			"success": false,
			"action": "save_scene_as",
			"error": (
				"save_scene_as could not be verified: "
				+ "the file was not written or the "
				+ "edited scene did not switch to the "
				+ "new path."
			)
		}

	return {
		"success": true,
		"action": "save_scene_as",
		"message": (
			"Scene saved to the new path "
			+ "successfully."
		),
		"scene_path": scene_path,
		"previous_path": previous_path,
		"scene_name": str(edited_scene_root.name),
		"changed": true,
		"verified_write": verified_write,
		"undoable": false
	}


# ==========================================
# list_open_scenes
# ==========================================


func list_open_scenes_from_request(
	_data: Dictionary
) -> Dictionary:

	if editor_interface == null:

		return {
			"success": false,
			"action": "list_open_scenes",
			"error": (
				"list_open_scenes requires the "
				+ "running Godot editor."
			)
		}

	var open_scenes: PackedStringArray = (
		editor_interface.get_open_scenes()
	)

	var scenes: Array = []

	for scene_path in open_scenes:
		scenes.append(str(scene_path))

	scenes.sort()

	var edited_scene_root: Node = (
		editor_interface.get_edited_scene_root()
	)

	var edited_scene_path: String = ""

	if edited_scene_root != null:
		edited_scene_path = (
			edited_scene_root.scene_file_path
		)

	return {
		"success": true,
		"action": "list_open_scenes",
		"open_scenes": scenes,
		"count": scenes.size(),
		"edited_scene": edited_scene_path,
	}
