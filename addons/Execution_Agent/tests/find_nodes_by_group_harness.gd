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

	# Deterministic hierarchy with real group state:
	# Root (Node, no groups)
	#   EnemyA  (Area2D, groups: enemies)
	#   EnemyB  (Area2D, groups: enemies, hostile)
	#   Boss    (Area2D, groups: hostile, bosses)
	#   Civilian(Node,   no groups)
	var root_node := Node.new()
	root_node.name = "Root"

	var enemy_a := Area2D.new()
	enemy_a.name = "EnemyA"

	var enemy_b := Area2D.new()
	enemy_b.name = "EnemyB"

	var boss := Area2D.new()
	boss.name = "Boss"

	var civilian := Node.new()
	civilian.name = "Civilian"

	root_node.add_child(enemy_a)
	root_node.add_child(enemy_b)
	root_node.add_child(boss)
	root_node.add_child(civilian)

	# Real Godot group assignments.
	enemy_a.add_to_group("enemies")
	enemy_b.add_to_group("enemies")
	enemy_b.add_to_group("hostile")
	boss.add_to_group("hostile")
	boss.add_to_group("bosses")

	var scene_helpers = FakeSceneHelpers.new(root_node)

	var node_tools = AIAgentNodeToolsScript.new(
		scene_helpers,
		null
	)

	# Independent cross-check with is_in_group():
	# the fixture must be what the harness expects
	# before the tool is exercised.
	assert(enemy_a.is_in_group("enemies"))
	assert(enemy_b.is_in_group("enemies"))
	assert(enemy_b.is_in_group("hostile"))
	assert(boss.is_in_group("hostile"))
	assert(boss.is_in_group("bosses"))
	assert(not civilian.is_in_group("enemies"))
	assert(not enemy_a.is_in_group("hostile"))

	# 1. A matching group returns exactly its members,
	# in find_nodes traversal order, with real
	# paths/names/types.
	var enemies_result = (
		node_tools.find_nodes_by_group_from_request(
			{"group_name": "enemies"}
		)
	)
	assert(enemies_result["success"])
	assert(enemies_result["action"] == "find_nodes_by_group")
	assert(enemies_result["group_name"] == "enemies")
	assert(enemies_result["count"] == 2)
	assert(enemies_result["nodes"].size() == 2)

	var first = enemies_result["nodes"][0]
	var second = enemies_result["nodes"][1]
	assert(first["name"] == "EnemyA")
	assert(first["node_type"] == "Area2D")
	assert(first["path"] == "EnemyA")
	assert(first["is_root"] == false)
	assert(second["name"] == "EnemyB")
	assert(second["node_type"] == "Area2D")

	# 2. Nodes in other groups are excluded; a node in
	# multiple groups appears for each of its groups.
	var hostile_result = (
		node_tools.find_nodes_by_group_from_request(
			{"group_name": "hostile"}
		)
	)
	assert(hostile_result["success"])
	assert(hostile_result["count"] == 2)
	assert(hostile_result["nodes"][0]["name"] == "EnemyB")
	assert(hostile_result["nodes"][1]["name"] == "Boss")

	var bosses_result = (
		node_tools.find_nodes_by_group_from_request(
			{"group_name": "bosses"}
		)
	)
	assert(bosses_result["success"])
	assert(bosses_result["count"] == 1)
	assert(bosses_result["nodes"][0]["name"] == "Boss")

	# 3. Un-grouped nodes are never returned.
	for entry in enemies_result["nodes"]:
		assert(entry["name"] != "Civilian")
		assert(entry["name"] != "Root")

	# 4. A zero-match group is a success with count 0.
	var zero_result = (
		node_tools.find_nodes_by_group_from_request(
			{"group_name": "nonexistent_group"}
		)
	)
	assert(zero_result["success"])
	assert(zero_result["count"] == 0)
	assert(zero_result["nodes"] == [])

	# 5. Exact, case-sensitive matching: "Enemies" and
	# "enemy" must not match the "enemies" group.
	var wrong_case = (
		node_tools.find_nodes_by_group_from_request(
			{"group_name": "Enemies"}
		)
	)
	assert(wrong_case["success"])
	assert(wrong_case["count"] == 0)

	var partial = (
		node_tools.find_nodes_by_group_from_request(
			{"group_name": "enemy"}
		)
	)
	assert(partial["success"])
	assert(partial["count"] == 0)

	# 6. Blank and missing group_name return the
	# structured validation errors.
	var blank_result = (
		node_tools.find_nodes_by_group_from_request(
			{"group_name": "   "}
		)
	)
	assert(not blank_result["success"])
	assert(not blank_result["error"].is_empty())

	var missing_key_result = (
		node_tools.find_nodes_by_group_from_request(
			{}
		)
	)
	assert(not missing_key_result["success"])
	assert(not missing_key_result["error"].is_empty())

	# 7. Determinism: a repeated call is byte-equivalent.
	var repeat_result = (
		node_tools.find_nodes_by_group_from_request(
			{"group_name": "enemies"}
		)
	)
	assert(repeat_result == enemies_result)

	# 8. The result is JSON-serializable.
	var serialized := JSON.stringify(enemies_result)
	assert(not serialized.is_empty())
	assert(serialized.contains("EnemyA"))

	print("find_nodes_by_group harness passed")
	quit()
