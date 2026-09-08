extends SceneTree

const AIAgentNodeToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_node_tools.gd"
)

const AIAgentSceneHelpersScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_scene_helpers.gd"
)


# Stand-in scene helpers: the real helpers need an
# EditorInterface, which does not exist in a headless
# harness. Node resolution logic is inherited unchanged;
# only the edited-scene-root lookup is faked with a real,
# manually built Node tree.
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


func _init() -> void:

	# Deterministic test hierarchy:
	# Root (Node)
	#   Level (Node2D)
	#     SpawnPoint (Node2D)
	#     SpawnPoint2 (Node2D)
	#     TriggerArea (Area2D)
	#   Enemies (Node2D)
	#     EnemyA (Area2D)
	#     EnemyB (Area2D)
	#     EnemyC (CharacterBody2D)
	var root_node := Node.new()
	root_node.name = "Root"

	var level := Node2D.new()
	level.name = "Level"

	var spawn_point := Node2D.new()
	spawn_point.name = "SpawnPoint"

	var spawn_point2 := Node2D.new()
	spawn_point2.name = "SpawnPoint2"

	var trigger_area := Area2D.new()
	trigger_area.name = "TriggerArea"

	var enemies := Node2D.new()
	enemies.name = "Enemies"

	var enemy_a := Area2D.new()
	enemy_a.name = "EnemyA"

	var enemy_b := Area2D.new()
	enemy_b.name = "EnemyB"

	var enemy_c := CharacterBody2D.new()
	enemy_c.name = "EnemyC"

	level.add_child(spawn_point)
	level.add_child(spawn_point2)
	level.add_child(trigger_area)
	enemies.add_child(enemy_a)
	enemies.add_child(enemy_b)
	enemies.add_child(enemy_c)
	root_node.add_child(level)
	root_node.add_child(enemies)

	var scene_helpers = FakeSceneHelpers.new(root_node)

	var node_tools = AIAgentNodeToolsScript.new(
		scene_helpers,
		null
	)

	# Independent reference traversal used to
	# cross-check counts against direct Godot
	# state instead of the implementation alone.
	var all_descendants: Array = []

	var stack: Array = []
	for top_child in root_node.get_children():
		stack.append(top_child)

	while not stack.is_empty():
		var current: Node = stack.pop_back()
		all_descendants.append(current)
		for child in current.get_children():
			stack.append(child)

	var no_filter = (
		node_tools.count_nodes_from_request({})
	)
	assert(no_filter["success"])
	assert(no_filter["action"] == "count_nodes")
	assert(no_filter["count"] == all_descendants.size())
	assert(no_filter["node_name_filter"] == "")
	assert(no_filter["name_match"] == "exact")

	var exact_result = (
		node_tools.count_nodes_from_request(
			{"node_name": "SpawnPoint"}
		)
	)
	assert(exact_result["success"])
	assert(exact_result["count"] == 1)

	var contains_result = (
		node_tools.count_nodes_from_request(
			{"node_name": "Enemy", "name_match": "contains"}
		)
	)
	assert(contains_result["success"])
	assert(contains_result["count"] == 3)

	var starts_result = (
		node_tools.count_nodes_from_request(
			{"node_name": "Spawn", "name_match": "starts_with"}
		)
	)
	assert(starts_result["success"])
	assert(starts_result["count"] == 2)

	var ends_result = (
		node_tools.count_nodes_from_request(
			{"node_name": "A", "name_match": "ends_with"}
		)
	)
	assert(ends_result["success"])
	assert(ends_result["count"] == 2)

	var type_result = (
		node_tools.count_nodes_from_request(
			{"node_type": "Area2D"}
		)
	)
	assert(type_result["success"])
	assert(type_result["count"] == 3)

	var parent_result = (
		node_tools.count_nodes_from_request(
			{"parent_path": "Level"}
		)
	)
	assert(parent_result["success"])
	# find_nodes semantics: the resolved parent itself
	# is considered (it is not the edited scene root),
	# so Level + its 3 descendants = 4.
	assert(parent_result["count"] == 4)
	assert(parent_result["parent_path_filter"] == "Level")

	_continue_harness(root_node, node_tools, all_descendants)


func _continue_harness(
	root_node: Node,
	node_tools,
	all_descendants: Array
) -> void:

	var combined_result = (
		node_tools.count_nodes_from_request(
			{
				"node_name": "Enemy",
				"node_type": "Area2D",
				"parent_path": "Enemies",
				"name_match": "starts_with"
			}
		)
	)
	assert(combined_result["success"])
	assert(combined_result["count"] == 2)

	var zero_result = (
		node_tools.count_nodes_from_request(
			{"node_name": "DoesNotExist"}
		)
	)
	assert(zero_result["success"])
	assert(zero_result["count"] == 0)

	var missing_parent = (
		node_tools.count_nodes_from_request(
			{"parent_path": "MissingLevel"}
		)
	)
	assert(not missing_parent["success"])
	assert(
		missing_parent["error"]
		== (
			"Parent node not found: MissingLevel. "
			+ "Node not found: MissingLevel"
		)
	)

	var root_result = (
		node_tools.count_nodes_from_request(
			{"parent_path": "."}
		)
	)
	assert(root_result["success"])
	assert(root_result["count"] == all_descendants.size())

	var same_type_result = (
		node_tools.count_nodes_from_request(
			{"node_type": "Node2D"}
		)
	)
	assert(same_type_result["success"])
	assert(same_type_result["count"] == 4)

	var invalid_mode = (
		node_tools.count_nodes_from_request(
			{"node_name": "Enemy", "name_match": "regex"}
		)
	)
	assert(not invalid_mode["success"])
	assert(invalid_mode["error"] == "Invalid name_match mode: regex")

	var repeat_result = (
		node_tools.count_nodes_from_request(
			{
				"node_name": "Enemy",
				"node_type": "Area2D",
				"parent_path": "Enemies",
				"name_match": "starts_with"
			}
		)
	)
	assert(repeat_result == combined_result)

	var serialized := JSON.stringify(repeat_result)
	assert(not serialized.is_empty())
	assert(not repeat_result.has("nodes"))

	print("count_nodes harness passed")
	quit()
