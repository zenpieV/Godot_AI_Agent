@tool
extends RefCounted

class_name AIAgentRefactorTools


# ==========================================
# Refactor tools
# ==========================================
# Deterministic, parse-gated, multi-file project
# refactoring operations:
#
# - rename_script moves a .gd file to a new res://
#   path and updates every textual reference to the
#   old path across project text files in the same
#   operation, so a rename never leaves dangling
#   references behind.
# - find_replace_across_files applies one exact
#   string replacement to multiple project files at
#   once, bounded by a maximum file count.
#
# Contract notes shared with the script tools:
#
# - Both are FILE operations, not editor-native
#   EditorUndoRedoManager actions; they report
#   undoable: false and verify by reading files back.
# - Both are TWO-PHASE and parse-gated: all new
#   content is computed and parse-checked BEFORE any
#   write, so a failed parse (or a refused request)
#   leaves every file untouched.
# - Path handling is strict: res:// scheme (auto-
#   prefixed), .gd extension required for scripts,
#   no directory traversal, no backslashes.
# - Caveat reported in results: files currently open
#   in the editor (open scenes, the edited scene's
#   scripts) are modified on disk; the editor's
#   in-memory copies are not reloaded by this tool.


const REFACTOR_MAX_WALK := 5000

const REFACTOR_MAX_FILE_BYTES := 1048576

const REFERENCE_FILE_EXTENSIONS := [
	"gd",
	"tscn",
	"tres",
	"cfg",
]

const REPLACE_DEFAULT_EXTENSIONS := [
	"gd",
	"tscn",
	"tres",
]

const REPLACE_DEFAULT_MAX_FILES := 20

const REPLACE_MAX_MAX_FILES := 50


var scene_helpers: AIAgentSceneHelpers
var editor_interface: EditorInterface


func _init(
	p_scene_helpers: AIAgentSceneHelpers,
	p_editor_interface: EditorInterface
) -> void:

	scene_helpers = p_scene_helpers

	editor_interface = p_editor_interface


# ==========================================
# Shared helpers
# ==========================================


func data_has_string(value) -> bool:

	return typeof(value) == TYPE_STRING


func _normalize_script_path(
	raw_path,
	action_name: String
) -> Dictionary:

	if not data_has_string(raw_path):

		return {
			"success": false,
			"error": (
				action_name
				+ " requires a path."
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
				+ "path."
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
				+ " requires a file name."
			)
		}

	if script_path.contains("\\"):

		return {
			"success": false,
			"error": (
				action_name
				+ " paths must use "
				+ "forward slashes."
			)
		}

	if script_path.contains(".."):

		return {
			"success": false,
			"error": (
				action_name
				+ " paths must not "
				+ "contain directory "
				+ "traversal."
			)
		}

	if not script_path.ends_with(".gd"):

		return {
			"success": false,
			"error": (
				action_name
				+ " requires a path "
				+ "ending in .gd."
			)
		}

	if script_path.get_file() == ".gd":

		return {
			"success": false,
			"error": (
				action_name
				+ " requires a non-empty "
				+ "file name."
			)
		}

	return {
		"ok": true,
		"script_path": script_path
	}


func _parse_check(
	source: String
) -> Dictionary:

	# Fresh parse of the given source via a detached
	# GDScript instance. Returns {"ok": true} or
	# {"ok": false, "error": ...}. Never fabricates
	# line-level diagnostics.

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


func _read_text_file(
	file_path: String
) -> Dictionary:

	if not FileAccess.file_exists(file_path):

		return {
			"ok": false,
			"error": (
				"file not found: "
				+ file_path
			)
		}

	var file := FileAccess.open(
		file_path,
		FileAccess.READ
	)

	if file == null:

		return {
			"ok": false,
			"error": (
				"could not open "
				+ file_path
				+ " for reading. Error: "
				+ error_string(
					FileAccess.get_open_error()
				)
			)
		}

	var content: String = file.get_as_text()

	file.close()

	return {
		"ok": true,
		"source": content
	}


