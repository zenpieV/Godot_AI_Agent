@tool
extends RefCounted

class_name AIAgentHTTP


# ==========================================
# HTTP layer (v2)
# ==========================================
# Framing contract:
#
# - Headers are read until the \r\n\r\n terminator; the
#   body is then read until exactly Content-Length bytes
#   have arrived, so multi-segment requests (large
#   edit_script bodies) are no longer truncated mid-read.
# - Hard caps: 64 KiB of headers, 10 MiB of body, and a
#   10 s wall-clock deadline per connection - a slow or
#   dead client can no longer hold a connection open
#   indefinitely (408), and oversized bodies are refused
#   (413) instead of silently consuming memory.
# - Status codes: 200 for handled requests (including
#   structured {success:false} failures - the body is the
#   contract), 400 for malformed HTTP/JSON, 404 for
#   unknown routes, 413/408 for the caps above. Handlers
#   may set "_http_status" in their result to override
#   the code; the key is stripped before serialization.
# - Responses are written in bounded chunks with status
#   checks between chunks, so a client that stops
#   reading cannot block the editor main thread
#   indefinitely.
#
# Wire compatibility: the JSON body shape is unchanged;
# the Python client treats non-2xx statuses as
# structured failures via the same body.


const MAX_HEADER_BYTES := 65536

const MAX_BODY_BYTES := 10485760

const REQUEST_DEADLINE_MS := 10000

const WRITE_CHUNK_BYTES := 65536


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

	var deadline: int = (
		Time.get_ticks_msec()
		+ REQUEST_DEADLINE_MS
	)

	var read_result := await _read_request(
		peer,
		deadline
	)

	if not read_result["ok"]:

		_send_json_response(
			peer,
			read_result["status"],
			read_result["response"]
		)

		await _close_peer(peer)

		return

	var request: Dictionary = read_result["request"]

	print(
		"AI Agent request: "
		+ str(request["method"])
		+ " "
		+ str(request["path"])
	)

	var response_data: Dictionary = (
		router.route_request(
			str(request["method"]),
			str(request["path"]),
			str(request["body"])
		)
	)

	var status := 200

	if response_data.has("_http_status"):

		status = int(response_data["_http_status"])

		response_data.erase("_http_status")

	_send_json_response(
		peer,
		status,
		response_data
	)

	await _close_peer(peer)


func _read_request(
	peer: StreamPeerTCP,
	deadline: int
) -> Dictionary:

	# Reads headers, then exactly Content-Length body
	# bytes. Returns {ok, request} on success or
	# {ok:false, status, response} with a structured
	# error body.

	var buffer := PackedByteArray()

	var header_end := -1

	while true:

		if Time.get_ticks_msec() > deadline:

			return _read_error(
				408,
				"Request timed out before "
				+ "completing."
			)

		if peer.get_status() != (
			StreamPeerTCP.STATUS_CONNECTED
		):

			if header_end == -1:

				return _read_error(
					400,
					"Client disconnected before "
					+ "the request was received."
				)

			break

		var available: int = (
			peer.get_available_bytes()
		)

		if available > 0:

			var chunk: Array = peer.get_data(
				available
			)

			if chunk[0] != OK:

				return _read_error(
					400,
					"Socket read error."
				)

			buffer.append_array(chunk[1])

			# Find the terminator BEFORE enforcing the
			# header cap: a large body merged into the
			# first segment must not count as header
			# bytes.

			if header_end == -1:

				header_end = (
					_find_header_terminator(buffer)
				)

			if (
				header_end == -1
				and buffer.size() > MAX_HEADER_BYTES
			):

				return _read_error(
					413,
					"Request headers exceed "
					+ str(MAX_HEADER_BYTES)
					+ " bytes."
				)

		if header_end == -1:

			await (
				host_plugin
				.get_tree()
				.process_frame
			)

			continue

		# Headers complete: parse them once, then keep
		# reading until exactly Content-Length body
		# bytes are buffered.

		var parsed := _parse_headers(
			buffer,
			header_end
		)

		if not parsed.get("ok", false):
			return parsed

		var content_length: int = (
			parsed["content_length"]
		)

		if content_length > MAX_BODY_BYTES:

			return _read_error(
				413,
				"Request body exceeds "
				+ str(MAX_BODY_BYTES)
				+ " bytes."
			)

		var body_start: int = header_end + 4

		var needed: int = (
			body_start + content_length
		)

		if buffer.size() >= needed:

			var body_bytes: PackedByteArray = (
				buffer.slice(
					body_start,
					needed
				)
			)

			return {
				"ok": true,
				"request": {
					"method": parsed["method"],
					"path": parsed["path"],
					"body": body_bytes
						.get_string_from_utf8(),
				},
			}

		await (
			host_plugin
			.get_tree()
			.process_frame
		)

	# Socket closed with headers but an incomplete body.

	return _read_error(
		400,
		"Client disconnected before the request "
		+ "body was complete."
	)


