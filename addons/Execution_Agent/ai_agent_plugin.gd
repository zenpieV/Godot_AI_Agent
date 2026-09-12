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
const AIAgentRefactorToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_refactor_tools.gd"
)
const AIAgentStateStoreScript = preload(
	"res://addons/Execution_Agent/ui/ai_agent_state_store.gd"
)
const AIAgentPanelScript = preload(
	"res://addons/Execution_Agent/ui/ai_agent_panel.gd"
)
const AIAgentDebuggerCaptureScript = preload(
	"res://addons/Execution_Agent/bridge/ai_agent_debugger_capture.gd"
)
const AIAgentRouterScript = preload(
	"res://addons/Execution_Agent/bridge/ai_agent_router.gd"
)


var tcp_server: TCPServer = TCPServer.new()

# Single source of truth for the bridge port: the listener,
# the startup print, and the UI's POST target all use it.

const BRIDGE_PORT := 8081

var undo_redo: EditorUndoRedoManager

var scene_helpers: AIAgentSceneHelpers
var variant_serializer: AIAgentVariantSerializer
var node_tools: AIAgentNodeTools
var property_tools: AIAgentPropertyTools
var editor_tools: RefCounted
var script_tools: AIAgentScriptTools
var scene_file_tools: AIAgentSceneFileTools
var runtime_tools: AIAgentRuntimeTools
var refactor_tools: RefCounted
var state_store: RefCounted
var agent_panel  # AIAgentPanel (untyped: setup() is panel-specific)
var agent_panel_toggle: Button
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
		BRIDGE_PORT,
		"127.0.0.1"
	)

	if error == OK:

		print(
			"AI Agent editor plugin loaded."
		)

		print(
			"AI Agent editor bridge listening on "
			+ "http://127.0.0.1:%d" % BRIDGE_PORT
		)

	else:

		push_error(
			"Failed to start AI Agent editor bridge. "
			+ "Error code: "
			+ str(error)
		)


func _exit_tree() -> void:

	if agent_panel != null:

		remove_control_from_bottom_panel(
			agent_panel
		)

		agent_panel = null

	remove_debugger_plugin(debugger_capture)

	tcp_server.stop()

	print(
		"AI Agent editor plugin unloaded."
	)


# ==========================================
# Agent process lifecycle
# ==========================================


func _start_agent_process() -> bool:

	# Spawn the Python agent in bridge input mode as a
	# detached, console-less process driven by this
	# panel. The agent dir is expected beside the Godot
	# project root (res://Python_Agent).

	var agent_dir: String = (
		ProjectSettings.globalize_path("res://Python_Agent")
	)

	if not DirAccess.dir_exists_absolute(agent_dir):

		push_error(
			"AI Agent: could not find the Python_Agent "
			+ "directory at "
			+ agent_dir
			+ "; start the agent manually with "
			+ "'py -m agent.godot_agent'."
		)

		return false

	# The spawned process inherits this environment; the
	# bridge URL keeps the UI POSTs and the agent's polls
	# on the same listener even in throwaway copies.

	OS.set_environment("AGENT_INPUT_MODE", "bridge")

	OS.set_environment(
		"GODOT_BRIDGE_URL",
		"http://127.0.0.1:%d" % BRIDGE_PORT
	)

	var command := 'cd /d "%s" && py -m agent.godot_agent' % [
		agent_dir
	]

	# 4.7's create_process has no console-hiding flag: the
	# agent runs in a visible console window, which doubles
	# as its live log (closing it terminates the agent).

	var pid: int = OS.create_process(
		"cmd",
		["/c", command],
		false
	)

	if pid <= 0:

		push_error(
			"AI Agent: failed to spawn the agent process."
		)

		return false

	print(
		"AI Agent: agent process started (pid %d)."
		% pid
	)

	return true


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

	refactor_tools = AIAgentRefactorToolsScript.new(
		scene_helpers,
		get_editor_interface()
	)

	state_store = AIAgentStateStoreScript.new()

	state_store.bridge_port = BRIDGE_PORT

	router = AIAgentRouterScript.new(
		node_tools,
		property_tools,
		editor_tools,
		script_tools,
		scene_file_tools,
		runtime_tools,
		refactor_tools,
		state_store
	)

	http_bridge = AIAgentHTTP.new(
		self,
		router
	)

	# The observability bottom panel is the only UI
	# surface: chat input, model selector, timeline,
	# ledger. The status pill doubles as the Start
	# Session button while no agent process is running.

	agent_panel = AIAgentPanelScript.new()

	agent_panel.setup(
		state_store,
		Callable(self, "_start_agent_process")
	)

	agent_panel_toggle = add_control_to_bottom_panel(
		agent_panel,
		"AI Agent"
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