func _write_text_file(
	file_path: String,
	content: String
) -> Dictionary:

	var file := FileAccess.open(
		file_path,
		FileAccess.WRITE
	)

	if file == null:

		return {
			"ok": false,
			"error": (
				"could not open "
				+ file_path
				+ " for writing. Error: "
				+ error_string(
					FileAccess.get_open_error()
				)
			)
		}

	file.store_string(content)

	file.close()

	var verify_result := (
		_read_text_file(file_path)
	)

	var verified: bool = (
		verify_result.get("ok", false)
		and verify_result["source"] == content
	)

	return {
		"ok": true,
		"verified": verified
	}


func _ensure_parent_dir(
	file_path: String
) -> Dictionary:

	var target_dir: String = (
		file_path.get_base_dir()
	)

	var needs_dir: bool = (
		target_dir.length() > len("res://")
		and not DirAccess.dir_exists_absolute(
			target_dir
		)
	)

	if not needs_dir:
		return {"ok": true}

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

	return {"ok": true}


func _walk_project_files(
	prefix_normalized: String
) -> Dictionary:

	# Depth-first traversal of res:// below the
	# prefix, skipping editor-internal directories.
	# Returns {"ok": true, "paths": [...],
	# "truncated_walk": bool} or a structured failure.

	var base_dir := "res://"

	if not prefix_normalized.is_empty():

		base_dir = (
			"res://"
			+ prefix_normalized
		)

	var dir := DirAccess.open(base_dir)

	if dir == null:

		return {
			"ok": false,
			"error": (
				"Could not open project "
				+ "directory: "
				+ base_dir
				+ ". Error: "
				+ error_string(
					DirAccess.get_open_error()
				)
			)
		}

	var paths: Array = []

	var truncated_walk := false

	var stack: Array = [base_dir]

	var walked := 0

	while not stack.is_empty():

		if walked >= REFACTOR_MAX_WALK:

			truncated_walk = true

			break

		var current_dir: String = (
			stack.pop_back()
		)

		if not current_dir.ends_with("/"):
			current_dir = current_dir + "/"

		var access := DirAccess.open(current_dir)

		if access == null:
			continue

		for file_name in access.get_files():

			if walked >= REFACTOR_MAX_WALK:

				truncated_walk = true

				break

			paths.append(
				current_dir + file_name
			)

			walked += 1

		for dir_name in access.get_directories():

			if dir_name.begins_with("."):
				continue

			stack.append(
				current_dir + dir_name + "/"
			)

	paths.sort()

	return {
		"ok": true,
		"paths": paths,
		"truncated_walk": truncated_walk,
	}


func _normalize_prefix(
	raw_prefix,
	action_name: String
) -> Dictionary:

	if raw_prefix == null:
		return {"ok": true, "prefix": ""}

	if typeof(raw_prefix) != TYPE_STRING:

		return {
			"success": false,
			"error": (
				action_name
				+ " prefix must be a string."
			)
		}

	var prefix := (
		str(raw_prefix)
		.strip_edges()
		.lstrip("/")
		.trim_prefix("res://")
	)

	if prefix.ends_with("/"):
		prefix = prefix.rstrip("/")

	return {"ok": true, "prefix": prefix}


func _normalize_extension_filter(
	extensions,
	default_extensions: Array,
	action_name: String
) -> Dictionary:

	if extensions == null:
		return {
			"ok": true,
			"extensions": default_extensions.duplicate()
		}

	if not (extensions is Array):

		return {
			"success": false,
			"error": (
				action_name
				+ " extensions must be a list "
				+ "of strings."
			)
		}

	var normalized: Array = []

	for extension in extensions:

		if typeof(extension) != TYPE_STRING:

			return {
				"success": false,
				"error": (
					action_name
					+ " extensions must be a "
					+ "list of strings."
				)
			}

		var ext := (
			str(extension)
			.strip_edges()
			.to_lower()
			.lstrip(".")
		)

		if ext.is_empty():
			continue

		normalized.append(ext)

	if normalized.is_empty():

		return {
			"success": false,
			"error": (
				action_name
				+ " extensions must not be "
				+ "empty when provided."
			)
		}

	return {
		"ok": true,
		"extensions": normalized
	}


