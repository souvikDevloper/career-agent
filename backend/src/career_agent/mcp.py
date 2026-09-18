"""Model Context Protocol server over Streamable HTTP.

Career Agent already exposes a registry of allowlisted, typed business tools to
its own voice agent. This serves that same registry to any MCP client, so a
judge can add the connector in their own client and drive the real system -
their calls create real operations, appear in the app's timeline, and are
subject to the same authorization as the in-app agent.

Two properties matter more than the protocol plumbing:

  * The owner comes from the JWT that API Gateway validated, never from the
    request body. An MCP client cannot name a user it is not signed in as.
  * Approval is not on this surface. Submitting an application is the one
    irreversible act in this product, and the guard on it is that a human said
    so in their own words - which a tool call from another model cannot
    evidence. Preparing is exposed; approving stays in the app, with the person.

Transport notes: JSON-RPC 2.0, one message per request. A request gets a
response; a notification gets 202 with no body. Tool failures are returned as
isError results rather than JSON-RPC errors, because the caller's model needs to
read them and try something else - a protocol error would just abort the turn.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from .agent import TOOL_NAMES, describe_tool

# Newest first. An unknown request version is answered with our newest rather
# than an error, which is what the spec asks of a server that cannot match.
SUPPORTED_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_INFO = {"name": "career-agent", "title": "Career Agent", "version": "1.0.0"}

INSTRUCTIONS = (
    "Career Agent finds openings, explains fit against the signed-in user's real resume, and prepares "
    "truthful application packets. Fit scores are this product's own explained rubric, not an employer's "
    "ATS score. Some results come from a clearly labelled test environment; say so when reporting them. "
    "Preparing an application never submits it - the user approves each submission in the Career Agent app."
)

# Deliberately not served over MCP; see the module docstring.
WITHHELD = {
    "approve_application": (
        "Approving a submission is not available over MCP. It is the one irreversible action here, and it "
        "requires the person to approve it themselves in the Career Agent app. Use prepare_application to "
        "get the packet ready for them to review."
    )
}

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def _error(msg_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _result(msg_id: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def tool_list() -> list[dict]:
    """The served surface, in registry order, minus anything withheld."""
    tools = []
    for name, fn in TOOL_NAMES.items():
        if name in WITHHELD:
            continue
        described = describe_tool(fn)
        tools.append({"name": described["name"], "description": described["description"],
                      "inputSchema": described["input_schema"]})
    return tools


def negotiate_version(requested: Any) -> str:
    return requested if requested in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0]


def dispatch(message: Any, call_tool: Callable[[str, dict], Any]) -> dict | None:
    """Handle one JSON-RPC message. Returns None for a notification.

    call_tool runs the named tool with the caller's arguments and is expected to
    raise on failure; the failure is reported to the client as an isError result.
    """
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, INVALID_REQUEST, "Expected a JSON-RPC 2.0 message")
    method = message.get("method")
    if not isinstance(method, str):
        return _error(message.get("id"), INVALID_REQUEST, "Missing method")
    params = message.get("params")
    params = params if isinstance(params, dict) else {}
    # A message with no id is a notification: act on it, answer nothing.
    is_notification = "id" not in message
    msg_id = message.get("id")

    if method == "initialize":
        if is_notification:
            return None
        return _result(msg_id, {
            "protocolVersion": negotiate_version(params.get("protocolVersion")),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": INSTRUCTIONS,
        })

    if method.startswith("notifications/"):
        return None  # initialized, cancelled, progress: nothing to send back

    if is_notification:
        return None

    if method == "ping":
        return _result(msg_id, {})

    if method == "tools/list":
        return _result(msg_id, {"tools": tool_list()})

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments")
        arguments = arguments if isinstance(arguments, dict) else {}
        if name in WITHHELD:
            return _result(msg_id, _tool_error(WITHHELD[name]))
        if name not in TOOL_NAMES:
            return _error(msg_id, INVALID_PARAMS, f"Unknown tool: {name}")
        try:
            output = call_tool(name, arguments)
        except TypeError as exc:  # wrong or missing arguments for this tool
            return _result(msg_id, _tool_error(f"Invalid arguments for {name}: {exc}"))
        except Exception as exc:
            return _result(msg_id, _tool_error(f"{type(exc).__name__}: {exc}"))
        return _result(msg_id, _tool_success(output))

    if method in ("resources/list", "prompts/list"):
        # Answer the shape rather than an error: clients probe these on connect,
        # and an error in the log looks like a broken server.
        return _result(msg_id, {"resources": []} if method.startswith("resources") else {"prompts": []})

    return _error(msg_id, METHOD_NOT_FOUND, f"Unknown method: {method}")


def _tool_success(output: Any) -> dict:
    text = json.dumps(output, default=str, ensure_ascii=False)
    result: dict[str, Any] = {"content": [{"type": "text", "text": text[:60000]}], "isError": False}
    if isinstance(output, dict):
        result["structuredContent"] = output
    return result


def _tool_error(message: str) -> dict:
    return {"content": [{"type": "text", "text": message[:2000]}], "isError": True}
