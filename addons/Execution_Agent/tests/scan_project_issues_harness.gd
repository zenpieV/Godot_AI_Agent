extends SceneTree

const AIAgentEditorToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_editor_tools.gd"
)

const SCRATCH_DIR := "res://addons/Execution_Agent/tests"

const SCAN_PREFIX := "addons/Execution_Agent/tests"

const GOOD_SCENE := (
	"res://addons/Execution_Agent/tests/scratch_lint_good.tscn"
)

const BAD_SCRIPT := (
	"res://addons/Execution_Agent/tests/scratch_lint_bad.gd"
)

const BROKEN_SCENE := (
	"res://addons/Execution_Agent/tests/scratch_lint_broken.tscn"
)

var editor_tools


func _raw_write(path: String, content: String) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	assert(file != null)
	file.store_string(content)
	file.close()


func _remove_file(path: String) -> void:
	if FileAccess.file_exists(path):
		var dir := DirAccess.open(SCRATCH_DIR)
		assert(dir != null)
		assert(dir.remove(path.get_file()) == OK)
	assert(not FileAccess.file_exists(path))


func _cleanup() -> void:
	_remove_file(GOOD_SCENE)
	_remove_file(BAD_SCRIPT)
	_remove_file(BROKEN_SCENE)


func _run_cases() -> void:
	# Scratch files from a crashed earlier run must not
	# break this run.
	_cleanup()

	# 1. Validation: bad limit is a structured failure.
	var bad_limit = editor_tools.scan_project_issues_from_request(
		{"limit": 0}
	)
	assert(bad_limit["success"] == false)

	var bad_prefix = editor_tools.scan_project_issues_from_request(
		{"prefix": 5}
	)
	assert(bad_prefix["success"] == false)

	# 2. Seed fixtures: a GOOD minimal scene (must NOT be
	# reported), a script that does not parse, and a
	# scene whose only dependency does not exist on
	# disk. The dependency string is assembled from
	# parts so no fixture ever parses cleanly by
	# accident. The broken scene's ext_resource also
	# carries a uid attribute so get_dependencies()
	# returns the uid-form string
	# ("uid://...::res://...") that the existence check
	# must normalize (live-validated false positive).
	_raw_write(
		GOOD_SCENE,
		"[gd_scene format=3]\n\n"
		+ "[node name=\"LintGood\" type=\"Node\"]\n"
	)
	_raw_write(
		BAD_SCRIPT,
		"extends Node\nfunc broken(:\n"
	)
	_raw_write(
		BROKEN_SCENE,
		"[gd_scene load_steps=2 format=3]\n\n"
		+ "[ext_resource type=\"Script\" "
		+ "uid=\"uid://deadbeefcafe01\" "
		+ "path=\"res://"
		+ "addons/Execution_Agent/tests/no_such_dep_"
		+ "fixture.gd\" id=\"1\"]\n\n"
		+ "[node name=\"LintBroken\" type=\"Node\"]\n"
		+ "script = ExtResource(\"1\")\n"
	)

	var scan = editor_tools.scan_project_issues_from_request(
		{"prefix": SCAN_PREFIX}
	)

	# 3. Structured shape: bounded result metadata is
	# always present.
	assert(scan["success"] == true)
	assert(scan["action"] == "scan_project_issues")
	assert(scan["total_matches"] >= 2)
	assert(scan["scanned_files"] > 0)
	assert(scan.has("truncated"))
	assert(scan["issues"].size() == min(
		scan["total_matches"], scan["limit"]
	))

	# 4. The parse-broken script is reported with kind
	# script_parse_error.
	var found_parse_error := false
	var found_broken_scene := false
	var reported_paths := {}

	for issue in scan["issues"]:
		assert(issue.has("issue_kind"))
		assert(issue.has("file_path"))
		assert(issue.has("detail"))
		reported_paths[issue["file_path"]] = true

		if issue["file_path"] == BAD_SCRIPT:
			if issue["issue_kind"] == "script_parse_error":
				found_parse_error = true

		if issue["file_path"] == BROKEN_SCENE:
			# A scene with a missing dependency either
			# fails to load outright or loads with the
			# dependency reported missing; both are
			# honest detections.
			if (
				issue["issue_kind"] == "missing_dependency"
				or issue["issue_kind"] == "scene_load_failed"
			):
				found_broken_scene = true

	assert(found_parse_error == true)
	assert(found_broken_scene == true)

	# 5. The clean scene is never flagged.
	assert(reported_paths.has(GOOD_SCENE) == false)

	# 6. A prefix that does not exist is a structured
	# failure (same semantics as list_project_files),
	# never a fabricated clean scan.
	var empty_scan = editor_tools.scan_project_issues_from_request(
		{"prefix": "addons/Execution_Agent/tests_no_such_dir"}
	)
	assert(empty_scan["success"] == false)

	# 7. JSON-serializable result.
	assert(not JSON.stringify(scan).is_empty())

	_cleanup()

	print("scan project issues cases passed")


func _init() -> void:

	editor_tools = AIAgentEditorToolsScript.new(
		null,
		null
	)

	_run_cases()

	quit()