func _coerce_positive_int(
	raw_value,
	default_value: int,
	max_value: int,
	action_name: String,
	value_label: String
) -> Dictionary:

	# JSON request bodies decode integral numbers
	# as floats in GDScript, so accept both int
	# and float and coerce.

	if raw_value == null:
		return {
			"ok": true,
			"value": default_value
		}

	if (
		typeof(raw_value) != TYPE_INT
		and typeof(raw_value) != TYPE_FLOAT
	):

		return {
			"success": false,
			"error": (
				action_name + " " + value_label
				+ " must be an integer between "
				+ "1 and " + str(max_value) + "."
			)
		}

	var value := int(raw_value)

	if value < 1 or value > max_value:

		return {
			"success": false,
			"error": (
				action_name + " " + value_label
				+ " must be an integer between "
				+ "1 and " + str(max_value) + "."
			)
		}

	return {"ok": true, "value": value}


func _open_scene_paths() -> Array:

	# Best-effort list of scenes currently open in
	# the editor; empty when unavailable (headless).

	var open_paths: Array = []

	if editor_interface == null:
		return open_paths

	for scene_path in editor_interface.get_open_scenes():
		open_paths.append(str(scene_path))

	return open_paths


func _edited_scene_stale_script_nodes(
	old_path: String
) -> Array:

	# Best-effort scan of the currently edited scene
	# for nodes still holding the OLD script attached
	# (a disk rename does not rewire live nodes).
	# Unavailable headless (no helpers, no scene):
	# reported as an empty list, never fabricated.

	var stale: Array = []

	if scene_helpers == null:
		return stale

	var scene_result: Dictionary = (
		scene_helpers
		.get_edited_scene_root_or_error()
	)

	if not scene_result.get("success", false):
		return stale

	var scene_root: Node = (
		scene_result["scene_root"]
	)

	if scene_root == null:
		return stale

	var stack: Array = [scene_root]

	while not stack.is_empty():

		var current: Node = stack.pop_back()

		var current_script: Variant = (
			current.get_script()
		)

		if current_script is GDScript:

			var typed_script: GDScript = current_script

			if typed_script.resource_path == old_path:

				stale.append(
					str(
						scene_root.get_path_to(current)
					)
				)

		for child in current.get_children():

			if child is Node:
				stack.append(child)

	return stale


# ==========================================
# rename_script
# ==========================================


