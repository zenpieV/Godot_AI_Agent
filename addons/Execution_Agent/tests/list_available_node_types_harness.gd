extends SceneTree

const AIAgentNodeToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_node_tools.gd"
)


func _init() -> void:

	var node_tools = AIAgentNodeToolsScript.new(
		null,
		null
	)

	var node2d_result = (
		node_tools.list_available_node_types_from_request(
			{
				"inherits_from": "Node2D",
				"limit": 100
			}
		)
	)
	assert(node2d_result["success"])
	assert(node2d_result["node_types"].has("Node2D"))
	assert(node2d_result["node_types"].has("CharacterBody2D"))

	var name_result = (
		node_tools.list_available_node_types_from_request(
			{
				"name_contains": "characterbody2d"
			}
		)
	)
	assert(name_result["success"])
	assert(name_result["total_matches"] >= 1)
	assert(name_result["node_types"].has("CharacterBody2D"))

	var combined_result = (
		node_tools.list_available_node_types_from_request(
			{
				"inherits_from": "Node2D",
				"name_contains": "body",
				"limit": 100
			}
		)
	)
	assert(combined_result["success"])
	assert(combined_result["node_types"].has("CharacterBody2D"))

	var no_match_result = (
		node_tools.list_available_node_types_from_request(
			{
				"name_contains": "DefinitelyNotARealNodeType"
			}
		)
	)
	assert(no_match_result["success"])
	assert(no_match_result["total_matches"] == 0)
	assert(no_match_result["node_types"].is_empty())

	var invalid_filter_result = (
		node_tools.list_available_node_types_from_request(
			{
				"inherits_from": "DefinitelyNotARealClass"
			}
		)
	)
	assert(not invalid_filter_result["success"])

	var invalid_limit_result = (
		node_tools.list_available_node_types_from_request(
			{
				"limit": 101
			}
		)
	)
	assert(not invalid_limit_result["success"])

	var blank_name_filter_result = (
		node_tools.list_available_node_types_from_request(
			{
				"name_contains": "   "
			}
		)
	)
	assert(not blank_name_filter_result["success"])

	var validated_candidate = (
		node_tools.validate_node_type_from_request(
			{
				"node_type": "CharacterBody2D"
			}
		)
	)
	assert(validated_candidate["success"])
	assert(validated_candidate["valid"])

	print("list_available_node_types harness passed")
	quit()
