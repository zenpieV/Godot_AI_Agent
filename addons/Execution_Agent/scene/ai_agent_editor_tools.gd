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


# ==========================================
# Project file inspection
# ==========================================
# Bounded project filesystem inspection using plain
# DirAccess traversal, so these tools work both inside
# the running editor and in headless processes. Editor-
# internal directories (.godot, .git) are always
# excluded. Bounds mirror the bounded-listing convention
# of the other discovery tools.


const PROJECT_FILE_MAX_WALK := 5000

const PROJECT_FILE_DEFAULT_LIMIT := 100

const PROJECT_FILE_MAX_LIMIT := 500

const SEARCH_MAX_SCANNED_FILES := 500

const SEARCH_MAX_FILE_BYTES := 524288

const SEARCH_DEFAULT_EXTENSIONS := [
	"gd",
	"tscn",
	"tres",
	"cfg",
	"json",
	"md",
	"txt",
]


func _walk_project_files(
	prefix_normalized: String
) -> Dictionary:

	# Depth-first traversal of res:// below the prefix,
	# skipping editor-internal directories. Returns
	# {"ok": true, "paths": [...], "walked": int} or a
	# structured failure.

	var base_dir := "res://"

	if not prefix_normalized.is_empty():

		base_dir = (
			"res://"
			+ prefix_normalized
		)

	var dir := DirAccess.open(base_dir)

	if dir == null:

		return {
			"success": false,
			"error": (
				"Could not open project directory: "
				+ base_dir
				+ ". Error: "
				+ error_string(
					DirAccess.get_open_error()
				)
			)
		}

	var paths: Array = []

	var walked := 0

	var truncated_walk := false

	var stack: Array = [base_dir]

	while not stack.is_empty():

		if walked >= PROJECT_FILE_MAX_WALK:

			truncated_walk = true

			break

		var current_dir: String = stack.pop_back()

		if not current_dir.ends_with("/"):
			current_dir = current_dir + "/"

		var access := DirAccess.open(current_dir)

		if access == null:
			continue

		for file_name in access.get_files():

			if walked >= PROJECT_FILE_MAX_WALK:

				truncated_walk = true

				break

			var file_path := (
				current_dir
				+ file_name
			)

			paths.append(file_path)

			walked += 1

		for dir_name in access.get_directories():

			# Editor-internal and VCS directories are
			# never listed or searched.

			if dir_name.begins_with("."):
				continue

			stack.append(
				current_dir + dir_name + "/"
			)

	return {
		"ok": true,
		"paths": paths,
		"walked": walked,
		"truncated_walk": truncated_walk,
	}


func _normalize_extension_filter(
	extensions,
	action_name: String
) -> Dictionary:

	# Returns {"ok": true, "extensions": [...]} where each
	# entry is a lowercase extension without the dot, or a
	# structured failure.

	if extensions == null:
		return {"ok": true, "extensions": []}

	if not (extensions is Array):

		return {
			"success": false,
			"error": (
				action_name
				+ " extensions must be a list of "
				+ "strings."
			)
		}

	var normalized: Array = []

	for extension in extensions:

		if typeof(extension) != TYPE_STRING:

			return {
				"success": false,
				"error": (
					action_name
					+ " extensions must be a list "
					+ "of strings."
				)
			}

		var ext := str(extension).strip_edges().to_lower()

		ext = ext.lstrip(".")

		if ext.is_empty():
			continue

		normalized.append(ext)

	return {
		"ok": true,
		"extensions": normalized
	}


func _validate_result_limit(
	limit,
	default_limit: int,
	max_limit: int,
	action_name: String
) -> Dictionary:

	if limit == null:
		return {"ok": true, "limit": default_limit}

	# JSON request bodies decode integral numbers as floats in
	# GDScript, so accept both int and float and coerce.

	if (
		typeof(limit) != TYPE_INT
		and typeof(limit) != TYPE_FLOAT
	):

		return {
			"success": false,
			"error": (
				action_name
				+ " limit must be an integer between "
				+ "1 and "
				+ str(max_limit)
				+ "."
			)
		}

	var effective_limit := int(limit)

	if effective_limit < 1 or effective_limit > max_limit:

		return {
			"success": false,
			"error": (
				action_name
				+ " limit must be an integer between "
				+ "1 and "
				+ str(max_limit)
				+ "."
			)
		}

	return {
		"ok": true,
		"limit": effective_limit
	}