func rename_script_from_request(
	data: Dictionary
) -> Dictionary:

	var old_check := (
		_normalize_script_path(
			data.get("script_path"),
			"rename_script"
		)
	)

	if not old_check.get("ok", false):
		return old_check

	var new_check := (
		_normalize_script_path(
			data.get("new_script_path"),
			"rename_script"
		)
	)

	if not new_check.get("ok", false):
		return new_check

	var old_path: String = (
		old_check["script_path"]
	)

	var new_path: String = (
		new_check["script_path"]
	)

	if old_path == new_path:

		return {
			"success": false,
			"error": (
				"rename_script: new_script_path "
				+ "is identical to script_path."
			)
		}

	if not FileAccess.file_exists(old_path):

		return {
			"success": false,
			"error": (
				"rename_script: script not found: "
				+ old_path
			)
		}

	if FileAccess.file_exists(new_path):

		return {
			"success": false,
			"error": (
				"rename_script: target already "
				+ "exists: "
				+ new_path
				+ ". Existing files are never "
				+ "overwritten."
			)
		}

	# Ensure the destination directory exists BEFORE
	# any file is written, so a mid-operation
	# directory failure cannot leave the project
	# half-updated.

	var dir_result := (
		_ensure_parent_dir(new_path)
	)

	if not dir_result.get("ok", false):

		return {
			"success": false,
			"error": (
				"rename_script: "
				+ dir_result["error"]
			)
		}

	var walk_result := (
		_walk_project_files("")
	)

	if not walk_result.get("ok", false):
		return walk_result

	if walk_result["truncated_walk"]:

		return {
			"success": false,
			"error": (
				"rename_script: project file walk "
				+ "was truncated at "
				+ str(REFACTOR_MAX_WALK)
				+ " files; refusing to rename "
				+ "without seeing all references."
			)
		}

	# Phase 1: compute new content for every file
	# referencing the old path. Nothing is checked or
	# written yet.

	var candidates: Array = []

	for file_path in walk_result["paths"]:

		var file_ext: String = (
			str(file_path.get_extension())
		)

		var is_reference_file: bool = (
			REFERENCE_FILE_EXTENSIONS.has(file_ext)
			or file_path == "res://project.godot"
		)

		if not is_reference_file:
			continue

		var read_result := (
			_read_text_file(file_path)
		)

		if not read_result.get("ok", false):
			continue

		var content: String = read_result["source"]

		var occurrence_count: int = content.count(
			old_path
		)

		if occurrence_count == 0:
			continue

		candidates.append(
			{
				"file_path": file_path,
				"original_content": content,
				"new_content": content.replace(
					old_path,
					new_path
				),
				"replacement_count": occurrence_count,
			}
		)

	# Phase 2: MOVE the script file (and its .uid
	# sidecar) BEFORE parse-checking, because GDScript
	# preload() resolves at parse time: an updated
	# preload only parses once the target path exists.

	var old_uid_path: String = (
		old_path + ".uid"
	)

	var new_uid_path: String = (
		new_path + ".uid"
	)

	var move_error := DirAccess.rename_absolute(
		old_path,
		new_path
	)

	if move_error != OK:

		return {
			"success": false,
			"error": (
				"rename_script: could not move "
				+ old_path + " to " + new_path
				+ ". Error: "
				+ error_string(move_error)
			),
		}

	var uid_renamed := false

	if FileAccess.file_exists(old_uid_path):

		var uid_error := DirAccess.rename_absolute(
			old_uid_path,
			new_uid_path
		)

		uid_renamed = (
			uid_error == OK
			and FileAccess.file_exists(new_uid_path)
		)

	# Phase 3: parse-gate the affected .gd files. The
	# moved script must exist at its NEW path for
	# preload() to resolve, hence the ordering. A file
	# whose ORIGINAL content already failed to parse is
	# never made worse by a path replacement and does
	# not block the rename. On any regression the move
	# is rolled back and NOTHING is written.

	var parse_failures: Array = []

	for candidate in candidates:

		var file_ext: String = str(
			candidate["file_path"].get_extension()
		)

		if file_ext != "gd":
			continue

		var new_parse := _parse_check(
			candidate["new_content"]
		)

		if new_parse["ok"]:
			continue

		var old_parse := _parse_check(
			candidate["original_content"]
		)

		if not old_parse["ok"]:
			continue

		parse_failures.append(
			{
				"file_path": candidate["file_path"],
				"error": new_parse["error"],
			}
		)

	if not parse_failures.is_empty():

		var rollback_error := (
			DirAccess.rename_absolute(
				new_path,
				old_path
			)
		)

		if uid_renamed:

			DirAccess.rename_absolute(
				new_uid_path,
				old_uid_path
			)

		return {
			"success": false,
			"error": (
				"rename_script: updating references "
				+ "would break the parse of "
				+ str(parse_failures.size())
				+ " script(s); the rename was rolled "
				+ "back and nothing was written."
			),
			"parse_failures": parse_failures,
			"rollback_ok": rollback_error == OK,
		}

	# Phase 4: write every updated reference file,
	# verifying each write by reading it back. The
	# script's own file (if it referenced its old path)
	# is written at its NEW location.

	var changed_files: Array = []

	var total_updates := 0

	for candidate in candidates:

		var write_path: String = (
			new_path
			if candidate["file_path"] == old_path
			else candidate["file_path"]
		)

		var write_result := _write_text_file(
			write_path,
			candidate["new_content"]
		)

		if not write_result.get("ok", false):

			return {
				"success": false,
				"error": (
					"rename_script: "
					+ write_result["error"]
				),
				"changed_files": changed_files,
			}

		changed_files.append(
			{
				"file_path": write_path,
				"replacement_count": (
					candidate["replacement_count"]
				),
				"verified_write": write_result["verified"],
			}
		)

		total_updates += (
			candidate["replacement_count"]
		)

	# Post-mutation verification: the file moved, it
	# loads as a GDScript, and no textual reference to
	# the old path remains in scanned project files.

	var verified_move: bool = (
		FileAccess.file_exists(new_path)
		and not FileAccess.file_exists(old_path)
	)

	var verified_load := false

	if verified_move:

		var loaded: Variant = load(new_path)

		verified_load = loaded is GDScript

	var rescan := _walk_project_files("")

	var remaining_references := 0

	if rescan.get("ok", false):

		for file_path in rescan["paths"]:

			var file_ext: String = (
				str(file_path.get_extension())
			)

			if not (
				REFERENCE_FILE_EXTENSIONS.has(file_ext)
				or file_path == "res://project.godot"
			):
				continue

			var check := _read_text_file(file_path)

			if not check.get("ok", false):
				continue

			if check["source"].contains(old_path):
				remaining_references += 1

	var stale_nodes := (
		_edited_scene_stale_script_nodes(old_path)
	)

	return {
		"success": true,
		"action": "rename_script",
		"message": (
			"Script renamed and references "
			+ "updated successfully."
		),
		"old_path": old_path,
		"new_path": new_path,
		"changed_files": changed_files,
		"changed_file_count": changed_files.size(),
		"total_reference_updates": total_updates,
		"uid_renamed": uid_renamed,
		"verified_move": verified_move,
		"verified_load": verified_load,
		"remaining_old_references": (
			remaining_references
		),
		"verified_no_leftover_references": (
			remaining_references == 0
		),
		"edited_scene_stale_script_nodes": stale_nodes,
		"undoable": false,
	}


