@tool
extends RefCounted

class_name AIAgentHTTP


var host_plugin: EditorPlugin
var router: AIAgentRouter


func _init(
	p_host_plugin: EditorPlugin,
	p_router: AIAgentRouter
) -> void:

	host_plugin = p_host_plugin

	router = p_router


# ==========================================
# Connection processing
# ==========================================


func handle_connection(
	peer: StreamPeerTCP
) -> void:

	print(
		"AI Agent received connection."
	)

	var wait_count := 0

	while (
		peer.get_available_bytes() == 0
		and wait_count < 100
	):

		await (
			host_plugin
			.get_tree()
			.process_frame
		)

		wait_count += 1

	if peer.get_available_bytes() == 0:

		peer.disconnect_from_host()

		return

	var request_data := (
		peer.get_data(
			peer.get_available_bytes()
		)
	)

	var request_text: String = (
		request_data[1]
		.get_string_from_utf8()
	)

	print(
		"AI Agent received request:"
	)

	print(
		request_text
	)

	var parsed_request := (
		parse_http_request(
			request_text
		)
	)

	if not parsed_request["success"]:

		await send_json_response(
			peer,
			parsed_request
		)

		return

	var response_data: Dictionary = (
	router.route_request(
		str(parsed_request["method"]),
		str(parsed_request["path"]),
		str(parsed_request["body"])
	)
	)

	await send_json_response(
		peer,
		response_data
	)


# ==========================================
# HTTP request parsing
# ==========================================


func parse_http_request(
	request_text: String
) -> Dictionary:

	var request_parts := (
		request_text.split(
			"\r\n\r\n",
			false,
			1
		)
	)

	if request_parts.is_empty():

		return {
			"success": false,
			"error": (
				"Invalid HTTP request."
			)
		}

	var headers_text: String = (
		request_parts[0]
	)

	var body_text := ""

	if request_parts.size() > 1:

		body_text = (
			request_parts[1]
		)

	var request_lines := (
		headers_text.split(
			"\r\n"
		)
	)

	if request_lines.is_empty():

		return {
			"success": false,
			"error": (
				"Invalid HTTP request line."
			)
		}

	var request_line_parts := (
		request_lines[0].split(
			" "
		)
	)

	if request_line_parts.size() < 2:

		return {
			"success": false,
			"error": (
				"Invalid HTTP request line."
			)
		}

	return {
		"success": true,
		"method": (
			request_line_parts[0]
		),
		"path": (
			request_line_parts[1]
		),
		"body": body_text
	}


# ==========================================
# HTTP response
# ==========================================


func send_json_response(
	peer: StreamPeerTCP,
	body_data: Dictionary
) -> void:

	var response_body := (
		JSON.stringify(
			body_data
		)
	)

	var response := (
		"HTTP/1.1 200 OK\r\n"
		+ "Content-Type: application/json\r\n"
		+ "Content-Length: "
		+ str(
			response_body
			.to_utf8_buffer()
			.size()
		)
		+ "\r\n"
		+ "Connection: close\r\n"
		+ "\r\n"
		+ response_body
	)

	peer.put_data(
		response
		.to_utf8_buffer()
	)

	await (
		host_plugin
		.get_tree()
		.process_frame
	)

	peer.disconnect_from_host()