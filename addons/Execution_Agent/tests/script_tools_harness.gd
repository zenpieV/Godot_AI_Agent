extends SceneTree

const AIAgentScriptToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_script_tools.gd"
)

const AIAgentSceneHelpersScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_scene_helpers.gd"
)

const SCRATCH_DIR := "res://addons/Execution_Agent/tests"

const SCRATCH_SCRIPT := (
	"res://addons/Execution_Agent/tests/scratch_script_harness.gd"
)

const SCRATCH_SCRIPT_2 := (
	"res://addons/Execution_Agent/tests/scratch_script_harness_2.gd"
)

const SCRATCH_BAD := (
	"res://addons/Execution_Agent/tests/scratch_script_harness_bad.gd"
)

const SCRATCH_PAGING := (
	"res://addons/Execution_Agent/tests/scratch_paging_probe.gd"
)

const VALID_CONTENT := (
	"extends Node\n\nvar probe_health := 10\n"
)

const VALID_CONTENT_2 := (
	"extends Node\n\nvar probe_second := 20\n"
)

const BROKEN_CONTENT := (
	"extends Node\nfunc broken(:\n"
)


# Stand-in scene helpers: identical to the pattern used by the
# signal harness. The real helpers need an EditorInterface; only
# the edited-scene-root lookup is faked with a real node tree.
class FakeSceneHelpers extends AIAgentSceneHelpersScript:

	var scene_root: Node

	func _init(p_scene_root: Node) -> void:
		super(null)
		scene_root = p_scene_root

	func get_edited_scene_root_or_error() -> Dictionary:
		return {
			"success": true,
			"scene_root": scene_root
		}


var root_node: Node
var script_tools


func _build_scene() -> void:
	root_node = Node.new()
	root_node.name = "Root"

	for child_name in ["Alpha", "Beta", "Gamma"]:
		var child := Node.new()
		child.name = child_name
		root_node.add_child(child)


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
	_remove_file(SCRATCH_SCRIPT)
	_remove_file(SCRATCH_SCRIPT_2)
	_remove_file(SCRATCH_BAD)
	_remove_file(SCRATCH_PAGING)


func _attached(path: String) -> bool:
	var node: Node = root_node.get_node(path)
	return node.get_script() != null


