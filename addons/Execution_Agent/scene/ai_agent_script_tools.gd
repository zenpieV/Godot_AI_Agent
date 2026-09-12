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


func _gated_write_script(
	script_path: String,
	content: String
) -> Dictionary:
	# Shared parse-gated write used by create_script,
	# edit_script, and replace_in_script: the content is
	# parse-checked BEFORE anything is written, so an
	# unparseable result never reaches the disk. The write
	# is verified by reading the file back.
	#
	# Returns {"ok": true, "verified_write": bool,
	# "line_count": int} or {"ok": false, "error": ...}.

	# Parse gate: unparseable content is never written,
	# so the agent cannot leave a broken script file
	# behind.

	var parse_result := _parse_check(content)

	if not parse_result["ok"]:

		return {
			"ok": false,
			"error": (
				"content does not parse ("
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
				"ok": false,
				"error": (
					"could not create directory "
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
			"ok": false,
			"error": (
				"could not open "
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
			"script write"
		)
	)

	var verified_write: bool = (
		verify_result.get("ok", false)
		and verify_result["source"] == content
	)

	return {
		"ok": true,
		"verified_write": verified_write,
		"line_count": _count_lines(content)
	}


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

	var write_result := (
		_gated_write_script(
			script_path,
			content
		)
	)

	if not write_result["ok"]:

		return {
			"success": false,
			"error": (
				"create_script: "
				+ write_result["error"]
			)
		}

	# Soft convention nudge: a file in the project root
	# is legal (bridge scripts live there) but usually a
	# mistake; the flag lets the model course-correct.

	var root_hint: bool = (
		script_path.get_base_dir() == "res://"
	)

	return {
		"success": true,
		"action": "create_script",
		"message": (
			"Script created successfully in the "
			+ "project. Note: file placed in the "
			+ "project root; prefer the project's "
			+ "folder conventions (scripts/, ...)."
			if root_hint
			else "Script created successfully in the "
			+ "project."
		),
		"script_path": script_path,
		"line_count": write_result["line_count"],
		"parse_ok": true,
		"root_directory_hint": root_hint,
		"changed": true,
		"verified_write": write_result["verified_write"],
		"undoable": false
	}


# ==========================================
# edit_script
# ==========================================
# Whole-file replacement of an existing script. The
# parse gate means a rejected edit leaves the previous,
# working content on disk; a successful edit is verified
# by reading the file back. Not undoable: the file
# system has no editor undo history.


func edit_script_from_request(
	data: Dictionary
) -> Dictionary:

	var path_check := (
		_normalize_script_path(
			data.get("script_path"),
			"edit_script"
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
				"edit_script requires content."
			)
		}

	if not data_has_string(data["content"]):

		return {
			"success": false,
			"error": (
				"edit_script content must be "
				+ "a string."
			)
		}

	var content: String = data["content"]

	if content.strip_edges().is_empty():

		return {
			"success": false,
			"error": (
				"edit_script requires non-empty "
				+ "content."
			)
		}

	# edit_script replaces; it never creates.

	if not FileAccess.file_exists(script_path):

		return {
			"success": false,
			"error": (
				"edit_script: script not found: "
				+ script_path
				+ ". Use create_script for new "
				+ "files."
			)
		}

	var read_result := (
		_read_script_file(
			script_path,
			"edit_script"
		)
	)

	if not read_result.get("ok", false):
		return read_result

	# Deterministic idempotent case: byte-identical
	# replacement.

	if read_result["source"] == content:

		return {
			"success": true,
			"action": "edit_script",
			"message": (
				"Content is already identical; no "
				+ "change was made."
			),
			"script_path": script_path,
			"line_count": _count_lines(content),
			"parse_ok": true,
			"changed": false,
			"verified_write": true,
			"undoable": false
		}

	var write_result := (
		_gated_write_script(
			script_path,
			content
		)
	)

	if not write_result["ok"]:

		return {
			"success": false,
			"error": (
				"edit_script: "
				+ write_result["error"]
			)
		}

	return {
		"success": true,
		"action": "edit_script",
		"message": (
			"Script content replaced successfully."
		),
		"script_path": script_path,
		"line_count": write_result["line_count"],
		"parse_ok": true,
		"changed": true,
		"verified_write": write_result["verified_write"],
		"undoable": false
	}


# ==========================================
# replace_in_script
# ==========================================
# Deterministic anchored edit: the old_string must occur
# exactly once in the current content. Zero occurrences
# with the new_string already present means the edit was
# already applied (idempotent no-op); zero occurrences
# otherwise is a structured failure. Ambiguous (multiple)
# matches are refused, never fuzzy-resolved.


func replace_in_script_from_request(
	data: Dictionary
) -> Dictionary:

	var path_check := (
		_normalize_script_path(
			data.get("script_path"),
			"replace_in_script"
		)
	)

	if not path_check.get("ok", false):
		return path_check

	var script_path: String = (
		path_check["script_path"]
	)

	if not data.has("old_string"):

		return {
			"success": false,
			"error": (
				"replace_in_script requires "
				+ "old_string."
			)
		}

	var old_string_is_invalid: bool = (
		not data_has_string(data["old_string"])
		or str(data["old_string"]).is_empty()
	)

	if old_string_is_invalid:

		return {
			"success": false,
			"error": (
				"replace_in_script requires a "
				+ "non-empty old_string."
			)
		}

	if not data.has("new_string"):

		return {
			"success": false,
			"error": (
				"replace_in_script requires "
				+ "new_string."
			)
		}

	if not data_has_string(data["new_string"]):

		return {
			"success": false,
			"error": (
				"replace_in_script new_string must "
				+ "be a string."
			)
		}

	if not FileAccess.file_exists(script_path):

		return {
			"success": false,
			"error": (
				"replace_in_script: script not "
				+ "found: "
				+ script_path
			)
		}

	var read_result := (
		_read_script_file(
			script_path,
			"replace_in_script"
		)
	)

	if not read_result.get("ok", false):
		return read_result

	var current: String = read_result["source"]

	var old_string: String = data["old_string"]

	var new_string: String = data["new_string"]

	var occurrence_count: int = current.count(
		old_string
	)

	# Deterministic idempotent case: the anchor is gone
	# and the replacement is already in place.

	if occurrence_count == 0:

		var already_applied: bool = (
			not new_string.is_empty()
			and current.contains(new_string)
		)

		if already_applied:

			return {
				"success": true,
				"action": "replace_in_script",
				"message": (
					"Replacement already applied; "
					+ "no change was made."
				),
				"script_path": script_path,
				"changed": false,
				"verified_write": true,
				"undoable": false
			}

		return {
			"success": false,
			"error": (
				"replace_in_script: old_string not "
				+ "found in "
				+ script_path
				+ ". Use get_script_content to "
				+ "read the current source."
			)
		}

	# Ambiguous anchors are refused, never fuzzy-resolved.

	if occurrence_count > 1:

		return {
			"success": false,
			"error": (
				"replace_in_script: old_string "
				+ "occurs "
				+ str(occurrence_count)
				+ " times in "
				+ script_path
				+ ". The anchor must be unique; "
				+ "use a longer anchor."
			)
		}

	var new_content: String = current.replace(
		old_string,
		new_string
	)

	if new_content == current:

		return {
			"success": true,
			"action": "replace_in_script",
			"message": (
				"Replacement is identical to the "
				+ "current content; no change was "
				+ "made."
			),
			"script_path": script_path,
			"changed": false,
			"verified_write": true,
			"undoable": false
		}

	var write_result := (
		_gated_write_script(
			script_path,
			new_content
		)
	)

	if not write_result["ok"]:

		return {
			"success": false,
			"error": (
				"replace_in_script: "
				+ write_result["error"]
			)
		}

	return {
		"success": true,
		"action": "replace_in_script",
		"message": (
			"Script edited successfully."
		),
		"script_path": script_path,
		"line_count": write_result["line_count"],
		"parse_ok": true,
		"changed": true,
		"verified_write": write_result["verified_write"],
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

	# Optional line paging for large scripts: with
	# start_line/line_count the read is bounded and
	# the result reports total_lines and truncated
	# so a bounded read is never mistaken for the
	# whole file. Without them the full source is
	# returned (the historical behavior).

	var start_line := 0

	var line_count := 0

	if (
		data.has("start_line")
		and data["start_line"] != null
	):

		if (
			typeof(data["start_line"]) != TYPE_INT
			and typeof(data["start_line"]) != TYPE_FLOAT
		):

			return {
				"success": false,
				"error": (
					"get_script_content start_line "
					+ "must be an integer >= 1."
				)
			}

		start_line = int(data["start_line"])

		if start_line < 1:

			return {
				"success": false,
				"error": (
					"get_script_content start_line "
					+ "must be an integer >= 1."
				)
			}

	if (
		data.has("line_count")
		and data["line_count"] != null
	):

		if (
			typeof(data["line_count"]) != TYPE_INT
			and typeof(data["line_count"]) != TYPE_FLOAT
		):

			return {
				"success": false,
				"error": (
					"get_script_content line_count "
					+ "must be an integer between "
					+ "1 and 500."
				)
			}

		line_count = int(data["line_count"])

		if line_count < 1 or line_count > 500:

			return {
				"success": false,
				"error": (
					"get_script_content line_count "
					+ "must be an integer between "
					+ "1 and 500."
				)
			}

	if start_line > 0 and line_count == 0:

		return {
			"success": false,
			"error": (
				"get_script_content start_line "
				+ "requires line_count."
			)
		}

	var read_result := (
		_read_script_file(
			script_path,
			"get_script_content"
		)
	)

	if not read_result.get("ok", false):
		return read_result

	var source: String = read_result["source"]

	var total_lines := _count_lines(source)

	if start_line > 0:

		var lines := source.split("\n")

		var slice_start: int = start_line - 1

		var slice_end: int = min(
			slice_start + line_count,
			lines.size()
		)

		var paged_source := ""

		if slice_start < lines.size():

			paged_source = "\n".join(
				lines.slice(slice_start, slice_end)
			)

		var end_line: int = (
			slice_start + paged_source.count("\n") + 1
			if slice_start < lines.size()
			else slice_start
		)

		return {
			"success": true,
			"action": "get_script_content",
			"script_path": script_path,
			"source": paged_source,
			"total_lines": total_lines,
			"start_line": start_line,
			"end_line": end_line,
			"truncated": end_line < total_lines,
			"line_count": total_lines,
			"size_bytes": source.to_utf8_buffer().size(),
		}

	return {
		"success": true,
		"action": "get_script_content",
		"script_path": script_path,
		"source": source,
		"total_lines": total_lines,
		"line_count": total_lines,
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