# ==========================================
# find_replace_across_files
# ==========================================


func find_replace_across_files_from_request(
	data: Dictionary
) -> Dictionary:

	if not data.has("old_string"):

		return {
			"success": false,
			"error": (
				"find_replace_across_files requires "
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
				"find_replace_across_files requires "
				+ "a non-empty old_string."
			)
		}

	if not data.has("new_string"):

		return {
			"success": false,
			"error": (
				"find_replace_across_files requires "
				+ "new_string."
			)
		}

	if not data_has_string(data["new_string"]):

		return {
			"success": false,
			"error": (
				"find_replace_across_files "
				+ "new_string must be a string."
			)
		}

	var old_string: String = data["old_string"]

	var new_string: String = data["new_string"]

	if old_string == new_string:

		return {
			"success": false,
			"error": (
				"find_replace_across_files: "
				+ "old_string and new_string are "
				+ "identical; nothing would change."
			)
		}

	var prefix_check := _normalize_prefix(
		data.get("prefix"),
		"find_replace_across_files"
	)

	if not prefix_check.get("ok", false):
		return prefix_check

	var prefix: String = prefix_check["prefix"]

	var extension_check := (
		_normalize_extension_filter(
			data.get("extensions"),
			REPLACE_DEFAULT_EXTENSIONS,
			"find_replace_across_files"
		)
	)

	if not extension_check.get("ok", false):
		return extension_check

	var extensions: Array = (
		extension_check["extensions"]
	)

	var max_files_check := (
		_coerce_positive_int(
			data.get("max_files"),
			REPLACE_DEFAULT_MAX_FILES,
			REPLACE_MAX_MAX_FILES,
			"find_replace_across_files",
			"max_files"
		)
	)

	if not max_files_check.get("ok", false):
		return max_files_check

	var max_files: int = max_files_check["value"]

	var walk_result := (
		_walk_project_files(prefix)
	)

	if not walk_result.get("ok", false):
		return walk_result

	# Phase 1: find and compute. Every file that
	# contains old_string becomes a candidate; a
	# candidate set larger than max_files refuses the
	# whole request rather than partially applying it.

	var candidates: Array = []

	var parse_failures: Array = []

	var scanned_files := 0

	var skipped_large_files := 0

	var truncated_walk: bool = (
		walk_result["truncated_walk"]
	)

	for file_path in walk_result["paths"]:

		var file_ext: String = (
			str(file_path.get_extension())
		)

		if not extensions.has(file_ext):
			continue

		scanned_files += 1

		if FileAccess.get_modified_time(file_path) < 0:
			continue

		var file_handle := FileAccess.open(
			file_path,
			FileAccess.READ
		)

		if file_handle == null:
			continue

		var content: String = (
			file_handle.get_as_text()
		)

		file_handle.close()

		if content.to_utf8_buffer().size() > (
			REFACTOR_MAX_FILE_BYTES
		):

			skipped_large_files += 1

			continue

		var occurrence_count: int = content.count(
			old_string
		)

		if occurrence_count == 0:
			continue

		var new_content: String = content.replace(
			old_string,
			new_string
		)

		if file_ext == "gd":

			# Regression-only gate: a fresh detached
			# parse of a script whose class_name is
			# already registered in the running editor
			# fails spuriously (duplicate global class).
			# Only a file whose ORIGINAL content parsed
			# but whose NEW content does not counts as
			# a failure; pre-existing broken files are
			# never made worse by a replacement.

			var new_parse := _parse_check(
				new_content
			)

			if not new_parse["ok"]:

				var old_parse := _parse_check(
					content
				)

				if old_parse["ok"]:

					parse_failures.append(
						{
							"file_path": file_path,
							"error": new_parse["error"],
						}
					)

					continue

		candidates.append(
			{
				"file_path": file_path,
				"new_content": new_content,
				"replacement_count": occurrence_count,
			}
		)

	if not parse_failures.is_empty():

		return {
			"success": false,
			"error": (
				"find_replace_across_files: the "
				+ "replacement would break the "
				+ "parse of "
				+ str(parse_failures.size())
				+ " script(s); nothing was written."
			),
			"parse_failures": parse_failures,
			"scanned_files": scanned_files,
		}

	if truncated_walk:

		return {
			"success": false,
			"error": (
				"find_replace_across_files: the "
				+ "project file walk was truncated "
				+ "at "
				+ str(REFACTOR_MAX_WALK)
				+ " files; refusing to replace "
				+ "without seeing all matches. "
				+ "Narrow the prefix."
			),
			"scanned_files": scanned_files,
		}

	if candidates.size() > max_files:

		return {
			"success": false,
			"error": (
				"find_replace_across_files: "
				+ str(candidates.size())
				+ " files would be modified but "
				+ "max_files is "
				+ str(max_files)
				+ ". Nothing was written. Narrow "
				+ "the prefix/extensions or raise "
				+ "max_files."
			),
			"matching_file_count": candidates.size(),
			"scanned_files": scanned_files,
		}

	if candidates.is_empty():

		return {
			"success": false,
			"error": (
				"find_replace_across_files: "
				+ "old_string was not found in any "
				+ "of the "
				+ str(scanned_files)
				+ " scanned file(s). Use "
				+ "search_in_files to confirm the "
				+ "current state."
			),
			"scanned_files": scanned_files,
		}

	# Phase 2: write every candidate, verifying each
	# write by reading it back and confirming the old
	# string is gone.

	var changed_files: Array = []

	var total_replacements := 0

	var verified_all := true

	for candidate in candidates:

		var write_result := _write_text_file(
			candidate["file_path"],
			candidate["new_content"]
		)

		if not write_result.get("ok", false):

			return {
				"success": false,
				"error": (
					"find_replace_across_files: "
					+ write_result["error"]
				),
				"changed_files": changed_files,
			}

		var readback := _read_text_file(
			candidate["file_path"]
		)

		# Exact-content verification: comparing against
		# the computed replacement avoids the substring
		# trap where new_string contains old_string
		# (e.g. "Node" -> "Node2D") and would falsely
		# look like a leftover match.

		var file_verified: bool = (
			readback.get("ok", false)
			and readback["source"] == (
				candidate["new_content"]
			)
		)

		if not file_verified:
			verified_all = false

		changed_files.append(
			{
				"file_path": candidate["file_path"],
				"replacement_count": (
					candidate["replacement_count"]
				),
				"verified_write": file_verified,
			}
		)

		total_replacements += (
			candidate["replacement_count"]
		)

	# Editor-overlap warning: files currently open in
	# the editor are modified on disk; the editor's
	# in-memory copies are not reloaded by this call.

	var open_paths := _open_scene_paths()

	var open_scene_overlap: Array = []

	for changed in changed_files:

		if open_paths.has(changed["file_path"]):
			open_scene_overlap.append(
				changed["file_path"]
			)

	return {
		"success": true,
		"action": "find_replace_across_files",
		"message": (
			"Replaced occurrences across "
			+ str(changed_files.size())
			+ " file(s) successfully."
		),
		"old_string": old_string,
		"new_string": new_string,
		"extensions": extensions,
		"prefix": prefix,
		"changed_files": changed_files,
		"changed_file_count": changed_files.size(),
		"total_replacements": total_replacements,
		"scanned_files": scanned_files,
		"skipped_large_files": skipped_large_files,
		"verified_no_leftover_matches": verified_all,
		"open_scene_overlap": open_scene_overlap,
		"undoable": false,
	}



