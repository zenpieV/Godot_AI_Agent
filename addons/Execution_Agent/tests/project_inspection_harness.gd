extends SceneTree

const AIAgentEditorToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_editor_tools.gd"
)


# Project-file inspection runs on plain DirAccess, so these
# tools work in a headless SceneTree process with both
# editor_interface and undo_redo set to null.
var editor_tools


func _run_cases() -> void:
	# 1. list_project_files: unbounded listing is structured,
	# sorted, limited, and excludes editor-internal directories.
	# The default limit (100) is far below this project's file
	# count, so a truncated flag must be present.
	var all_files = (
		editor_tools.list_project_files_from_request({})
	)
	assert(all_files["success"])
	assert(all_files["action"] == "list_project_files")
	assert(all_files["files"].size() == 100)
	assert(all_files["limit"] == 100)
	assert(all_files["truncated"] == true)
	assert(all_files["total_matches"] >= all_files["files"].size())

	var previous := ""

	for file_path in all_files["files"]:
		assert(file_path.begins_with("res://"))
		assert(file_path > previous)
		previous = file_path
		assert(not file_path.contains("/.godot/"))
		assert(not file_path.contains("/.git/"))
		assert(not file_path.contains(".."))

	# 2. list_project_files: prefix filter.
	var bridged = (
		editor_tools.list_project_files_from_request(
			{"prefix": "addons/Execution_Agent/bridge"}
		)
	)
	assert(bridged["success"])
	assert(bridged["files"].has(
		"res://addons/Execution_Agent/bridge/ai_agent_router.gd"
	))
	for file_path in bridged["files"]:
		assert(file_path.begins_with(
			"res://addons/Execution_Agent/bridge/"
		))

	# 3. list_project_files: extension filter.
	var gd_files = (
		editor_tools.list_project_files_from_request(
			{"prefix": "addons/Execution_Agent", "extensions": ["gd"]}
		)
	)
	assert(gd_files["success"])
	assert(gd_files["files"].size() > 0)
	for file_path in gd_files["files"]:
		assert(file_path.ends_with(".gd"))

	# 4. list_project_files: dot-prefixed extensions normalized,
	# yielding the same files as the plain extension filter over
	# the same prefix.
	var dot_files = (
		editor_tools.list_project_files_from_request(
			{"prefix": "addons/Execution_Agent/bridge", "extensions": [".gd"]}
		)
	)
	assert(dot_files["success"])
	assert(dot_files["extensions"] == ["gd"])

	var bridge_gd = (
		editor_tools.list_project_files_from_request(
			{"prefix": "addons/Execution_Agent/bridge", "extensions": ["gd"]}
		)
	)
	assert(bridge_gd["success"])
	assert(dot_files["files"] == bridge_gd["files"])

	# 5. list_project_files: limit and truncation flags.
	var limited = (
		editor_tools.list_project_files_from_request(
			{"limit": 2}
		)
	)
	assert(limited["success"])
	assert(limited["files"].size() == 2)
	assert(limited["limit"] == 2)
	assert(limited["truncated"] == true)

	var bad_limit = (
		editor_tools.list_project_files_from_request(
			{"limit": 501}
		)
	)
	assert(not bad_limit["success"])
	assert(bad_limit["error"].contains("between 1 and 500"))

	# 6. search_in_files: content search across scripts.
	var search = (
		editor_tools.search_in_files_from_request(
			{"query": "route_request", "extensions": ["gd"]}
		)
	)
	assert(search["success"])
	assert(search["total_matches"] >= 1)
	var hit_files := {}
	for match in search["matches"]:
		assert(not match["file_path"].contains("/.godot/"))
		assert(match["line_number"] >= 1)
		assert(not match["snippet"].is_empty())
		hit_files[match["file_path"]] = true
	assert(hit_files.has(
		"res://addons/Execution_Agent/bridge/ai_agent_router.gd"
	))

	# 7. search_in_files: bounded by limit.
	var limited_search = (
		editor_tools.search_in_files_from_request(
			{"query": "func", "extensions": ["gd"], "limit": 3}
		)
	)
	assert(limited_search["success"])
	assert(limited_search["matches"].size() <= 3)
	assert(limited_search["limit"] == 3)

	# 8. search_in_files: validation.
	var empty_query = (
		editor_tools.search_in_files_from_request(
			{"query": "   "}
		)
	)
	assert(not empty_query["success"])
	assert(empty_query["error"].contains("non-empty"))

	var bad_extension = (
		editor_tools.search_in_files_from_request(
			{"query": "x", "extensions": [5]}
		)
	)
	assert(not bad_extension["success"])
	assert(bad_extension["error"].contains("list of strings"))

	# 9. get_global_class_list: the plugin's classes are globals.
	var globals = (
		editor_tools.get_global_class_list_from_request({})
	)
	assert(globals["success"])
	assert(globals["class_count"] > 0)
	var global_names := {}
	for entry in globals["classes"]:
		assert(not entry["class_name"].is_empty())
		assert(entry["script_path"].begins_with("res://"))
		global_names[entry["class_name"]] = true
	assert(global_names.has("AIAgentNodeTools"))
	assert(global_names.has("AIAgentRouter"))

	# 10. get_input_map: built-in ui_* actions are present.
	var input_map = (
		editor_tools.get_input_map_from_request({})
	)
	assert(input_map["success"])
	assert(input_map["action_count"] > 0)
	var action_names := {}
	for entry in input_map["actions"]:
		assert(not entry["action"].is_empty())
		action_names[entry["action"]] = true
	assert(action_names.has("ui_accept"))
	assert(action_names.has("ui_cancel"))

	# 11. JSON-serializable results.
	assert(not JSON.stringify(search).is_empty())
	assert(not JSON.stringify(input_map).is_empty())


func _init() -> void:

	editor_tools = AIAgentEditorToolsScript.new(
		null,
		null
	)

	_run_cases()

	print("project inspection cases passed")

	quit()
