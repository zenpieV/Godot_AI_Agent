@tool
extends RefCounted

class_name AIAgentRouter


var node_tools: AIAgentNodeTools
var property_tools: AIAgentPropertyTools


func _init(
	p_node_tools: AIAgentNodeTools,
	p_property_tools: AIAgentPropertyTools
) -> void:

	node_tools = p_node_tools

	property_tools = p_property_tools


# ==========================================
# Request routing
# ==========================================


func route_request(
	method: String,
	path: String,
	body_text: String
) -> Dictionary:

	# ======================================
	# Route: /ping
	# ======================================

	if (
		method == "POST"
		and path == "/ping"
	):

		return {
			"success": true,
			"message": (
				"AI Agent editor bridge is running."
			)
		}

	# ======================================
	# Route: /scene_tree
	# ======================================

	if (
		method == "GET"
		and path == "/scene_tree"
	):

		return node_tools.get_scene_tree()


	# ======================================
	# Route: /find_nodes
	# ======================================

	if (
		method == "POST"
		and path == "/find_nodes"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"find_nodes_from_request"
		)

	# ======================================
	# Route: /validate_node_type
	# ======================================

	if (
		method == "POST"
		and path == "/validate_node_type"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"validate_node_type_from_request"
		)

	# ======================================
	# Route: /list_available_node_types
	# ======================================

	if (
		method == "POST"
		and path == "/list_available_node_types"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"list_available_node_types_from_request"
		)

	# ======================================
	# Route: /get_node_properties
	# ======================================

	if (
		method == "POST"
		and path == "/get_node_properties"
	):

		return _handle_json_route(
			body_text,
			property_tools,
			"get_node_properties_from_request"
		)

	# ======================================
	# Route: /get_node_property
	# ======================================

	if (
		method == "POST"
		and path == "/get_node_property"
	):

		return _handle_json_route(
			body_text,
			property_tools,
			"get_node_property_from_request"
		)

	# ======================================
	# Route: /set_properties
	# ======================================

	if (
		method == "POST"
		and path == "/set_properties"
	):

		return _handle_json_route(
			body_text,
			property_tools,
			"set_properties_from_request"
		)

	# ======================================
	# Route: /create_node
	# ======================================

	if (
		method == "POST"
		and path == "/create_node"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"create_node_from_request"
		)

	# ======================================
	# Route: /rename_node
	# ======================================

	if (
		method == "POST"
		and path == "/rename_node"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"rename_node_from_request"
		)

	# ======================================
	# Route: /delete_node
	# ======================================

	if (
		method == "POST"
		and path == "/delete_node"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"delete_node_from_request"
		)

	# ======================================
	# Route: /reparent_node
	# ======================================

	if (
		method == "POST"
		and path == "/reparent_node"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"reparent_node_from_request"
		)

	# ======================================
	# Route: /duplicate_node
	# ======================================

	if (
		method == "POST"
		and path == "/duplicate_node"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"duplicate_node_from_request"
		)

	# ======================================
	# Unknown route
	# ======================================

	return {
		"success": false,
		"error": (
			"Unknown endpoint: "
			+ method
			+ " "
			+ path
		)
	}


# ==========================================
# JSON route helper
# ==========================================


func _handle_json_route(
	body_text: String,
	target,
	method_name: String
) -> Dictionary:

	var parse_result := (
		parse_request_json(
			body_text
		)
	)

	if not parse_result["success"]:
		return parse_result

	return target.call(
		method_name,
		parse_result["data"]
	)


# ==========================================
# JSON parsing
# ==========================================


func parse_request_json(
	body_text: String
) -> Dictionary:

	var json := JSON.new()

	var parse_error := (
		json.parse(
			body_text
		)
	)

	if parse_error != OK:

		return {
			"success": false,
			"error": (
				"Invalid JSON request body."
			)
		}

	var data = (
		json.data
	)

	if not data is Dictionary:

		return {
			"success": false,
			"error": (
				"Request JSON must be an object."
			)
		}

	return {
		"success": true,
		"data": data
	}
