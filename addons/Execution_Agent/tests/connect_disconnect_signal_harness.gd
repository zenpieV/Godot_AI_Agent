extends SceneTree

const AIAgentNodeToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_node_tools.gd"
)

const AIAgentSceneHelpersScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_scene_helpers.gd"
)


# Stand-in scene helpers: identical to the pattern used by
# add_remove_group_harness.gd. The real helpers need an
# EditorInterface; only the edited-scene-root lookup is faked
# with a real, manually built Node tree.
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
var node_tools


func _build_scene() -> void:
	root_node = Node.new()
	root_node.name = "Root"

	for child_name in ["Alpha", "Beta", "Gamma"]:
		var child := Node.new()
		child.name = child_name
		root_node.add_child(child)


func _connected(
	source_path: String,
	signal_name: String,
	target_path: String,
	method_name: String
) -> bool:
	var source: Node = root_node.get_node(source_path)
	var target: Node = root_node.get_node(target_path)
	return source.is_connected(
		signal_name,
		Callable(target, method_name)
	)


func _run_shared_validation_cases() -> void:
	# 1. Missing fields.
	var missing_signal = (
		node_tools.connect_signal_from_request(
			{
				"node_path": "Alpha",
				"target_path": "Beta",
				"method_name": "queue_free"
			}
		)
	)
	assert(not missing_signal["success"])
	assert(missing_signal["error"].contains("requires signal_name"))

	var missing_target = (
		node_tools.connect_signal_from_request(
			{
				"node_path": "Alpha",
				"signal_name": "tree_entered",
				"method_name": "queue_free"
			}
		)
	)
	assert(not missing_target["success"])
	assert(missing_target["error"].contains("requires target_path"))

	var missing_method = (
		node_tools.connect_signal_from_request(
			{
				"node_path": "Alpha",
				"signal_name": "tree_entered",
				"target_path": "Beta"
			}
		)
	)
	assert(not missing_method["success"])
	assert(missing_method["error"].contains("requires method_name"))

	var missing_node = (
		node_tools.connect_signal_from_request(
			{
				"signal_name": "tree_entered",
				"target_path": "Beta",
				"method_name": "queue_free"
			}
		)
	)
	assert(not missing_node["success"])
	assert(missing_node["error"].contains("requires node_path"))

	# 2. Non-string field.
	var non_string = (
		node_tools.connect_signal_from_request(
			{
				"node_path": "Alpha",
				"signal_name": 5,
				"target_path": "Beta",
				"method_name": "queue_free"
			}
		)
	)
	assert(not non_string["success"])
	assert(non_string["error"].contains("must be a string"))

	# 3. Empty field.
	var empty_field = (
		node_tools.connect_signal_from_request(
			{
				"node_path": "Alpha",
				"signal_name": "   ",
				"target_path": "Beta",
				"method_name": "queue_free"
			}
		)
	)
	assert(not empty_field["success"])
	assert(empty_field["error"].contains("non-empty"))

	# 4. Missing emitter node.
	var ghost_emitter = (
		node_tools.connect_signal_from_request(
			{
				"node_path": "Ghost",
				"signal_name": "tree_entered",
				"target_path": "Beta",
				"method_name": "queue_free"
			}
		)
	)
	assert(not ghost_emitter["success"])
	assert(ghost_emitter["error"].contains("Node not found"))

	# 5. Missing target node.
	var ghost_target = (
		node_tools.connect_signal_from_request(
			{
				"node_path": "Alpha",
				"signal_name": "tree_entered",
				"target_path": "Ghost",
				"method_name": "queue_free"
			}
		)
	)
	assert(not ghost_target["success"])
	assert(ghost_target["error"].contains("Node not found"))

	# 6. Emitter has no such signal.
	var bad_signal = (
		node_tools.connect_signal_from_request(
			{
				"node_path": "Alpha",
				"signal_name": "nonexistent_signal",
				"target_path": "Beta",
				"method_name": "queue_free"
			}
		)
	)
	assert(not bad_signal["success"])
	assert(bad_signal["error"].contains("has no signal named"))

	# 7. Target has no such method.
	var bad_method = (
		node_tools.connect_signal_from_request(
			{
				"node_path": "Alpha",
				"signal_name": "tree_entered",
				"target_path": "Beta",
				"method_name": "nonexistent_method"
			}
		)
	)
	assert(not bad_method["success"])
	assert(bad_method["error"].contains("has no method named"))

	# 8. Non-boolean deferred.
	var bad_deferred = (
		node_tools.connect_signal_from_request(
			{
				"node_path": "Alpha",
				"signal_name": "tree_entered",
				"target_path": "Beta",
				"method_name": "queue_free",
				"deferred": "yes"
			}
		)
	)
	assert(not bad_deferred["success"])
	assert(bad_deferred["error"].contains("deferred must be a boolean"))

	# 9. disconnect_signal: missing fields and missing node.
	var disconnect_missing = (
		node_tools.disconnect_signal_from_request({})
	)
	assert(not disconnect_missing["success"])
	assert(disconnect_missing["error"].contains("requires signal_name"))

	var disconnect_ghost = (
		node_tools.disconnect_signal_from_request(
			{
				"node_path": "Ghost",
				"signal_name": "tree_entered",
				"target_path": "Beta",
				"method_name": "queue_free"
			}
		)
	)
	assert(not disconnect_ghost["success"])
	assert(disconnect_ghost["error"].contains("Node not found"))

	# 10. list_node_connections: missing and empty node_path.
	var listing_missing = (
		node_tools.list_node_connections_from_request({})
	)
	assert(not listing_missing["success"])
	assert(listing_missing["error"].contains("requires node_path"))

	var listing_empty = (
		node_tools.list_node_connections_from_request(
			{"node_path": "   "}
		)
	)
	assert(not listing_empty["success"])
	assert(listing_empty["error"].contains("non-empty"))

	var listing_ghost = (
		node_tools.list_node_connections_from_request(
			{"node_path": "Ghost"}
		)
	)
	assert(not listing_ghost["success"])
	assert(listing_ghost["error"].contains("Node not found"))