func list_project_files_from_request(
	data: Dictionary
) -> Dictionary:

	var prefix := ""

	if data.has("prefix"):

		if typeof(data["prefix"]) != TYPE_STRING:

			return {
				"success": false,
				"error": (
					"list_project_files prefix must "
					+ "be a string."
				)
			}

		prefix = (
			str(data["prefix"])
			.strip_edges()
			.lstrip("/")
			.trim_prefix("res://")
		)

		if prefix.ends_with("/"):
			prefix = prefix.rstrip("/")

	var extension_check := (
		_normalize_extension_filter(
			data.get("extensions"),
			"list_project_files"
		)
	)

	if not extension_check.get("ok", false):
		return extension_check

	var extensions: Array = (
		extension_check["extensions"]
	)

	var limit_check := (
		_validate_result_limit(
			data.get("limit"),
			PROJECT_FILE_DEFAULT_LIMIT,
			PROJECT_FILE_MAX_LIMIT,
			"list_project_files"
		)
	)

	if not limit_check.get("ok", false):
		return limit_check

	var limit: int = limit_check["limit"]

	var walk_result := (
		_walk_project_files(prefix)
	)

	if not walk_result.get("ok", false):
		return walk_result

	var all_paths: Array = walk_result["paths"]

	var matching: Array = []

	for file_path in all_paths:

		if not extensions.is_empty():

			var file_extension: String = str(
				file_path.get_extension()
			)

			if not extensions.has(file_extension):
				continue

		matching.append(file_path)

	matching.sort()

	var truncated: bool = (
		matching.size() > limit
	)

	return {
		"success": true,
		"action": "list_project_files",
		"prefix": prefix,
		"extensions": extensions,
		"total_matches": matching.size(),
		"truncated": truncated,
		"limit": limit,
		"walked_files": walk_result["walked"],
		"walk_truncated": walk_result["truncated_walk"],
		"files": matching.slice(0, limit),
	}


func search_in_files_from_request(
	data: Dictionary
) -> Dictionary:

	if not data.has("query"):

		return {
			"success": false,
			"error": (
				"search_in_files requires query."
			)
		}

	if typeof(data["query"]) != TYPE_STRING:

		return {
			"success": false,
			"error": (
				"search_in_files query must be a "
				+ "string."
			)
		}

	var query: String = str(data["query"]).strip_edges()

	if query.is_empty():

		return {
			"success": false,
			"error": (
				"search_in_files requires a non-empty "
				+ "query."
			)
		}

	var extension_check := (
		_normalize_extension_filter(
			data.get("extensions"),
			"search_in_files"
		)
	)

	if not extension_check.get("ok", false):
		return extension_check

	var extensions: Array = (
		extension_check["extensions"]
	)

	if extensions.is_empty():
		extensions = SEARCH_DEFAULT_EXTENSIONS.duplicate()

	var limit_check := (
		_validate_result_limit(
			data.get("limit"),
			10,
			50,
			"search_in_files"
		)
	)

	if not limit_check.get("ok", false):
		return limit_check

	var limit: int = limit_check["limit"]

	var walk_result := (
		_walk_project_files("")
	)

	if not walk_result.get("ok", false):
		return walk_result

	var all_paths: Array = walk_result["paths"]

	all_paths.sort()

	var needle := query.to_lower()

	var matches: Array = []

	var scanned := 0

	var reached_scan_cap := false

	for file_path in all_paths:

		if matches.size() >= limit:
			break

		if scanned >= SEARCH_MAX_SCANNED_FILES:

			reached_scan_cap = true

			break

		var file_extension: String = str(
			file_path.get_extension()
		)

		if not extensions.has(file_extension):
			continue

		scanned += 1

		if FileAccess.get_modified_time(file_path) < 0:
			continue

		var file := FileAccess.open(
			file_path,
			FileAccess.READ
		)

		if file == null:
			continue

		var content := file.get_as_text()

		file.close()

		if content.is_empty():
			continue

		if content.length() > (SEARCH_MAX_FILE_BYTES / 2):
			# Only the first bounded region of very large
			# text files is searched; this is reported via
			# scanned bounds rather than silently pretending
			# the whole file was read.
			content = content.substr(
				0,
				SEARCH_MAX_FILE_BYTES / 2
			)

		var lines := content.split("\n")

		for line_index in range(lines.size()):

			var line := lines[line_index]

			var hit := line.to_lower().find(needle)

			if hit == -1:
				continue

			var snippet := line.replace(
				"\t", "    "
			).strip_edges()

			if snippet.length() > 200:
				snippet = snippet.substr(0, 200)

			matches.append(
				{
					"file_path": file_path,
					"line_number": line_index + 1,
					"snippet": snippet,
				}
			)

			if matches.size() >= limit:
				break

	var total_matches := matches.size()

	return {
		"success": true,
		"action": "search_in_files",
		"query": query,
		"extensions": extensions,
		"total_matches": total_matches,
		"truncated": (
			reached_scan_cap
			or walk_result["truncated_walk"]
			or (
				total_matches == limit
				and scanned < all_paths.size()
			)
		),
		"limit": limit,
		"scanned_files": scanned,
		"scan_cap": SEARCH_MAX_SCANNED_FILES,
		"matches": matches,
	}