# ==========================================
# checkpoint tools
# ==========================================
# File-level safety net: snapshot the project's text
# files into res://.agent_checkpoints/<id>/ and restore
# them on demand. Deliberately bounded (walk cap, per-
# file size cap) and deliberately NOT undoable - a
# restore is itself a mutation and is verified by
# read-back. The checkpoint directory is editor-
# internal (hidden folder, excluded from the other
# tools' scans).


const CHECKPOINT_ROOT := "res://.agent_checkpoints"

const CHECKPOINT_MAX_TOTAL_BYTES := 268435456


func _checkpoint_extensions() -> Array:

	return REFERENCE_FILE_EXTENSIONS + [
		"uid", "json", "md", "txt", "import",
	]


func checkpoint_create_from_request(
	data: Dictionary
) -> Dictionary:

	var label := "checkpoint"

	if data.has("label") and data["label"] != null:

		if typeof(data["label"]) != TYPE_STRING:
			return {
				"success": false,
				"error": (
					"checkpoint_create label must be a "
					+ "string."
				),
			}

		label = str(data["label"]).strip_edges()

	var stamp := str(
		Time.get_unix_time_from_system()
	)
	stamp = stamp.replace(".", "_")

	var checkpoint_id := label + "-" + stamp

	var target_root := (
		CHECKPOINT_ROOT + "/" + checkpoint_id
	)

	var walk_result := _walk_project_files("")

	if not walk_result.get("ok", false):
		return walk_result

	var copied := 0

	var total_bytes := 0

	var skipped: Array = []

	for file_path in walk_result["paths"]:

		if file_path.begins_with(CHECKPOINT_ROOT):
			continue

		var file_ext: String = str(
			file_path.get_extension()
		)

		var file_name: String = file_path.get_file()

		var is_text: bool = (
			REFERENCE_FILE_EXTENSIONS.has(file_ext)
			or file_path == "res://project.godot"
			or ["uid", "json", "md", "txt", "import"]
			.has(file_ext)
		)

		if not is_text:
			continue

		var read_result := _read_text_file(file_path)

		if not read_result.get("ok", false):
			skipped.append(file_path)
			continue

		var content: String = read_result["source"]

		var size: int = content.to_utf8_buffer().size()

		if size > REFACTOR_MAX_FILE_BYTES:
			skipped.append(file_path)
			continue

		total_bytes += size

		if total_bytes > CHECKPOINT_MAX_TOTAL_BYTES:
			return {
				"success": false,
				"error": (
					"checkpoint_create exceeded the total "
					+ "size budget; nothing was written."
				),
			}

		var backup_path: String = (
			target_root + "/" + file_path.trim_prefix("res://")
		)

		var dir_result := _ensure_parent_dir(backup_path)

		if not dir_result.get("ok", false):
			return {
				"success": false,
				"error": (
					"checkpoint_create: "
					+ dir_result["error"]
				),
			}

		var write_result := _write_text_file(
			backup_path,
			content
		)

		if not write_result.get("ok", false):
			return {
				"success": false,
				"error": (
					"checkpoint_create: "
					+ write_result["error"]
				),
			}

		copied += 1

	return {
		"success": true,
		"action": "checkpoint_create",
		"checkpoint_id": checkpoint_id,
		"file_count": copied,
		"total_bytes": total_bytes,
		"skipped_files": skipped.size(),
		"undoable": false,
}

