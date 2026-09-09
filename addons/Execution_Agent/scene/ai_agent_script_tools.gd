@tool
extends RefCounted

class_name AIAgentScriptTools


var scene_helpers: AIAgentSceneHelpers
var undo_redo: EditorUndoRedoManager


func _init(
	p_scene_helpers: AIAgentSceneHelpers,
	p_undo_redo: EditorUndoRedoManager
) -> void:

	scene_helpers = p_scene_helpers

	undo_redo = p_undo_redo


# ==========================================
# Script tools
# ==========================================
# Script creation, attachment, and inspection for the
# currently edited scene and project.
#
# Contract notes that differ deliberately from the
# scene-mutation tools:
#
# - create_script writes a PROJECT file. File creation
#   is not undoable through the editor's undo system,
#   so it reports undoable: false and verifies the
#   write by reading the file back (verified_write).
#   Content is parse-checked BEFORE writing: a script
#   that does not parse is never written to disk, so
#   the agent cannot create an unfixable broken file.
# - Existing files are never overwritten; script
#   modification is deliberately out of scope for this
#   tool set.
# - attach/detach mutate the node's script attachment
#   as editor-native, undoable EditorUndoRedoManager
#   property actions with read-back verification.
# - Path handling is strict: res:// scheme (auto-
#   prefixed), .gd extension required, no directory
#   traversal, no backslashes.


func _normalize_script_path(
	raw_path,
	action_name: String
) -> Dictionary:

	if not data_has_string(raw_path):

		return {
			"success": false,
			"error": (
				action_name
				+ " requires script_path."
			)
		}

	var script_path: String = (
		str(raw_path).strip_edges()
	)

	if script_path.is_empty():

		return {
			"success": false,
			"error": (
				action_name
				+ " requires a non-empty "
				+ "script_path."
			)
		}

	if not script_path.begins_with("res://"):

		script_path = (
			"res://"
			+ script_path
		)

	if script_path.length() <= len("res://"):

		return {
			"success": false,
			"error": (
				action_name
				+ " requires a script file name."
			)
		}

	if script_path.contains("\\"):

		return {
			"success": false,
			"error": (
				action_name
				+ " script_path must use "
				+ "forward slashes."
			)
		}

	if script_path.contains(".."):

		return {
			"success": false,
			"error": (
				action_name
				+ " script_path must not "
				+ "contain directory traversal."
			)
		}

	if not script_path.ends_with(".gd"):

		return {
			"success": false,
			"error": (
				action_name
				+ " requires a script_path "
				+ "ending in .gd."
			)
		}

	if script_path.get_file() == ".gd":

		return {
			"success": false,
			"error": (
				action_name
				+ " requires a non-empty "
				+ "script file name."
			)
		}

	return {
		"ok": true,
		"script_path": script_path
	}


func data_has_string(value) -> bool:

	return typeof(value) == TYPE_STRING


func _parse_check(
	source: String
) -> Dictionary:

	# Fresh parse of the given source via a detached
	# GDScript instance. Returns {"ok": true} or
	# {"ok": false, "error": ...}. The Godot error code
	# is the only programmatic parse signal available;
	# line-level diagnostics are not exposed here and
	# are never fabricated.

	var gd := GDScript.new()

	gd.source_code = source

	var err := gd.reload()

	if err != OK:

		return {
			"ok": false,
			"error": error_string(err)
		}

	return {
		"ok": true,
		"error": ""
	}


func _read_script_file(
	script_path: String,
	action_name: String
) -> Dictionary:

	if not FileAccess.file_exists(script_path):

		return {
			"success": false,
			"error": (
				action_name + ": script not found: "
				+ script_path
			)
		}

	var file := FileAccess.open(
		script_path,
		FileAccess.READ
	)

	if file == null:

		return {
			"success": false,
			"error": (
				action_name + ": could not open "
				+ script_path + " for reading. "
				+ "Error: "
				+ error_string(
					FileAccess.get_open_error()
				)
			)
		}

	var source: String = file.get_as_text()

	file.close()

	return {
		"ok": true,
		"source": source
	}


func _count_lines(source: String) -> int:

	if source.is_empty():
		return 0

	return source.count("\n") + 1


# ==========================================
# create_script
# ==========================================


