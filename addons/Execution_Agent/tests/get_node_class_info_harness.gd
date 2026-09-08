extends SceneTree

const AIAgentNodeToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_node_tools.gd"
)


func _init() -> void:

	var node_tools = AIAgentNodeToolsScript.new(
		null,
		null
	)

	# 1. Valid instantiable class: Node2D
	var node2d_result = (
		node_tools.get_node_class_info_from_request(
			{
				"class_name": "Node2D"
			}
		)
	)
	assert(node2d_result["success"])
	assert(node2d_result["class_name"] == "Node2D")
	assert(node2d_result["base_class"] == "CanvasItem")
	assert(node2d_result["can_instantiate"] == true)

	# 2. Valid instantiable class: Node3D with correct base
	var node3d_result = (
		node_tools.get_node_class_info_from_request(
			{
				"class_name": "Node3D"
			}
		)
	)
	assert(node3d_result["success"])
	assert(node3d_result["class_name"] == "Node3D")
	assert(node3d_result["base_class"] == "Node")
	assert(node3d_result["can_instantiate"] == true)

	# 3. Valid non-instantiable class: CanvasItem
	var canvas_item_result = (
		node_tools.get_node_class_info_from_request(
			{
				"class_name": "CanvasItem"
			}
		)
	)
	assert(canvas_item_result["success"])
	assert(canvas_item_result["class_name"] == "CanvasItem")
	assert(canvas_item_result["base_class"] == "Node")
	assert(canvas_item_result["can_instantiate"] == false)

	# 4. Unknown class
	var unknown_result = (
		node_tools.get_node_class_info_from_request(
			{
				"class_name": "NotARealClass"
			}
		)
	)
	assert(not unknown_result["success"])
	assert(not unknown_result["error"].is_empty())

	# 5. Blank class name
	var blank_result = (
		node_tools.get_node_class_info_from_request(
			{
				"class_name": ""
			}
		)
	)
	assert(not blank_result["success"])
	assert(not blank_result["error"].is_empty())

	# 6. Whitespace-only class name
	var whitespace_result = (
		node_tools.get_node_class_info_from_request(
			{
				"class_name": "   "
			}
		)
	)
	assert(not whitespace_result["success"])
	assert(not whitespace_result["error"].is_empty())

	# 7. Missing class_name key
	var missing_result = (
		node_tools.get_node_class_info_from_request(
			{}
		)
	)
	assert(not missing_result["success"])
	assert(not missing_result["error"].is_empty())

	print("get_node_class_info harness passed")
	quit()
