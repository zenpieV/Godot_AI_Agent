@tool
extends EditorPlugin


const AIAgentEditorToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_editor_tools.gd"
)
const AIAgentScriptToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_script_tools.gd"
)
const AIAgentSceneFileToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_scene_file_tools.gd"
)
const AIAgentRuntimeToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_runtime_tools.gd"
)
const AIAgentDebuggerCaptureScript = preload(
	"res://addons/Execution_Agent/bridge/ai_agent_debugger_capture.gd"
)
const AIAgentRouterScript = preload(
	"res://addons/Execution_Agent/bridge/ai_agent_router.gd"
)


var tcp_server: TCPServer = TCPServer.new()

var undo_redo: EditorUndoRedoManager

var scene_helpers: AIAgentSceneHelpers
var variant_serializer: AIAgentVariantSerializer
var node_tools: AIAgentNodeTools
var property_tools: AIAgentPropertyTools
var editor_tools: RefCounted
var script_tools: AIAgentScriptTools
var scene_file_tools: AIAgentSceneFileTools
var runtime_tools: AIAgentRuntimeTools
var debugger_capture: AIAgentDebuggerCapture
var router: RefCounted
var http_bridge: AIAgentHTTP


# ==========================================
# Editor lifecycle
# ==========================================


func _enter_tree() -> void:

	undo_redo = get_undo_redo()

	initialize_modules()

	# Register the agent's debugger capture so
	# get_runtime_output can read what a game run via
	# run_scene actually prints and reports.

	add_debugger_plugin(debugger_capture)

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

	remove_debugger_plugin(debugger_capture)

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

	editor_tools = AIAgentEditorToolsScript.new(
		get_editor_interface(),
		undo_redo
	)

	script_tools = AIAgentScriptToolsScript.new(
		scene_helpers,
		undo_redo
	)

	scene_file_tools = AIAgentSceneFileToolsScript.new(
		scene_helpers,
		get_editor_interface(),
		undo_redo
	)

	# The debugger capture may already have been created
	# by _get_debugger_plugin() (the editor can query it
	# before this point); never replace a registered
	# instance.

	if debugger_capture == null:

		debugger_capture = (
			AIAgentDebuggerCaptureScript.new()
		)

	runtime_tools = AIAgentRuntimeToolsScript.new(
		get_editor_interface(),
		debugger_capture
	)

	router = AIAgentRouterScript.new(
		node_tools,
		property_tools,
		editor_tools,
		script_tools,
		scene_file_tools,
		runtime_tools
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