func create_script_from_request(
	data: Dictionary
) -> Dictionary:

	var path_check := (
		_normalize_script_path(
			data.get("script_path"),
			"create_script"
		)
	)

	if not path_check.get("ok", false):
		return path_check

	var script_path: String = (
		path_check["script_path"]
	)

	if not data.has("content"):

		return {
			"success": false,
			"error": (
				"create_script requires content."
			)
		}

	if not data_has_string(data["content"]):

		return {
			"success": false,
			"error": (
				"create_script content must be "
				+ "a string."
			)
		}

	var content: String = data["content"]

	if content.strip_edges().is_empty():

		return {
			"success": false,
			"error": (
				"create_script requires non-empty "
				+ "content."
			)
		}

	# Deterministic create-only contract: never
	# overwrite. Script modification is a separate,
	# future tool.

	if FileAccess.file_exists(script_path):

		return {
			"success": false,
			"error": (
				"create_script: script already "
				+ "exists: "
				+ script_path
				+ ". Existing scripts are never "
				+ "overwritten."
			)
		}

	# Parse gate: unparseable content is never written,
	# so the agent cannot create an unfixable broken
	# script file.

	var parse_result := _parse_check(content)

	if not parse_result["ok"]:

		return {
			"success": false,
			"error": (
				"create_script: content does not "
				+ "parse ("
				+ parse_result["error"]
				+ "). Nothing was written to disk."
			)
		}

	# Create missing parent directories so a script can be
	# placed into a not-yet-existing project folder (mirrors
	# what the editor's script-creation workflow produces).

	var target_dir: String = script_path.get_base_dir()

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
					"create_script: could not create "
					+ "directory "
					+ target_dir
					+ ". Error: "
					+ error_string(mkdir_error)
				)
			}

	var file := FileAccess.open(
		script_path,
		FileAccess.WRITE
	)

	if file == null:

		return {
			"success": false,
			"error": (
				"create_script: could not open "
				+ script_path + " for writing. "
				+ "Error: "
				+ error_string(
					FileAccess.get_open_error()
				)
			)
		}

	file.store_string(content)

	file.close()

	# Post-write verification: read the file back and
	# compare against the requested content.

	var verify_result := (
		_read_script_file(
			script_path,
			"create_script"
		)
	)

	var verified_write: bool = (
		verify_result.get("ok", false)
		and verify_result["source"] == content
	)

	return {
		"success": true,
		"action": "create_script",
		"message": (
			"Script created successfully in the "
			+ "project."
		),
		"script_path": script_path,
		"line_count": _count_lines(content),
		"parse_ok": true,
		"changed": true,
		"verified_write": verified_write,
		"undoable": false
	}


# ==========================================
# attach_script
# ==========================================


func attach_script_from_request(
	data: Dictionary
) -> Dictionary:

	if not data.has("node_path"):

		return {
			"success": false,
			"error": (
				"attach_script requires node_path."
			)
		}

	var path_check := (
		_normalize_script_path(
			data.get("script_path"),
			"attach_script"
		)
	)

	if not path_check.get("ok", false):
		return path_check

	var script_path: String = (
		path_check["script_path"]
	)

	var node_path: String = (
		str(data["node_path"]).strip_edges()
	)

	var node_result: Dictionary = (
		scene_helpers
		.resolve_node_or_error(
			node_path
		)
	)

	if not node_result["success"]:
		return node_result

	var target_node: Node = (
		node_result["node"]
	)

	var target_name: String = (
		str(target_node.name)
	)

	if not FileAccess.file_exists(script_path):

		return {
			"success": false,
			"error": (
				"attach_script: script not found: "
				+ script_path
			)
		}

	var script_resource: Variant = load(
		script_path
	)

	if script_resource == null:

		return {
			"success": false,
			"error": (
				"attach_script: script could not "
				+ "be loaded: "
				+ script_path
			)
		}

	if not (script_resource is GDScript):

		return {
			"success": false,
			"error": (
				"attach_script: resource is not a "
				+ "GDScript: "
				+ script_path
			)
		}

	var existing: Variant = (
		target_node.get_script()
	)

	# Deterministic idempotent case: the exact same
	# script is already attached.

	var same_script: bool = false

	if existing is GDScript:

		var existing_variant: GDScript = existing

		if existing_variant.resource_path == script_path:
			same_script = true

	if same_script:

		return {
			"success": true,
			"action": "attach_script",
			"message": (
				"Script is already attached; no "
				+ "change was made."
			),
			"node_path": node_path,
			"node_name": target_name,
			"script_path": script_path,
			"was_attached": true,
			"is_attached": true,
			"changed": false,
			"verified_attachment": true,
			"undoable": false
		}

	# Deterministic refusal: a different script is
	# already attached. Never implicitly destructive;
	# the caller detaches first.

	if existing != null:

		var existing_path: String = ""

		if existing is GDScript:

			existing_path = (
				existing.resource_path
			)

		return {
			"success": false,
			"error": (
				"attach_script: node "
				+ target_name
				+ " already has a different script "
				+ "attached ("
				+ existing_path
				+ "). Use detach_script first."
			)
		}

	if undo_redo == null:

		return {
			"success": false,
			"action": "attach_script",
			"error": (
				"attach_script requires the plugin-owned "
				+ "EditorUndoRedoManager, which is only "
				+ "available inside the running Godot "
				+ "editor."
			)
		}

	var script_name: String = (
		script_path.get_file()
	)

	undo_redo.create_action(
		"AI Agent: Attach "
		+ script_name
		+ " to "
		+ target_name
	)

	undo_redo.add_do_property(
		target_node,
		"script",
		script_resource
	)

	undo_redo.add_undo_property(
		target_node,
		"script",
		existing
	)

	undo_redo.commit_action()

	# Post-mutation verification: read the real
	# attachment back from the node.

	var attached: Variant = (
		target_node.get_script()
	)

	var is_attached: bool = (
		attached is GDScript
		and attached.resource_path == script_path
	)

	return {
		"success": true,
		"action": "attach_script",
		"message": (
			"Script attached successfully in the "
			+ "Godot editor."
		),
		"node_path": node_path,
		"node_name": target_name,
		"script_path": script_path,
		"was_attached": false,
		"is_attached": is_attached,
		"changed": true,
		"verified_attachment": is_attached,
		"undoable": true
	}