func _run_undo_capable_cases(undo_manager) -> void:
	# 11. Successful connect: Alpha.tree_entered -> Beta.queue_free.
	var connect_result = (
		node_tools.connect_signal_from_request(
			{
				"node_path": "Alpha",
				"signal_name": "tree_entered",
				"target_path": "Beta",
				"method_name": "queue_free"
			}
		)
	)
	assert(connect_result["success"])
	assert(connect_result["action"] == "connect_signal")
	assert(connect_result["changed"] == true)
	assert(connect_result["was_connected"] == false)
	assert(connect_result["is_connected"] == true)
	assert(connect_result["verified_connection"] == true)
	assert(connect_result["undoable"] == true)
	assert(
		_connected("Alpha", "tree_entered", "Beta", "queue_free")
		== true
	)

	# 12. Listing sees the outgoing connection, persistent and
	# not deferred.
	var alpha_listing = (
		node_tools.list_node_connections_from_request(
			{"node_path": "Alpha"}
		)
	)
	assert(alpha_listing["success"])
	assert(alpha_listing["total_outgoing"] == 1)
	assert(alpha_listing["outgoing"][0]["signal"] == "tree_entered")
	assert(alpha_listing["outgoing"][0]["target"] == "Beta")
	assert(alpha_listing["outgoing"][0]["method"] == "queue_free")
	assert(alpha_listing["outgoing"][0]["persistent"] == true)
	assert(alpha_listing["outgoing"][0]["deferred"] == false)
	assert(alpha_listing["total_incoming"] == 0)

	# 13. Listing sees the incoming connection from the target side.
	var beta_listing = (
		node_tools.list_node_connections_from_request(
			{"node_path": "Beta"}
		)
	)
	assert(beta_listing["success"])
	assert(beta_listing["total_incoming"] == 1)
	assert(beta_listing["incoming"][0]["signal"] == "tree_entered")
	assert(beta_listing["incoming"][0]["source"] == "Alpha")
	assert(beta_listing["incoming"][0]["method"] == "queue_free")
	assert(beta_listing["total_outgoing"] == 0)

	# 14. Idempotent connect: same pair again.
	var idempotent_connect = (
		node_tools.connect_signal_from_request(
			{
				"node_path": "Alpha",
				"signal_name": "tree_entered",
				"target_path": "Beta",
				"method_name": "queue_free"
			}
		)
	)
	assert(idempotent_connect["success"])
	assert(idempotent_connect["changed"] == false)
	assert(idempotent_connect["was_connected"] == true)
	assert(idempotent_connect["is_connected"] == true)
	assert(idempotent_connect["verified_connection"] == true)
	assert(idempotent_connect["undoable"] == false)

	# 15. Deferred connect on a second pair, then verify the flag
	# through the listing.
	var deferred_connect = (
		node_tools.connect_signal_from_request(
			{
				"node_path": "Alpha",
				"signal_name": "tree_exited",
				"target_path": "Gamma",
				"method_name": "queue_free",
				"deferred": true
			}
		)
	)
	assert(deferred_connect["success"])
	assert(deferred_connect["changed"] == true)
	assert(deferred_connect["deferred"] == true)
	assert(deferred_connect["verified_connection"] == true)

	var deferred_listing = (
		node_tools.list_node_connections_from_request(
			{"node_path": "Alpha"}
		)
	)
	assert(deferred_listing["total_outgoing"] == 2)
	for entry in deferred_listing["outgoing"]:
		if entry["signal"] == "tree_exited":
			assert(entry["deferred"] == true)
			assert(entry["persistent"] == true)

	# 16. Successful disconnect: Alpha.tree_entered from
	# Beta.queue_free.
	var disconnect_result = (
		node_tools.disconnect_signal_from_request(
			{
				"node_path": "Alpha",
				"signal_name": "tree_entered",
				"target_path": "Beta",
				"method_name": "queue_free"
			}
		)
	)
	assert(disconnect_result["success"])
	assert(disconnect_result["action"] == "disconnect_signal")
	assert(disconnect_result["changed"] == true)
	assert(disconnect_result["was_connected"] == true)
	assert(disconnect_result["is_connected"] == false)
	assert(disconnect_result["verified_connection"] == true)
	assert(disconnect_result["undoable"] == true)
	assert(
		_connected("Alpha", "tree_entered", "Beta", "queue_free")
		== false
	)

	# 17. Idempotent disconnect: pair no longer connected.
	var idempotent_disconnect = (
		node_tools.disconnect_signal_from_request(
			{
				"node_path": "Alpha",
				"signal_name": "tree_entered",
				"target_path": "Beta",
				"method_name": "queue_free"
			}
		)
	)
	assert(idempotent_disconnect["success"])
	assert(idempotent_disconnect["changed"] == false)
	assert(idempotent_disconnect["was_connected"] == false)
	assert(idempotent_disconnect["verified_connection"] == true)
	assert(idempotent_disconnect["undoable"] == false)

	# 18. Undo the disconnect (step 16) through the existing Godot
	# undo system: undo must restore the connection with its
	# original flags.
	var history_id: int = undo_manager.get_object_history_id(
		root_node
	)
	var history = undo_manager.get_history_undo_redo(
		history_id
	)

	history.undo()
	assert(
		_connected("Alpha", "tree_entered", "Beta", "queue_free")
		== true
	)

	history.redo()
	assert(
		_connected("Alpha", "tree_entered", "Beta", "queue_free")
		== false
	)

	history.undo()
	assert(
		_connected("Alpha", "tree_entered", "Beta", "queue_free")
		== true
	)

	# 19. JSON-serializable results.
	var serialized := JSON.stringify(disconnect_result)
	assert(not serialized.is_empty())
	assert(serialized.contains("verified_connection"))

	var serialized_listing := JSON.stringify(alpha_listing)
	assert(not serialized_listing.is_empty())