func get_global_class_list_from_request(
	_data: Dictionary
) -> Dictionary:

	# ScriptServer is not exposed to GDScript, so this
	# reads the editor's own global class cache - the same
	# data the editor maintains for class_name globals.
	# The cache lives in .godot/ and is regenerated by the
	# editor on project scans.

	var cache_path := (
		"res://.godot/global_script_class_cache.cfg"
	)

	if not FileAccess.file_exists(cache_path):

		return {
			"success": false,
			"action": "get_global_class_list",
			"error": (
				"No global class cache found. The "
				+ "project may have no class_name "
				+ "globals, or the editor has not "
				+ "scanned the project yet."
			)
		}

	var config := ConfigFile.new()

	var load_error := config.load(cache_path)

	if load_error != OK:

		return {
			"success": false,
			"action": "get_global_class_list",
			"error": (
				"Could not read the global class "
				+ "cache. Error: "
				+ error_string(load_error)
			)
		}

	var entries: Variant = config.get_value(
		"",
		"list",
		[]
	)

	if not (entries is Array):

		return {
			"success": false,
			"action": "get_global_class_list",
			"error": (
				"Global class cache has an "
				+ "unexpected format."
			)
		}

	var classes: Array = []

	for entry in entries:

		if not (entry is Dictionary):
			continue

		classes.append(
			{
				"class_name": str(
					entry.get("class", "")
				),
				"script_path": str(
					entry.get("path", "")
				),
				"base_class": str(
					entry.get("base", "")
				),
			}
		)

	classes.sort_custom(
		func(a, b):
			return a["class_name"] < b["class_name"]
	)

	return {
		"success": true,
		"action": "get_global_class_list",
		"class_count": classes.size(),
		"classes": classes,
	}


func get_input_map_from_request(
	_data: Dictionary
) -> Dictionary:

	# InputMap reflects the project's input settings in
	# any process, including headless ones.

	var actions: Array = []

	for action_name in InputMap.get_actions():

		var events: Array = []

		for event in InputMap.action_get_events(
			action_name
		):

			if event is InputEvent:
				events.append(event.as_text())

		actions.append(
			{
				"action": str(action_name),
				"deadzone": InputMap.action_get_deadzone(
					action_name
				),
				"events": events,
			}
		)

	actions.sort_custom(
		func(a, b):
			return a["action"] < b["action"]
	)

	return {
		"success": true,
		"action": "get_input_map",
		"action_count": actions.size(),
		"actions": actions,
	}


# ==========================================
# scan_project_issues
# ==========================================
# Read-only project lint: bounded scan for
# mechanical problems a mutation-heavy agent can
# cause. Works headless and in the editor (plain
# file/ResourceLoader access, no editor state).
# Three checks per file:
#
# - script_parse_error: .gd fails a fresh parse
# - scene_load_failed: .tscn does not load
# - missing_dependency: a scene's dependency path
#   does not exist on disk
#
# Bounds mirror the bounded-listing convention:
# scan cap, walk cap, reported-issue limit, and
# explicit total_matches/truncated so a short
# issue list is never mistaken for a full clean
# scan.


const SCAN_MAX_FILES := 500

const SCAN_DEFAULT_LIMIT := 50

const SCAN_MAX_LIMIT := 100


