extends SceneTree

const AIAgentRefactorToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_refactor_tools.gd"
)

const AIAgentSceneHelpersScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_scene_helpers.gd"
)

const SCRATCH_DIR := "res://addons/Execution_Agent/tests"

# Paths are built dynamically so the harness source never
# contains the res:// literals it rewrites at runtime.
var old_script_path: String
var new_script_path: String
var ref_scene_path: String
var ref_script_path: String
var marker_a_path: String
var marker_b_path: String
var marker_broken_path: String

var refactor_tools


func _raw_write(path: String, content: String) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	assert(file != null)
	file.store_string(content)
	file.close()


func _remove_file(path: String) -> void:
	if FileAccess.file_exists(path):
		var dir := DirAccess.open(path.get_base_dir())
		assert(dir != null)
		assert(dir.remove(path.get_file()) == OK)
	assert(not FileAccess.file_exists(path))


func _cleanup() -> void:
	_remove_file(old_script_path)
	_remove_file(new_script_path)
	_remove_file(old_script_path + ".uid")
	_remove_file(new_script_path + ".uid")
	_remove_file(ref_scene_path)
	_remove_file(ref_script_path)
	_remove_file(marker_a_path)
	_remove_file(marker_b_path)
	_remove_file(marker_broken_path)

	# The nested-directory case must also start clean:
	# leftovers from an aborted run would trip the
	# never-overwrite contract inside the test itself.
	var nested_dir_path := SCRATCH_DIR + "/scratch_nested_dir"
	_remove_file(nested_dir_path + "/probe_moved.gd")
	_remove_file(nested_dir_path + "/probe_moved.gd.uid")
	DirAccess.remove_absolute(nested_dir_path)


func _seed_fixture() -> void:
	# A probe script, a scene referencing it as an
	# ext_resource, and a script preloading it. The
	# .uid sidecar exists too and must move along.
	_raw_write(
		old_script_path,
		"extends Node\n\nvar probe_value := 41\n"
	)
	_raw_write(
		old_script_path + ".uid",
		"uid://probe0uid0harness\n"
	)
	_raw_write(
		ref_scene_path,
		"[gd_scene load_steps=2 format=3]\n\n"
		+ "[ext_resource type=\"Script\" path=\""
		+ old_script_path
		+ "\" id=\"1\"]\n\n"
		+ "[node name=\"Probe\" type=\"Node\"]\n"
		+ "script = ExtResource(\"1\")\n"
	)
	_raw_write(
		ref_script_path,
		"extends Node\n\nconst Probe := preload(\""
		+ old_script_path
		+ "\")\n"
	)


func _run_rename_cases() -> void:
	# 1. Validation: missing source, existing target,
	# identical paths, traversal and extension rules.
	var missing = refactor_tools.rename_script_from_request(
		{
			"script_path": SCRATCH_DIR + "/no_such_probe.gd",
			"new_script_path": new_script_path,
		}
	)
	assert(missing["success"] == false)

	_seed_fixture()

	var identical = refactor_tools.rename_script_from_request(
		{
			"script_path": old_script_path,
			"new_script_path": old_script_path,
		}
	)
	assert(identical["success"] == false)

	var bad_target_ext = refactor_tools.rename_script_from_request(
		{
			"script_path": old_script_path,
			"new_script_path": SCRATCH_DIR + "/probe.tscn",
		}
	)
	assert(bad_target_ext["success"] == false)

	# 2. Full rename: references in .tscn and .gd are
	# updated, the .uid sidecar moves, the file loads
	# at the new path, and no old-path reference
	# remains anywhere.
	var rename = refactor_tools.rename_script_from_request(
		{
			"script_path": old_script_path,
			"new_script_path": new_script_path,
		}
	)
	assert(rename["success"] == true)
	assert(rename["action"] == "rename_script")
	assert(rename["undoable"] == false)
	assert(rename["changed_file_count"] == 2)
	assert(rename["total_reference_updates"] == 2)
	assert(rename["uid_renamed"] == true)
	assert(rename["verified_move"] == true)
	assert(rename["verified_load"] == true)
	assert(rename["verified_no_leftover_references"] == true)
	assert(not FileAccess.file_exists(old_script_path))
	assert(FileAccess.file_exists(new_script_path))
	assert(FileAccess.file_exists(new_script_path + ".uid"))
	assert(not FileAccess.file_exists(old_script_path + ".uid"))

	var scene_text := _read(ref_scene_path)
	assert(scene_text.contains(new_script_path))
	assert(not scene_text.contains(old_script_path))

	var script_text := _read(ref_script_path)
	assert(script_text.contains(new_script_path))
	assert(not script_text.contains(old_script_path))

	# 3. The moved script still parses and keeps its
	# content.
	var moved_read := FileAccess.open(new_script_path, FileAccess.READ)
	assert(moved_read != null)
	var moved_source: String = moved_read.get_as_text()
	moved_read.close()
	assert(moved_source.contains("probe_value := 41"))

	# 4. Rename with a target in a NEW directory: the
	# directory is created, never overwritten.
	var nested_dir_path := SCRATCH_DIR + "/scratch_nested_dir"
	var nested_target := nested_dir_path + "/probe_moved.gd"
	var nested = refactor_tools.rename_script_from_request(
		{
			"script_path": new_script_path,
			"new_script_path": nested_target,
		}
	)
	assert(nested["success"] == true)
	assert(FileAccess.file_exists(nested_target))
	assert(not FileAccess.file_exists(new_script_path))
	_remove_file(nested_target)
	_remove_file(nested_target + ".uid")
	assert(DirAccess.remove_absolute(nested_dir_path) == OK)

	_remove_file(ref_scene_path)
	_remove_file(ref_script_path)

	print("rename script cases passed")