func _init() -> void:

	_build_scene()

	var scene_helpers = FakeSceneHelpers.new(root_node)

	node_tools = AIAgentNodeToolsScript.new(
		scene_helpers,
		null
	)

	_run_shared_validation_cases()

	# The editor undo manager is normally unavailable in a
	# headless SceneTree process: mutations must report an
	# explicit unavailable error instead of mutating without
	# undo support.

	var unavailable_connect = (
		node_tools.connect_signal_from_request(
			{
				"node_path": "Alpha",
				"signal_name": "tree_entered",
				"target_path": "Beta",
				"method_name": "queue_free"
			}
		)
	)
	assert(not unavailable_connect["success"])
	assert(
		unavailable_connect["error"].contains(
			"running Godot editor"
		)
	)

	# A disconnect of a pair that is NOT connected is a
	# deterministic idempotent no-op: it needs no undo
	# support, so it succeeds even without the undo
	# manager.

	var idempotent_headless_disconnect = (
		node_tools.disconnect_signal_from_request(
			{
				"node_path": "Alpha",
				"signal_name": "tree_exited",
				"target_path": "Gamma",
				"method_name": "queue_free"
			}
		)
	)
	assert(idempotent_headless_disconnect["success"])
	assert(idempotent_headless_disconnect["changed"] == false)
	assert(idempotent_headless_disconnect["undoable"] == false)

	# Removing an EXISTING connection, however, is a real
	# mutation: set one up through the raw Node API, then
	# require the explicit unavailable error.

	var pre_connected: bool = (
		root_node.get_node("Alpha").connect(
			"tree_exited",
			Callable(
				root_node.get_node("Beta"),
				"queue_free"
			)
		)
		== OK
	)
	assert(pre_connected)

	var unavailable_disconnect = (
		node_tools.disconnect_signal_from_request(
			{
				"node_path": "Alpha",
				"signal_name": "tree_exited",
				"target_path": "Beta",
				"method_name": "queue_free"
			}
		)
	)
	assert(not unavailable_disconnect["success"])
	assert(
		unavailable_disconnect["error"].contains(
			"running Godot editor"
		)
	)

	# Remove the raw connection again so later cases start
	# from a clean wiring state.

	root_node.get_node("Alpha").disconnect(
		"tree_exited",
		Callable(
			root_node.get_node("Beta"),
			"queue_free"
		)
	)

	# The read-only listing works without the undo manager.
	var headless_listing = (
		node_tools.list_node_connections_from_request(
			{"node_path": "Alpha"}
		)
	)
	assert(headless_listing["success"])
	assert(headless_listing["total_outgoing"] == 0)
	assert(headless_listing["total_incoming"] == 0)

	# If this binary allows instantiating the editor undo
	# manager, exercise the full connect/disconnect path,
	# idempotent cases, deferred connections, listing
	# verification, and undo/redo through the existing Godot
	# undo system.
	if ClassDB.can_instantiate("EditorUndoRedoManager"):
		var undo_manager = ClassDB.instantiate(
			"EditorUndoRedoManager"
		)
		if undo_manager != null:
			node_tools = AIAgentNodeToolsScript.new(
				scene_helpers,
				undo_manager
			)
			_build_scene()
			scene_helpers.scene_root = root_node
			_run_undo_capable_cases(undo_manager)
			print(
				"connect_signal/disconnect_signal undo/redo "
				+ "cases passed"
			)
		else:
			print(
				"connect_signal/disconnect_signal: "
				+ "EditorUndoRedoManager unavailable; "
				+ "undo/redo cases skipped"
			)
	else:
		print(
			"connect_signal/disconnect_signal: "
			+ "EditorUndoRedoManager not instantiable "
			+ "headless; undo/redo cases skipped"
		)

	quit()