func _run_shared_validation_cases() -> void:
	# 1. create_script: missing fields.
	var missing_path = (
		script_tools.create_script_from_request(
			{"content": VALID_CONTENT}
		)
	)
	assert(not missing_path["success"])
	assert(missing_path["error"].contains("requires script_path"))

	var missing_content = (
		script_tools.create_script_from_request(
			{"script_path": SCRATCH_SCRIPT}
		)
	)
	assert(not missing_content["success"])
	assert(missing_content["error"].contains("requires content"))

	# 2. create_script: non-string and empty content.
	var non_string = (
		script_tools.create_script_from_request(
			{"script_path": SCRATCH_SCRIPT, "content": 5}
		)
	)
	assert(not non_string["success"])
	assert(non_string["error"].contains("must be a string"))

	var empty_content = (
		script_tools.create_script_from_request(
			{"script_path": SCRATCH_SCRIPT, "content": "   "}
		)
	)
	assert(not empty_content["success"])
	assert(empty_content["error"].contains("non-empty"))

	# 3. create_script: path discipline.
	var bad_extension = (
		script_tools.create_script_from_request(
			{"script_path": "res://scripts/x.txt", "content": VALID_CONTENT}
		)
	)
	assert(not bad_extension["success"])
	assert(bad_extension["error"].contains("ending in .gd"))

	var traversal = (
		script_tools.create_script_from_request(
			{"script_path": "res://../evil.gd", "content": VALID_CONTENT}
		)
	)
	assert(not traversal["success"])
	assert(traversal["error"].contains("traversal"))

	var backslash = (
		script_tools.create_script_from_request(
			{
				"script_path": "res://scripts\\x.gd",
				"content": VALID_CONTENT
			}
		)
	)
	assert(not backslash["success"])
	assert(backslash["error"].contains("forward slashes"))

	var empty_filename = (
		script_tools.create_script_from_request(
			{"script_path": "res://.gd", "content": VALID_CONTENT}
		)
	)
	assert(not empty_filename["success"])
	assert(empty_filename["error"].contains("non-empty script file name"))

	# 4. create_script: parse gate rejects broken content and
	# writes NOTHING to disk.
	var broken = (
		script_tools.create_script_from_request(
			{"script_path": SCRATCH_SCRIPT, "content": BROKEN_CONTENT}
		)
	)
	assert(not broken["success"])
	assert(broken["error"].contains("does not parse"))
	assert(broken["error"].contains("Nothing was written"))
	assert(not FileAccess.file_exists(SCRATCH_SCRIPT))

	# 5. create_script: existing files are never overwritten.
	_raw_write(SCRATCH_SCRIPT, VALID_CONTENT)
	var exists_result = (
		script_tools.create_script_from_request(
			{"script_path": SCRATCH_SCRIPT, "content": VALID_CONTENT}
		)
	)
	assert(not exists_result["success"])
	assert(exists_result["error"].contains("already exists"))
	_remove_file(SCRATCH_SCRIPT)

	# 6. get_script_content / diagnostics: missing script.
	var missing_read = (
		script_tools.get_script_content_from_request(
			{"script_path": SCRATCH_SCRIPT}
		)
	)
	assert(not missing_read["success"])
	assert(missing_read["error"].contains("script not found"))

	var missing_diag = (
		script_tools.list_script_diagnostics_from_request(
			{"script_path": SCRATCH_SCRIPT}
		)
	)
	assert(not missing_diag["success"])
	assert(missing_diag["error"].contains("script not found"))

	# 7. attach_script: validation.
	var attach_missing = (
		script_tools.attach_script_from_request({})
	)
	assert(not attach_missing["success"])
	assert(attach_missing["error"].contains("requires node_path"))

	var attach_missing_script = (
		script_tools.attach_script_from_request(
			{"node_path": "Alpha"}
		)
	)
	assert(not attach_missing_script["success"])
	assert(attach_missing_script["error"].contains("requires script_path"))

	var attach_ghost = (
		script_tools.attach_script_from_request(
			{"node_path": "Ghost", "script_path": SCRATCH_SCRIPT}
		)
	)
	assert(not attach_ghost["success"])
	assert(attach_ghost["error"].contains("Node not found"))

	# 8. attach_script: valid request but no undo manager ->
	# explicit unavailable error.
	_raw_write(SCRATCH_SCRIPT, VALID_CONTENT)
	var attach_unavailable = (
		script_tools.attach_script_from_request(
			{"node_path": "Alpha", "script_path": SCRATCH_SCRIPT}
		)
	)
	assert(not attach_unavailable["success"])
	assert(
		attach_unavailable["error"].contains(
			"running Godot editor"
		)
	)

	# 9. detach_script: idempotent no-op works WITHOUT the undo
	# manager (nothing changes, so nothing needs undo).
	var idempotent_detach = (
		script_tools.detach_script_from_request(
			{"node_path": "Alpha"}
		)
	)
	assert(idempotent_detach["success"])
	assert(idempotent_detach["changed"] == false)
	assert(idempotent_detach["verified_attachment"] == true)
	assert(idempotent_detach["undoable"] == false)

	# 10. detach_script: removing an EXISTING attachment is a real
	# mutation -> explicit unavailable error. Set one up through
	# the raw Node API.
	var raw_script: Variant = load(SCRATCH_SCRIPT)
	assert(raw_script != null)
	root_node.get_node("Alpha").set_script(raw_script)

	var detach_unavailable = (
		script_tools.detach_script_from_request(
			{"node_path": "Alpha"}
		)
	)
	assert(not detach_unavailable["success"])
	assert(
		detach_unavailable["error"].contains(
			"running Godot editor"
		)
	)

	root_node.get_node("Alpha").set_script(null)
	_remove_file(SCRATCH_SCRIPT)

	# 11. detach_script: missing fields and node.
	var detach_missing = (
		script_tools.detach_script_from_request({})
	)
	assert(not detach_missing["success"])
	assert(detach_missing["error"].contains("requires node_path"))

	var detach_ghost = (
		script_tools.detach_script_from_request(
			{"node_path": "Ghost"}
		)
	)
	assert(not detach_ghost["success"])
	assert(detach_ghost["error"].contains("Node not found"))

	# 12. Read-only tools work without the undo manager (negative
	# paths already covered above; positive roundtrips run in the
	# undo-capable phase below).


