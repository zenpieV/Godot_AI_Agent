@tool
extends EditorPlugin


var tcp_server: TCPServer = TCPServer.new()

var undo_redo: EditorUndoRedoManager

var scene_helpers: AIAgentSceneHelpers
var variant_serializer: AIAgentVariantSerializer
var node_tools: AIAgentNodeTools
var property_tools: AIAgentPropertyTools
var router: AIAgentRouter
var http_bridge: AIAgentHTTP


# ==========================================
# Editor lifecycle
# ==========================================


func _enter_tree() -> void:

	undo_redo = get_undo_redo()

	initialize_modules()

	var error: int = tcp_server.listen(
		8081,
		"127.0.0.1"
	)

	if error == OK:

		print(
			"AI Agent editor plugin loaded."
		)

		print(
			"AI Agent editor bridge listening on "
			+ "http://127.0.0.1:8081"
		)

	else:

		push_error(
			"Failed to start AI Agent editor bridge. "
			+ "Error code: "
			+ str(error)
		)


func _exit_tree() -> void:

	tcp_server.stop()

	print(
		"AI Agent editor plugin unloaded."
	)


# ==========================================
# Module initialization
# ==========================================


func initialize_modules() -> void:

	scene_helpers = AIAgentSceneHelpers.new(
		get_editor_interface()
	)

	variant_serializer = (
		AIAgentVariantSerializer.new()
	)

	node_tools = AIAgentNodeTools.new(
		scene_helpers,
		undo_redo
	)

	property_tools = AIAgentPropertyTools.new(
		scene_helpers,
		variant_serializer,
		undo_redo
	)

	router = AIAgentRouter.new(
		node_tools,
		property_tools
	)

	http_bridge = AIAgentHTTP.new(
		self,
		router
	)


# ==========================================
# Connection processing
# ==========================================


func _process(
	_delta: float
) -> void:

	if tcp_server.is_connection_available():

		var peer: StreamPeerTCP = (
			tcp_server.take_connection()
		)

		http_bridge.handle_connection(
			peer
		)