func _read_error(
	status: int,
	error: String
) -> Dictionary:

	return {
		"ok": false,
		"status": status,
		"response": {
			"success": false,
			"error": error,
		},
	}


func _find_header_terminator(
	buffer: PackedByteArray
) -> int:

	# Scans for \r\n\r\n; header buffers are capped at
	# 64 KiB so a full rescan per arrival stays cheap.

	if buffer.size() < 4:
		return -1

	var limit := buffer.size() - 3

	for index in range(limit):

		if (
			buffer[index] == 13
			and buffer[index + 1] == 10
			and buffer[index + 2] == 13
			and buffer[index + 3] == 10
		):
			return index

	return -1


func _parse_headers(
	buffer: PackedByteArray,
	header_end: int
) -> Dictionary:

	var header_text: String = buffer.slice(
		0,
		header_end
	).get_string_from_utf8()

	var lines := header_text.split("\r\n")

	if lines.is_empty():

		return _read_error(
			400,
			"Invalid HTTP request line."
		)

	var request_line_parts := lines[0].split(" ")

	if request_line_parts.size() < 2:

		return _read_error(
			400,
			"Invalid HTTP request line."
		)

	var content_length := 0

	for line_index in range(1, lines.size()):

		var line := lines[line_index]

		var colon := line.find(":")

		if colon == -1:
			continue

		var key := line.substr(0, colon)

		var value := line.substr(colon + 1)

		if key.strip_edges().to_lower() == (
			"content-length"
		):

			if not value.strip_edges().is_valid_int():

				return _read_error(
					400,
					"Invalid Content-Length header."
				)

			content_length = int(
				value.strip_edges()
			)

			if content_length < 0:

				return _read_error(
					400,
					"Invalid Content-Length header."
				)

	return {
		"ok": true,
		"method": request_line_parts[0],
		"path": request_line_parts[1],
		"content_length": content_length,
	}


# ==========================================
# HTTP response
# ==========================================


func _send_json_response(
	peer: StreamPeerTCP,
	status: int,
	body_data: Dictionary
) -> void:

	var response_body := JSON.stringify(
		body_data
	)

	var status_text := "OK"

	if status != 200:
		status_text = str(status)

	var response := (
		"HTTP/1.1 "
		+ str(status)
		+ " "
		+ status_text
		+ "\r\n"
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

	var payload: PackedByteArray = (
		response.to_utf8_buffer()
	)

	# Chunked write with status checks: a client that
	# stops reading can no longer block the editor main
	# thread indefinitely.

	var offset := 0

	while offset < payload.size():

		if peer.get_status() != (
			StreamPeerTCP.STATUS_CONNECTED
		):
			return

		var chunk_size: int = min(
			WRITE_CHUNK_BYTES,
			payload.size() - offset
		)

		peer.put_data(
			payload.slice(
				offset,
				offset + chunk_size
			)
		)

		offset += chunk_size


func _close_peer(peer: StreamPeerTCP) -> void:

	await (
		host_plugin
		.get_tree()
		.process_frame
	)

	peer.disconnect_from_host()