func _run_file_edit_cases() -> void:
	# File-edit cases work with and without the undo manager:
	# edit_script and replace_in_script are file writes.

	# 1. Validation: missing fields.
	var missing_content = (
		script_tools.edit_script_from_request(
			{"script_path": SCRATCH_SCRIPT}
		)
	)
	assert(not missing_content["success"])
	assert(missing_content["error"].contains("requires content"))

	var missing_old = (
		script_tools.replace_in_script_from_request(
			{"script_path": SCRATCH_SCRIPT, "new_string": "x"}
		)
	)
	assert(not missing_old["success"])
	assert(missing_old["error"].contains("requires old_string"))

	# 2. edit_script: never creates files.
	var edit_missing = (
		script_tools.edit_script_from_request(
			{"script_path": SCRATCH_SCRIPT, "content": VALID_CONTENT}
		)
	)
	assert(not edit_missing["success"])
	assert(edit_missing["error"].contains("script not found"))
	assert(edit_missing["error"].contains("create_script"))

	# 3. replace_in_script: missing file.
	var replace_missing = (
		script_tools.replace_in_script_from_request(
			{
				"script_path": SCRATCH_SCRIPT,
				"old_string": "probe_health",
				"new_string": "other"
			}
		)
	)
	assert(not replace_missing["success"])
	assert(replace_missing["error"].contains("script not found"))

	# Seed a script through the tool pipeline.
	var seeded = (
		script_tools.create_script_from_request(
			{"script_path": SCRATCH_SCRIPT, "content": VALID_CONTENT}
		)
	)
	if not FileAccess.file_exists(SCRATCH_SCRIPT):
		# create_script is parse-gated; seed via raw write when the
		# tool refused (e.g. content already on disk from a prior
		# crashed run is cleaned at start).
		_raw_write(SCRATCH_SCRIPT, VALID_CONTENT)

	# 4. edit_script: byte-identical replacement is a no-op.
	var idempotent_edit = (
		script_tools.edit_script_from_request(
			{"script_path": SCRATCH_SCRIPT, "content": VALID_CONTENT}
		)
	)
	assert(idempotent_edit["success"])
	assert(idempotent_edit["changed"] == false)
	assert(idempotent_edit["verified_write"] == true)

	# 5. edit_script: successful replacement with verification.
	var new_content := (
		"extends Node\n\nvar probe_health := 42\n"
	)
	var edit_result = (
		script_tools.edit_script_from_request(
			{"script_path": SCRATCH_SCRIPT, "content": new_content}
		)
	)
	assert(edit_result["success"])
	assert(edit_result["changed"] == true)
	assert(edit_result["verified_write"] == true)
	assert(edit_result["undoable"] == false)

	var reread = (
		script_tools.get_script_content_from_request(
			{"script_path": SCRATCH_SCRIPT}
		)
	)
	assert(reread["source"] == new_content)

	# 6. edit_script: parse gate leaves the previous content.
	var broken_edit = (
		script_tools.edit_script_from_request(
			{
				"script_path": SCRATCH_SCRIPT,
				"content": BROKEN_CONTENT
			}
		)
	)
	assert(not broken_edit["success"])
	assert(broken_edit["error"].contains("does not parse"))

	var unchanged = (
		script_tools.get_script_content_from_request(
			{"script_path": SCRATCH_SCRIPT}
		)
	)
	assert(unchanged["source"] == new_content)

	# 7. replace_in_script: ambiguous anchor refused. Seed a
	# second occurrence of the anchor first via a valid edit.
	var doubled = (
		script_tools.edit_script_from_request(
			{
				"script_path": SCRATCH_SCRIPT,
				"content": (
					"extends Node\n\nvar probe_health := 42\n"
					+ "# probe_health marker\n"
				)
			}
		)
	)
	assert(doubled["success"])
	assert(doubled["changed"] == true)

	var ambiguous = (
		script_tools.replace_in_script_from_request(
			{
				"script_path": SCRATCH_SCRIPT,
				"old_string": "probe_health",
				"new_string": "other"
			}
		)
	)
	assert(not ambiguous["success"])
	assert(ambiguous["error"].contains("occurs"))
	assert(ambiguous["error"].contains("must be unique"))

	# Restore single-occurrence content for the following cases.
	var undoubled = (
		script_tools.edit_script_from_request(
			{
				"script_path": SCRATCH_SCRIPT,
				"content": (
					"extends Node\n\nvar probe_health := 42\n"
				)
			}
		)
	)
	assert(undoubled["success"])

	# 8. replace_in_script: zero occurrences with the replacement
	# already present is an already-applied no-op.
	var already = (
		script_tools.replace_in_script_from_request(
			{
				"script_path": SCRATCH_SCRIPT,
				"old_string": "nonexistent_anchor",
				"new_string": "probe_health"
			}
		)
	)
	assert(already["success"])
	assert(already["changed"] == false)

	# 9. replace_in_script: zero occurrences, replacement absent ->
	# structured not-found failure.
	var not_found = (
		script_tools.replace_in_script_from_request(
			{
				"script_path": SCRATCH_SCRIPT,
				"old_string": "nonexistent_anchor",
				"new_string": "other_value"
			}
		)
	)
	assert(not not_found["success"])
	assert(not_found["error"].contains("old_string not found"))

	# 10. replace_in_script: successful anchored edit (unique
	# anchor) with parse gate and verification.
	var replace_result = (
		script_tools.replace_in_script_from_request(
			{
				"script_path": SCRATCH_SCRIPT,
				"old_string": "var probe_health := 42",
				"new_string": "var probe_health := 99"
			}
		)
	)
	assert(replace_result["success"])
	assert(replace_result["changed"] == true)
	assert(replace_result["parse_ok"] == true)
	assert(replace_result["verified_write"] == true)

	var replaced_read = (
		script_tools.get_script_content_from_request(
			{"script_path": SCRATCH_SCRIPT}
		)
	)
	assert(replaced_read["source"].contains("probe_health := 99"))

	# 11. replace_in_script: a replacement that would break the
	# parse is refused and the file is untouched.
	var broken_replace = (
		script_tools.replace_in_script_from_request(
			{
				"script_path": SCRATCH_SCRIPT,
				"old_string": "var probe_health := 99",
				"new_string": "var probe_health := ("
			}
		)
	)
	assert(not broken_replace["success"])
	assert(broken_replace["error"].contains("does not parse"))

	var still_intact = (
		script_tools.get_script_content_from_request(
			{"script_path": SCRATCH_SCRIPT}
		)
	)
	assert(still_intact["source"].contains("probe_health := 99"))

	# 12. JSON-serializable results.
	var serialized := JSON.stringify(replace_result)
	assert(not serialized.is_empty())