func _scan_parse_check(
	source: String
) -> Dictionary:

	var gd := GDScript.new()

	gd.source_code = source

	var err := gd.reload()

	if err != OK:

		return {
			"ok": false,
			"error": error_string(err)
		}

	return {"ok": true, "error": ""}


func scan_project_issues_from_request(
	data: Dictionary
) -> Dictionary:

	var prefix := ""

	if data.has("prefix"):

		if typeof(data["prefix"]) != TYPE_STRING:

			return {
				"success": false,
				"error": (
					"scan_project_issues prefix "
					+ "must be a string."
				)
			}

		prefix = (
			str(data["prefix"])
			.strip_edges()
			.lstrip("/")
			.trim_prefix("res://")
		)

		if prefix.ends_with("/"):
			prefix = prefix.rstrip("/")

	var limit_check := (
		_validate_result_limit(
			data.get("limit"),
			SCAN_DEFAULT_LIMIT,
			SCAN_MAX_LIMIT,
			"scan_project_issues"
		)
	)

	if not limit_check.get("ok", false):
		return limit_check

	var limit: int = limit_check["limit"]

	var walk_result := (
		_walk_project_files(prefix)
	)

	if not walk_result.get("ok", false):
		return walk_result

	var issues: Array = []

	var scanned_files := 0

	var reached_scan_cap := false

	for file_path in walk_result["paths"]:

		if scanned_files >= SCAN_MAX_FILES:

			reached_scan_cap = true

			break

		var file_ext: String = str(
			file_path.get_extension()
		)

		if file_ext == "gd":

			scanned_files += 1

			var file := FileAccess.open(
				file_path,
				FileAccess.READ
			)

			if file == null:
				continue

			var source := file.get_as_text()

			file.close()

			var parse_result := (
				_scan_parse_check(source)
			)

			if not parse_result["ok"]:

				# Double evidence before reporting: a
				# fresh detached parse of a script
				# whose class_name is already
				# registered in the running editor
				# fails spuriously (duplicate global
				# class). The file is only reported
				# when the editor's own authority
				# also rejects it: load() returns
				# null, or an uncompiled script that
				# cannot instantiate.

				var disk_load: Variant = load(
					file_path
				)

				var editor_rejects: bool = (
					disk_load == null
					or (
						disk_load is GDScript
						and not disk_load.can_instantiate()
					)
				)

				if not editor_rejects:
					continue

				issues.append(
					{
						"issue_kind": (
							"script_parse_error"
						),
						"file_path": file_path,
						"detail": parse_result["error"],
					}
				)

		elif file_ext == "tscn":

			scanned_files += 1

			var packed: Variant = load(file_path)

			if packed == null:

				issues.append(
					{
						"issue_kind": (
							"scene_load_failed"
						),
						"file_path": file_path,
						"detail": (
							"the scene file does not "
							+ "load as a PackedScene"
						),
					}
				)

			else:

				var dependencies: PackedStringArray = (
					ResourceLoader.get_dependencies(
						file_path
					)
				)

				for dependency in dependencies:

					# get_dependencies() may return
					# uid-form strings like
					# "uid://abc::::res://x.gd" when the
					# referenced resource has a uid.
					# FileAccess cannot resolve those,
					# so the res:// path is extracted
					# before the existence check. A
					# dependency with no res:// part
					# (uid-only) cannot be verified on
					# disk and is skipped rather than
					# falsely reported.

					var dep := str(dependency)

					var res_marker := dep.find(
						"res://"
					)

					if res_marker > 0:
						dep = dep.substr(
							res_marker
						)
					elif res_marker == -1:
						continue

					if FileAccess.file_exists(dep):
						continue

					issues.append(
						{
							"issue_kind": (
								"missing_dependency"
							),
							"file_path": file_path,
							"detail": dep,
						}
					)

	var total_matches := issues.size()

	var truncated: bool = (
		reached_scan_cap
		or walk_result["truncated_walk"]
		or total_matches > limit
	)

	return {
		"success": true,
		"action": "scan_project_issues",
		"prefix": prefix,
		"issues": issues.slice(0, limit),
		"total_matches": total_matches,
		"truncated": truncated,
		"limit": limit,
		"scanned_files": scanned_files,
		"scan_cap": SCAN_MAX_FILES,
		"walked_files": walk_result["walked"],
		"walk_truncated": walk_result["truncated_walk"],
	}
