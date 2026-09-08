extends SceneTree

const AIAgentNodeToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_node_tools.gd"
)

const AIAgentSceneHelpersScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_scene_helpers.gd"
)

const PlayerFixtureScript = preload(
	"res://addons/Execution_Agent/tests/list_node_signals_custom_signal_fixture.gd"
)

const EnemyFixtureScript = preload(
	"res://addons/Execution_Agent/tests/find_nodes_by_script_enemy_fixture.gd"
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

	# Deterministic hierarchy mixing scripted and
	# unscripted nodes of different classes:
	# Root (Node, no script)
	#   PlayerA (Area2D,   player fixture script)
	#   PlayerB (Node2D,   player fixture script)
	#   Enemy   (Node,     enemy fixture script)
	#   Plain   (Node,     no script)
	var root_node := Node.new()
	root_node.name = "Root"

	var player_a := Area2D.new()
	player_a.name = "PlayerA"
	player_a.set_script(PlayerFixtureScript)

	var player_b := Node2D.new()
	player_b.name = "PlayerB"
	player_b.set_script(PlayerFixtureScript)

	var enemy := Node.new()
	enemy.name = "Enemy"
	enemy.set_script(EnemyFixtureScript)

	var plain := Node.new()
	plain.name = "Plain"

	root_node.add_child(player_a)
	root_node.add_child(player_b)
	root_node.add_child(enemy)
	root_node.add_child(plain)

	var scene_helpers = FakeSceneHelpers.new(root_node)

	var node_tools = AIAgentNodeToolsScript.new(
		scene_helpers,
		null
	)

	var player_path: String = (
		str(
			(PlayerFixtureScript as Script).resource_path
		)
	)

	var enemy_path: String = (
		str(
			(EnemyFixtureScript as Script).resource_path
		)
	)

	# Independent cross-check: read the real attached
	# scripts directly instead of trusting the tool.
	assert(str(player_a.get_script().resource_path) == player_path)
	assert(str(player_b.get_script().resource_path) == player_path)
	assert(str(enemy.get_script().resource_path) == enemy_path)
	assert(plain.get_script() == null)

	# 1. The player script returns exactly its two
	# nodes, with real paths/names/types, in the
	# same traversal order as find_nodes.
	var player_result = (
		node_tools.find_nodes_by_script_from_request(
			{"script_path": player_path}
		)
	)
	assert(player_result["success"])
	assert(player_result["action"] == "find_nodes_by_script")
	assert(player_result["script_path"] == player_path)
	assert(player_result["count"] == 2)
	assert(player_result["nodes"].size() == 2)

	var first = player_result["nodes"][0]
	var second = player_result["nodes"][1]
	assert(first["name"] == "PlayerA")
	assert(first["node_type"] == "Area2D")
	assert(first["path"] == "PlayerA")
	assert(first["is_root"] == false)
	assert(second["name"] == "PlayerB")
	assert(second["node_type"] == "Node2D")
	assert(second["path"] == "PlayerB")

	# 2. A different script returns only its own node.
	var enemy_result = (
		node_tools.find_nodes_by_script_from_request(
			{"script_path": enemy_path}
		)
	)
	assert(enemy_result["success"])
	assert(enemy_result["count"] == 1)
	assert(enemy_result["nodes"][0]["name"] == "Enemy")
	assert(enemy_result["nodes"][0]["node_type"] == "Node")

	# 3. Unscripted nodes and other scripts' nodes are
	# never mixed into the result.
	var enemy_names: Array = []
	for entry in enemy_result["nodes"]:
		enemy_names.append(entry["name"])
	assert(not enemy_names.has("PlayerA"))
	assert(not enemy_names.has("Plain"))

	# 4. A zero-match script is a success with count 0.
	var zero_result = (
		node_tools.find_nodes_by_script_from_request(
			{"script_path": "res://does/not/exist.gd"}
		)
	)
	assert(zero_result["success"])
	assert(zero_result["count"] == 0)
	assert(zero_result["nodes"] == [])

	# 5. A request without the res:// prefix is
	# normalized deterministically to the same
	# canonical path and the same result.
	var normalized_result = (
		node_tools.find_nodes_by_script_from_request(
			{
				"script_path": (
					player_path.substr(6)
				)
			}
		)
	)
	assert(normalized_result["success"])
	assert(normalized_result["script_path"] == player_path)
	assert(normalized_result == player_result)

	# 6. Invalid and missing script_path return the
	# structured validation errors.
	var blank_result = (
		node_tools.find_nodes_by_script_from_request(
			{"script_path": "   "}
		)
	)
	assert(not blank_result["success"])
	assert(not blank_result["error"].is_empty())

	var missing_key_result = (
		node_tools.find_nodes_by_script_from_request(
			{}
		)
	)
	assert(not missing_key_result["success"])
	assert(not missing_key_result["error"].is_empty())

	# 7. Determinism: a repeated call is byte-equivalent.
	var repeat_result = (
		node_tools.find_nodes_by_script_from_request(
			{"script_path": player_path}
		)
	)
	assert(repeat_result == player_result)

	# 8. The result is JSON-serializable.
	var serialized := JSON.stringify(player_result)
	assert(not serialized.is_empty())
	assert(serialized.contains("PlayerA"))

	print("find_nodes_by_script harness passed")
	quit()