func _run_paging_cases() -> void:
	# Seed a 13-line script (1: extends, 2: blank,
	# 3..13: probes) with no trailing newline so line
	# arithmetic is unambiguous.
	var content := "extends Node\n\n"
	for line_index in range(2, 13):
		content += "var probe_line_%d := %d\n" % [line_index, line_index]
	content = content.strip_edges(false, true)

	_raw_write(SCRATCH_PAGING, content)

	var total_lines := 13

	# 1. Unpaged read keeps the historical shape: full
	# source, total_lines reported.
	var full = script_tools.get_script_content_from_request(
		{"script_path": SCRATCH_PAGING}
	)
	assert(full["success"])
	assert(full["source"] == content)
	assert(full["total_lines"] == total_lines)
	assert(full.get("truncated", false) == false)

	# 2. Paged read returns exactly the requested lines
	# and reports the window plus truncation.
	var page = script_tools.get_script_content_from_request(
		{
			"script_path": SCRATCH_PAGING,
			"start_line": 3,
			"line_count": 2,
		}
	)
	assert(page["success"])
	assert(page["source"] == "var probe_line_2 := 2\nvar probe_line_3 := 3")
	assert(page["start_line"] == 3)
	assert(page["end_line"] == 4)
	assert(page["total_lines"] == total_lines)
	assert(page["truncated"] == true)

	# 3. A page covering the tail is not truncated.
	var tail = script_tools.get_script_content_from_request(
		{
			"script_path": SCRATCH_PAGING,
			"start_line": 10,
			"line_count": 500,
		}
	)
	assert(tail["success"])
	assert(tail["source"] == "var probe_line_9 := 9\nvar probe_line_10 := 10\nvar probe_line_11 := 11\nvar probe_line_12 := 12")
	assert(tail["end_line"] == total_lines)
	assert(tail["truncated"] == false)

	# 4. A start beyond EOF is an empty page, not an error.
	var beyond = script_tools.get_script_content_from_request(
		{
			"script_path": SCRATCH_PAGING,
			"start_line": 100,
			"line_count": 5,
		}
	)
	assert(beyond["success"])
	assert(beyond["source"] == "")

	# 5. Validation: bad bounds are structured failures.
	var bad_count = script_tools.get_script_content_from_request(
		{
			"script_path": SCRATCH_PAGING,
			"start_line": 1,
			"line_count": 501,
		}
	)
	assert(bad_count["success"] == false)

	var bad_start = script_tools.get_script_content_from_request(
		{
			"script_path": SCRATCH_PAGING,
			"start_line": 0,
			"line_count": 5,
		}
	)
	assert(bad_start["success"] == false)

	var missing_count = script_tools.get_script_content_from_request(
		{"script_path": SCRATCH_PAGING, "start_line": 2}
	)
	assert(missing_count["success"] == false)

	_remove_file(SCRATCH_PAGING)

	print("script content paging cases passed")