func checkpoint_list_from_request(
	_data: Dictionary
) -> Dictionary:

	var root := DirAccess.open(CHECKPOINT_ROOT)

	if root == null:

		return {
			"success": true,
			"action": "checkpoint_list",
			"checkpoints": [],
		}

	var checkpoints: Array = []

	for checkpoint_id in root.get_directories():

		var dir := DirAccess.open(
			CHECKPOINT_ROOT + "/" + checkpoint_id
		)

		var file_count := 0

		if dir != null:

			var stack: Array = [CHECKPOINT_ROOT + "/" + checkpoint_id]

			while not stack.is_empty():

				var current: String = stack.pop_back()

				if not current.ends_with("/"):
					current = current + "/"

				var access := DirAccess.open(current)

				if access == null:
					continue

				file_count += access.get_files().size()

				for sub in access.get_directories():
					stack.append(current + sub + "/")

		checkpoints.append(
			{
				"checkpoint_id": checkpoint_id,
				"file_count": file_count,
			}
		)

	checkpoints.sort_custom(
		func(a, b):
			return a["checkpoint_id"] < b["checkpoint_id"]
	)

	return {
		"success": true,
		"action": "checkpoint_list",
		"checkpoints": checkpoints,
		"count": checkpoints.size(),
	}


func checkpoint_restore_from_request(
	data: Dictionary
) -> Dictionary:

	if not data.has("checkpoint_id"):

		return {
			"success": false,
			"error": (
				"checkpoint_restore requires "
				+ "checkpoint_id."
			)
		}

	var checkpoint_id: String = str(
		data["checkpoint_id"]
	).strip_edges()

	var checkpoint_root := (
		CHECKPOINT_ROOT + "/" + checkpoint_id
	)

	if checkpoint_id.is_empty() \
			or checkpoint_id.contains("..") \
			or checkpoint_id.contains("/"):

		return {
			"success": false,
			"error": (
				"checkpoint_restore: invalid "
				+ "checkpoint_id."
			)
		}

	if not DirAccess.dir_exists_absolute(checkpoint_root):

		return {
			"success": false,
			"error": (
				"checkpoint_restore: unknown "
				+ "checkpoint: "
				+ checkpoint_id
			)
		}

	# Walk the checkpoint copy and restore every file to
	# its project location, verifying each write by
	# reading it back.

	var restored: Array = []

	var stack: Array = [checkpoint_root]

	var walked := 0

	while not stack.is_empty():

		if walked > REFACTOR_MAX_WALK:

			return {
				"success": false,
				"error": (
					"checkpoint_restore: checkpoint "
					+ "exceeds the walk cap; restore "
					+ "aborted."
				)
			}

		var current: String = stack.pop_back()

		if not current.ends_with("/"):
			current = current + "/"

		var access := DirAccess.open(current)

		if access == null:
			continue

		for file_name in access.get_files():

			var backup_path: String = (
				current + file_name
			)

			var project_path: String = (
				"res://"
				+ backup_path.trim_prefix(
					CHECKPOINT_ROOT + "/"
				).trim_prefix("/")
			)

			var read_result := _read_text_file(
				backup_path
			)

			if not read_result.get("ok", false):
				continue

			var write_result := _write_text_file(
				project_path,
				read_result["source"]
			)

			if not write_result.get("ok", false):

				return {
					"success": false,
					"error": (
						"checkpoint_restore: "
						+ write_result["error"]
					),
					"restored_files": restored,
				}

			restored.append(project_path)

			walked += 1

			for sub in access.get_directories():
				stack.append(current + sub + "/")

	return {
		"success": true,
		"action": "checkpoint_restore",
		"checkpoint_id": checkpoint_id,
		"restored_count": restored.size(),
		"restored_files": restored,
		"undoable": false,
	}