# ==========================================
# detach_script
# ==========================================


func detach_script_from_request(
	data: Dictionary
) -> Dictionary:

	if not data.has("node_path"):

		return {
			"success": false,
			"error": (
				"detach_script requires node_path."
			)
		}

	var node_path: String = (
		str(data["node_path"]).strip_edges()
	)

	var node_result: Dictionary = (
		scene_helpers
		.resolve_node_or_error(
			node_path
		)
	)

	if not node_result["success"]:
		return node_result

	var target_node: Node = (
		node_result["node"]
	)

	var target_name: String = (
		str(target_node.name)
	)

	var existing: Variant = (
		target_node.get_script()
	)

	# Deterministic idempotent case: no script
	# attached. No scene change, no undo history,
	# state still verified against the node.

	if existing == null:

		return {
			"success": true,
			"action": "detach_script",
			"message": (
				"Node has no attached script; no "
				+ "change was made."
			),
			"node_path": node_path,
			"node_name": target_name,
			"was_attached": false,
			"is_attached": false,
			"changed": false,
			"verified_attachment": true,
			"undoable": false
		}

	var previous_path: String = ""

	if existing is GDScript:

		previous_path = (
			existing.resource_path
		)

	if undo_redo == null:

		return {
			"success": false,
			"action": "detach_script",
			"error": (
				"detach_script requires the plugin-owned "
				+ "EditorUndoRedoManager, which is only "
				+ "available inside the running Godot "
				+ "editor."
			)
		}

	undo_redo.create_action(
		"AI Agent: Detach "
		+ previous_path.get_file()
		+ " from "
		+ target_name
	)

	undo_redo.add_do_property(
		target_node,
		"script",
		null
	)

	undo_redo.add_undo_property(
		target_node,
		"script",
		existing
	)

	undo_redo.commit_action()

	var is_attached: bool = (
		target_node.get_script() != null
	)

	return {
		"success": true,
		"action": "detach_script",
		"message": (
			"Script detached successfully in the "
			+ "Godot editor."
		),
		"node_path": node_path,
		"node_name": target_name,
		"detached_script": previous_path,
		"was_attached": true,
		"is_attached": is_attached,
		"changed": true,
		"verified_attachment": is_attached == false,
		"undoable": true
	}


# ==========================================
# get_script_content
# ==========================================


func get_script_content_from_request(
	data: Dictionary
) -> Dictionary:

	var path_check := (
		_normalize_script_path(
			data.get("script_path"),
			"get_script_content"
		)
	)

	if not path_check.get("ok", false):
		return path_check

	var script_path: String = (
		path_check["script_path"]
	)

	var read_result := (
		_read_script_file(
			script_path,
			"get_script_content"
		)
	)

	if not read_result.get("ok", false):
		return read_result

	var source: String = read_result["source"]

	return {
		"success": true,
		"action": "get_script_content",
		"script_path": script_path,
		"source": source,
		"line_count": _count_lines(source),
		"size_bytes": source.to_utf8_buffer().size(),
	}


# ==========================================
# list_script_diagnostics
# ==========================================


func list_script_diagnostics_from_request(
	data: Dictionary
) -> Dictionary:

	var path_check := (
		_normalize_script_path(
			data.get("script_path"),
			"list_script_diagnostics"
		)
	)

	if not path_check.get("ok", false):
		return path_check

	var script_path: String = (
		path_check["script_path"]
	)

	var read_result := (
		_read_script_file(
			script_path,
			"list_script_diagnostics"
		)
	)

	if not read_result.get("ok", false):
		return read_result

	var source: String = read_result["source"]

	# Fresh parse of the current file content. The
	# Godot error code is the only programmatic parse
	# signal available; line-level diagnostics are not
	# exposed and are never fabricated.

	var parse_result := _parse_check(source)

	return {
		"success": true,
		"action": "list_script_diagnostics",
		"script_path": script_path,
		"parse_ok": parse_result["ok"],
		"error": parse_result["error"],
		"line_count": _count_lines(source),
		"size_bytes": source.to_utf8_buffer().size(),
	}