func _run_root_hint_cases() -> void:
	# 1. A script in the project root is legal but flags
	# root_directory_hint with an explanatory message.
	var root_probe := "res://scratch_root_probe.gd"

	var root_create = script_tools.create_script_from_request(
		{
			"script_path": root_probe,
			"content": VALID_CONTENT,
		}
	)
	assert(root_create["success"])
	assert(root_create["root_directory_hint"] == true)
	assert(root_create["message"].contains("project root"))

	var root_dir := DirAccess.open("res://")
	assert(root_dir != null)
	assert(root_dir.remove("scratch_root_probe.gd") == OK)
	assert(not FileAccess.file_exists(root_probe))

	# 2. A script inside a project folder does not flag.
	# (Earlier cases may have left this file behind; the
	# create-only contract would otherwise refuse it.)
	_remove_file(SCRATCH_SCRIPT)

	var nested = script_tools.create_script_from_request(
		{
			"script_path": SCRATCH_SCRIPT,
			"content": VALID_CONTENT,
		}
	)
	assert(nested["success"])
	assert(nested["root_directory_hint"] == false)

	_remove_file(SCRATCH_SCRIPT)

	print("create_script root hint cases passed")


func _run_undo_capable_cases(undo_manager) -> void:
	# 13. create_script: parse-gated write with verification.
	var create_result = (
		script_tools.create_script_from_request(
			{"script_path": SCRATCH_SCRIPT, "content": VALID_CONTENT}
		)
	)
	assert(create_result["success"])
	assert(create_result["action"] == "create_script")
	assert(create_result["changed"] == true)
	assert(create_result["parse_ok"] == true)
	assert(create_result["verified_write"] == true)
	assert(create_result["undoable"] == false)
	assert(FileAccess.file_exists(SCRATCH_SCRIPT))

	# 14. get_script_content: roundtrip equals what was written.
	var read_result = (
		script_tools.get_script_content_from_request(
			{"script_path": SCRATCH_SCRIPT}
		)
	)
	assert(read_result["success"])
	assert(read_result["source"] == VALID_CONTENT)
	assert(read_result["line_count"] == VALID_CONTENT.count("\n") + 1)

	# 15. diagnostics: the created script parses cleanly.
	var diag_ok = (
		script_tools.list_script_diagnostics_from_request(
			{"script_path": SCRATCH_SCRIPT}
		)
	)
	assert(diag_ok["success"])
	assert(diag_ok["parse_ok"] == true)
	assert(diag_ok["error"] == "")

	# 16. diagnostics: a broken script reports parse_ok false with
	# the Godot error code (written via the raw API because the
	# parse gate refuses broken content).
	_raw_write(SCRATCH_BAD, BROKEN_CONTENT)
	var diag_bad = (
		script_tools.list_script_diagnostics_from_request(
			{"script_path": SCRATCH_BAD}
		)
	)
	assert(diag_bad["success"])
	assert(diag_bad["parse_ok"] == false)
	assert(diag_bad["error"] != "")
	_remove_file(SCRATCH_BAD)

	# 17. attach_script: successful attach with verification.
	var attach_result = (
		script_tools.attach_script_from_request(
			{"node_path": "Alpha", "script_path": SCRATCH_SCRIPT}
		)
	)
	assert(attach_result["success"])
	assert(attach_result["action"] == "attach_script")
	assert(attach_result["changed"] == true)
	assert(attach_result["was_attached"] == false)
	assert(attach_result["is_attached"] == true)
	assert(attach_result["verified_attachment"] == true)
	assert(attach_result["undoable"] == true)
	assert(_attached("Alpha") == true)

	# 18. attach_script: idempotent re-attach of the same script.
	var idempotent_attach = (
		script_tools.attach_script_from_request(
			{"node_path": "Alpha", "script_path": SCRATCH_SCRIPT}
		)
	)
	assert(idempotent_attach["success"])
	assert(idempotent_attach["changed"] == false)
	assert(idempotent_attach["was_attached"] == true)
	assert(idempotent_attach["verified_attachment"] == true)
	assert(idempotent_attach["undoable"] == false)

	# 19. attach_script: deterministic refusal when a DIFFERENT
	# script is already attached.
	var create_second = (
		script_tools.create_script_from_request(
			{"script_path": SCRATCH_SCRIPT_2, "content": VALID_CONTENT_2}
		)
	)
	assert(create_second["success"])

	var attach_different = (
		script_tools.attach_script_from_request(
			{"node_path": "Alpha", "script_path": SCRATCH_SCRIPT_2}
		)
	)
	assert(not attach_different["success"])
	assert(attach_different["error"].contains("different script"))
	assert(attach_different["error"].contains("detach_script first"))

	# 20. detach_script: successful detach with verification.
	var detach_result = (
		script_tools.detach_script_from_request(
			{"node_path": "Alpha"}
		)
	)
	assert(detach_result["success"])
	assert(detach_result["action"] == "detach_script")
	assert(detach_result["changed"] == true)
	assert(detach_result["was_attached"] == true)
	assert(detach_result["is_attached"] == false)
	assert(detach_result["verified_attachment"] == true)
	assert(detach_result["undoable"] == true)
	assert(detach_result["detached_script"] == SCRATCH_SCRIPT)
	assert(_attached("Alpha") == false)

	# 21. detach_script: idempotent re-detach.
	var idempotent_detach2 = (
		script_tools.detach_script_from_request(
			{"node_path": "Alpha"}
		)
	)
	assert(idempotent_detach2["success"])
	assert(idempotent_detach2["changed"] == false)
	assert(idempotent_detach2["verified_attachment"] == true)
	assert(idempotent_detach2["undoable"] == false)

	# 22. Undo the detach (step 20) through the existing Godot undo
	# system: undo must restore the script attachment.
	var history_id: int = undo_manager.get_object_history_id(
		root_node
	)
	var history = undo_manager.get_history_undo_redo(
		history_id
	)

	history.undo()
	assert(_attached("Alpha") == true)

	history.redo()
	assert(_attached("Alpha") == false)

	history.undo()
	assert(_attached("Alpha") == true)

	# 23. JSON-serializable results.
	var serialized := JSON.stringify(detach_result)
	assert(not serialized.is_empty())
	assert(serialized.contains("verified_attachment"))

	var serialized_read := JSON.stringify(read_result)
	assert(not serialized_read.is_empty())


