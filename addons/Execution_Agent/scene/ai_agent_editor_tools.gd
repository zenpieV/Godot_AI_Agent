@tool
extends RefCounted

class_name AIAgentEditorTools


var editor_interface: EditorInterface
var undo_redo: EditorUndoRedoManager


func _init(
	p_editor_interface: EditorInterface,
	p_undo_redo: EditorUndoRedoManager
) -> void:

	editor_interface = p_editor_interface

	undo_redo = p_undo_redo


# ==========================================
# list_autoloads
# ==========================================


func list_autoloads() -> Dictionary:

	var autoloads: Array = []

	for property in ProjectSettings.get_property_list():

		var setting_name := str(
			property.get("name", "")
		)

		if not setting_name.begins_with("autoload/"):
			continue

		var autoload_name := setting_name.substr(
			"autoload/".length()
		)
		var raw_target := str(
			ProjectSettings.get_setting(setting_name)
		)
		var target := raw_target

		if target.begins_with("*"):
			target = target.substr(1)

		autoloads.append({
			"name": autoload_name,
			"path": target,
			"resource_target": raw_target
		})

	autoloads.sort_custom(
		func(left: Dictionary, right: Dictionary) -> bool:
			return str(left["name"]) < str(right["name"])
	)

	return {
		"success": true,
		"action": "list_autoloads",
		"autoloads": autoloads,
		"count": autoloads.size()
	}


# ==========================================
# get_editor_state
# ==========================================


func get_editor_state() -> Dictionary:

	if editor_interface == null:
		return _editor_unavailable("get_editor_state")

	var edited_scene_root: Node = (
		editor_interface.get_edited_scene_root()
	)
	var edited_scene_exists := edited_scene_root != null
	var edited_scene_path := ""
	var edited_scene_name := ""
	var edited_scene_type := ""

	if edited_scene_exists:
		edited_scene_path = str(
			edited_scene_root.scene_file_path
		)
		edited_scene_name = str(
			edited_scene_root.name
		)
		edited_scene_type = edited_scene_root.get_class()

	var open_scenes: Array = []
	for scene_path in editor_interface.get_open_scenes():
		open_scenes.append(str(scene_path))
	open_scenes.sort()

	var selected_nodes: Array = []
	var selection := editor_interface.get_selection()

	if selection != null:
		for selected_node in selection.get_selected_nodes():
			if not selected_node is Node:
				continue

			var node: Node = selected_node
			var node_path := str(node.get_path())

			if edited_scene_root != null:
				if node == edited_scene_root:
					node_path = "."
				elif edited_scene_root.is_ancestor_of(node):
					node_path = str(
						edited_scene_root.get_path_to(node)
					)

			selected_nodes.append({
				"name": str(node.name),
				"node_type": node.get_class(),
				"path": node_path
			})

	selected_nodes.sort_custom(
		func(left: Dictionary, right: Dictionary) -> bool:
			return str(left["path"]) < str(right["path"])
	)

	var playing_scene_path := str(
		editor_interface.get_playing_scene()
	)

	return {
		"success": true,
		"action": "get_editor_state",
		"edited_scene_exists": edited_scene_exists,
		"edited_scene_path": edited_scene_path,
		"edited_scene_name": edited_scene_name,
		"edited_scene_type": edited_scene_type,
		"open_scenes": open_scenes,
		"selected_nodes": selected_nodes,
		"selection_count": selected_nodes.size(),
		"is_playing_scene": editor_interface.is_playing_scene(),
		"playing_scene_path": playing_scene_path
	}


# ==========================================
# list_scenes_in_project
# ==========================================


func list_scenes_in_project() -> Dictionary:

	if editor_interface == null:
		return _editor_unavailable("list_scenes_in_project")

	var filesystem := editor_interface.get_resource_filesystem()

	if filesystem == null:
		return {
			"success": false,
			"action": "list_scenes_in_project",
			"error": "The editor resource filesystem is unavailable."
		}

	if filesystem.is_scanning() or filesystem.is_importing():
		return {
			"success": false,
			"action": "list_scenes_in_project",
			"error": "The editor resource filesystem is still scanning or importing.",
			"scanning": filesystem.is_scanning(),
			"importing": filesystem.is_importing()
		}

	var scenes: Array = []
	var filesystem_root := filesystem.get_filesystem()

	if filesystem_root != null:
		_collect_scene_paths(filesystem_root, scenes)

	scenes.sort()

	return {
		"success": true,
		"action": "list_scenes_in_project",
		"scenes": scenes,
		"count": scenes.size(),
		"scanning": false,
		"importing": false
	}


func _collect_scene_paths(
	directory: EditorFileSystemDirectory,
	scenes: Array
) -> void:

	for file_index in range(directory.get_file_count()):

		if directory.get_file_type(file_index) == "PackedScene":
			scenes.append(
				str(directory.get_file_path(file_index))
			)

	for directory_index in range(directory.get_subdir_count()):
		_collect_scene_paths(
			directory.get_subdir(directory_index),
			scenes
		)


# ==========================================
# get_undo_history_summary
# ==========================================


func get_undo_history_summary() -> Dictionary:

	if undo_redo == null:
		return _editor_unavailable("get_undo_history_summary")

	var histories: Array = []
	var undo_available := false
	var redo_available := false
	var current_action_name := ""

	var global_history := undo_redo.get_history_undo_redo(
		EditorUndoRedoManager.GLOBAL_HISTORY
	)

	if global_history != null:
		var global_summary := _summarize_history(
			"global",
			EditorUndoRedoManager.GLOBAL_HISTORY,
			global_history
		)
		histories.append(global_summary)
		undo_available = undo_available or global_summary["undo_available"]
		redo_available = redo_available or global_summary["redo_available"]
		current_action_name = str(
			global_summary["current_action_name"]
		)

	var scene_root: Node = null

	if editor_interface != null:
		scene_root = editor_interface.get_edited_scene_root()

	if scene_root != null:
		var scene_history_id := undo_redo.get_object_history_id(
			scene_root
		)
		var scene_history := undo_redo.get_history_undo_redo(
			scene_history_id
		)

		if scene_history != null:
			var scene_summary := _summarize_history(
				"edited_scene",
				scene_history_id,
				scene_history
			)
			histories.append(scene_summary)
			undo_available = undo_available or scene_summary["undo_available"]
			redo_available = redo_available or scene_summary["redo_available"]
			if current_action_name.is_empty():
				current_action_name = str(
					scene_summary["current_action_name"]
				)

	return {
		"success": true,
		"action": "get_undo_history_summary",
		"undo_available": undo_available,
		"redo_available": redo_available,
		"current_action_name": current_action_name,
		"histories": histories
	}


func _summarize_history(
	label: String,
	history_id: int,
	history: UndoRedo
) -> Dictionary:

	return {
		"label": label,
		"history_id": history_id,
		"undo_available": history.has_undo(),
		"redo_available": history.has_redo(),
		"action_count": history.get_action_count(),
		"current_action_name": history.get_current_action_name()
	}


func _editor_unavailable(action_name: String) -> Dictionary:

	return {
		"success": false,
		"action": action_name,
		"error": (
			"This inspection requires the running Godot editor."
		)
	}
