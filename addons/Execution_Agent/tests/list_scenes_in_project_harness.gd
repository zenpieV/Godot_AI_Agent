extends SceneTree

const AIAgentEditorToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_editor_tools.gd"
)


func _init() -> void:

	var editor_tools = AIAgentEditorToolsScript.new(
		null,
		null
	)
	var result := editor_tools.list_scenes_in_project()

	assert(not result["success"])
	assert(result["action"] == "list_scenes_in_project")
	assert(result["error"].contains("running Godot editor"))
	assert(not JSON.stringify(result).is_empty())

	print("list_scenes_in_project harness passed")
	quit()
