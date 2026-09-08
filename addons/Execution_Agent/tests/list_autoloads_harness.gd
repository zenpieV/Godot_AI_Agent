extends SceneTree

const AIAgentEditorToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_editor_tools.gd"
)


func _init() -> void:

	var editor_tools = AIAgentEditorToolsScript.new(
		null,
		null
	)

	var initial_result := editor_tools.list_autoloads()
	assert(initial_result["success"])

	var first_key := "autoload/AgentTestFirst"
	var second_key := "autoload/AgentTestSecond"
	ProjectSettings.set_setting(
		first_key,
		"*res://game_scene.tscn"
	)
	ProjectSettings.set_setting(
		second_key,
		"res://game_scene.tscn"
	)

	var result := editor_tools.list_autoloads()
	assert(result["success"])
	assert(result["count"] == initial_result["count"] + 2)

	var autoloads: Array = result["autoloads"]
	var first_index := -1
	var second_index := -1

	for index in range(autoloads.size()):
		var entry: Dictionary = autoloads[index]
		if entry["name"] == "AgentTestFirst":
			first_index = index
			assert(entry["path"] == "res://game_scene.tscn")
			assert(entry["resource_target"] == "*res://game_scene.tscn")
		if entry["name"] == "AgentTestSecond":
			second_index = index
			assert(entry["path"] == "res://game_scene.tscn")
			assert(entry["resource_target"] == "res://game_scene.tscn")

	assert(first_index >= 0)
	assert(second_index >= 0)
	assert(first_index < second_index)
	assert(not JSON.stringify(result).is_empty())

	ProjectSettings.clear(first_key)
	ProjectSettings.clear(second_key)
	assert(not ProjectSettings.has_setting(first_key))
	assert(not ProjectSettings.has_setting(second_key))

	print("list_autoloads harness passed")
	quit()