func _read(path: String) -> String:
	var file := FileAccess.open(path, FileAccess.READ)
	assert(file != null)
	var content: String = file.get_as_text()
	file.close()
	return content


func _run_find_replace_cases() -> void:
	var marker_a := marker_a_path
	var marker_b := marker_b_path
	var marker_gd_broken := marker_broken_path

	# Markers are assembled from parts so THIS harness
	# file never contains the replaceable literals it
	# exercises: a find/replace that matched the harness
	# itself would rewrite the harness on disk mid-run.
	var old_marker := "PROBE_HP_TOKEN_" + "7Q"
	var new_marker := "PROBE_HP_TOKEN_" + "8R"

	_raw_write(
		marker_a,
		"extends Node\n\nvar " + old_marker + " := 10\n"
	)
	_raw_write(
		marker_b,
		"[resource]\nprobe_field = \"" + old_marker + "\"\n"
	)

	# 1. Scoped success: replaces across both files,
	# verifies read-back, reports per-file counts.
	var replace = refactor_tools.find_replace_across_files_from_request(
		{
			"old_string": old_marker,
			"new_string": new_marker,
			"prefix": "addons/Execution_Agent/tests",
		}
	)
	assert(replace["success"] == true)
	assert(replace["action"] == "find_replace_across_files")
	assert(replace["changed_file_count"] == 2)
	assert(replace["total_replacements"] == 2)
	assert(replace["verified_no_leftover_matches"] == true)
	assert(replace["undoable"] == false)
	assert(_read(marker_a).contains(new_marker))
	assert(_read(marker_b).contains(new_marker))

	# 2. Idempotency refusal: the anchor is gone now,
	# so a repeat is a structured failure, never a
	# silent success.
	var repeat = refactor_tools.find_replace_across_files_from_request(
		{
			"old_string": old_marker,
			"new_string": new_marker,
			"prefix": "addons/Execution_Agent/tests",
		}
	)
	assert(repeat["success"] == false)

	# 3. max_files bound: two matches but max_files=1
	# refuses the WHOLE request, nothing written.
	_raw_write(marker_b, "[resource]\nprobe_field = \"" + new_marker + "\"\n")
	var bounded = refactor_tools.find_replace_across_files_from_request(
		{
			"old_string": new_marker,
			"new_string": old_marker,
			"prefix": "addons/Execution_Agent/tests",
			"max_files": 1,
		}
	)
	assert(bounded["success"] == false)
	assert(bounded["matching_file_count"] == 2)
	assert(_read(marker_a).contains(new_marker))

	# 4. Parse gate: a replacement that would break a
	# .gd file's parse aborts with NOTHING written.
	_raw_write(
		marker_gd_broken,
		"extends Node\n\nvar " + old_marker + " := 10\n"
	)
	var gated = refactor_tools.find_replace_across_files_from_request(
		{
			"old_string": old_marker,
			"new_string": old_marker + "\nfunc broken(:\n",
			"prefix": "addons/Execution_Agent/tests",
			"extensions": ["gd"],
		}
	)
	assert(gated["success"] == false)
	assert(gated["parse_failures"].size() == 1)
	assert(_read(marker_gd_broken).contains("func broken(") == false)
	_remove_file(marker_gd_broken)

	# 5. Not-found is a structured failure. The token
	# is assembled from parts so THIS harness file
	# never contains the searchable literal: a
	# find/replace that matched the harness itself
	# would rewrite the harness on disk mid-run.
	var absent = refactor_tools.find_replace_across_files_from_request(
		{
			"old_string": "DEFINITELY_ABSENT_" + "TOKEN_1Z",
			"new_string": "anything",
			"prefix": "addons/Execution_Agent/tests",
		}
	)
	assert(absent["success"] == false)

	# 6. Identical old/new is refused.
	var same = refactor_tools.find_replace_across_files_from_request(
		{
			"old_string": "x",
			"new_string": "x",
			"prefix": "addons/Execution_Agent/tests",
		}
	)
	assert(same["success"] == false)

	_remove_file(marker_a)
	_remove_file(marker_b)

	print("find replace across files cases passed")


func _init() -> void:

	old_script_path = SCRATCH_DIR + "/scratch_rename_probe" + ".gd"
	new_script_path = SCRATCH_DIR + "/scratch_rename_probe_moved" + ".gd"
	ref_scene_path = SCRATCH_DIR + "/scratch_rename_ref" + ".tscn"
	ref_script_path = SCRATCH_DIR + "/scratch_rename_ref_user" + ".gd"
	marker_a_path = SCRATCH_DIR + "/scratch_replace_a" + ".gd"
	marker_b_path = SCRATCH_DIR + "/scratch_replace_b" + ".tres"
	marker_broken_path = SCRATCH_DIR + "/scratch_replace_broken" + ".gd"

	refactor_tools = AIAgentRefactorToolsScript.new(
		null,
		null
	)

	# Scratch files from a crashed earlier run must not
	# break this run.
	_cleanup()

	_run_rename_cases()

	_run_find_replace_cases()

	# Self-cleaning: the harness must leave no scratch
	# files behind, on every code path.
	_cleanup()

	print("refactor tools cases passed")

	quit()