func _init() -> void:

	_build_scene()

	var scene_helpers = FakeSceneHelpers.new(root_node)

	script_tools = AIAgentScriptToolsScript.new(
		scene_helpers,
		null
	)

	# Scratch files from a crashed earlier run must not break
	# this run.
	_cleanup()

	_run_shared_validation_cases()

	# File-edit tools need no undo manager: exercise them in
	# every run. They seed their own scratch script and clean
	# up through _cleanup().
	_run_file_edit_cases()

	# get_script_content line paging: bounded reads for
	# large scripts. Needs no undo manager.
	_run_paging_cases()

	# create_script root-directory convention hint.
	_run_root_hint_cases()

	# If this binary allows instantiating the editor undo
	# manager, exercise the full create/attach/detach path,
	# idempotent cases, diagnostics, and undo/redo through the
	# existing Godot undo system.
	if ClassDB.can_instantiate("EditorUndoRedoManager"):
		var undo_manager = ClassDB.instantiate(
			"EditorUndoRedoManager"
		)
		if undo_manager != null:
			_remove_file(SCRATCH_SCRIPT)
			script_tools = AIAgentScriptToolsScript.new(
				scene_helpers,
				undo_manager
			)
			_build_scene()
			scene_helpers.scene_root = root_node
			_run_undo_capable_cases(undo_manager)
			print(
				"script tools undo/redo cases passed"
			)
		else:
			print(
				"script tools: EditorUndoRedoManager "
				+ "unavailable; undo/redo cases skipped"
			)
	else:
		print(
			"script tools: EditorUndoRedoManager not "
			+ "instantiable headless; undo/redo cases skipped"
		)

	# Self-cleaning: the harness must leave no scratch files
	# behind, on every code path.
	_cleanup()

	quit()
