#!/usr/bin/env python3
"""
Lab 5: HTTP Bridge — MCP Client

Connects to mcp_server.py as a proper MCP client (via SSE transport) and
re-exposes the tools as simple JSON HTTP endpoints so ui.html can call them.

Start order:
    Terminal 1: python3 labs/lab5-mcp/mcp_server.py --sse
    Terminal 2: python3 labs/lab5-mcp/http_bridge.py
    Browser:    open labs/lab5-mcp/ui.html

Architecture:
    ui.html  →(HTTP/JSON)→  http_bridge.py  →(MCP/SSE)→
    mcp_server.py  →  network_tools.py  →  mock_network_devices.py
"""

from __future__ import annotations

import json
from contextlib import AsyncExitStack

from mcp import ClientSession
from mcp.client.sse import sse_client
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
import uvicorn

MCP_SERVER_URL = "http://localhost:8000/sse"
BRIDGE_PORT = 8765

# MCP session kept alive for the duration of the bridge process
_session: ClientSession | None = None
_exit_stack: AsyncExitStack | None = None


# ── MCP connection ────────────────────────────────────────────────────────────

async def connect_to_mcp() -> None:
    global _session, _exit_stack
    _exit_stack = AsyncExitStack()
    read, write = await _exit_stack.enter_async_context(sse_client(MCP_SERVER_URL))
    _session = await _exit_stack.enter_async_context(ClientSession(read, write))
    await _session.initialize()
    tools = await _session.list_tools()
    names = [t.name for t in tools.tools]
    print(f"  Tools registered: {names}")


async def call_tool(name: str, args: dict) -> dict:
    """Call an MCP tool and return its result as a plain dict."""
    if _session is None:
        return {"error": "Not connected to MCP server"}
    try:
        result = await _session.call_tool(name, args)
        if result.content:
            text = getattr(result.content[0], "text", str(result.content[0]))
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"result": text}
        return {"error": "Tool returned no content"}
    except Exception as e:
        return {"error": str(e)}


# ── HTTP route handlers ───────────────────────────────────────────────────────

async def handle_devices(request: Request) -> JSONResponse:
    return JSONResponse(await call_tool("devices", {}))


async def handle_status(request: Request) -> JSONResponse:
    device = request.query_params.get("device", "")
    return JSONResponse(await call_tool("device_status", {"device": device}))


async def handle_bgp(request: Request) -> JSONResponse:
    device = request.query_params.get("device", "")
    return JSONResponse(await call_tool("bgp_summary", {"device": device}))


async def handle_interface(request: Request) -> JSONResponse:
    device = request.query_params.get("device", "")
    args: dict = {"device": device}
    interface = request.query_params.get("interface")
    if interface:
        args["interface"] = interface
    return JSONResponse(await call_tool("interface_status", args))


async def handle_ping(request: Request) -> JSONResponse:
    target = request.query_params.get("target", "")
    count = int(request.query_params.get("count", 4))
    return JSONResponse(await call_tool("ping", {"target": target, "count": count}))


async def handle_command(request: Request) -> JSONResponse:
    device = request.query_params.get("device", "")
    command = request.query_params.get("command", "")
    return JSONResponse(await call_tool("show_command", {"device": device, "command": command}))


async def handle_topology(request: Request) -> JSONResponse:
    return JSONResponse(await call_tool("topology", {}))


# ── App lifespan (connect/disconnect MCP session) ─────────────────────────────

async def lifespan(app: Starlette):
    print(f"\n🔌 Connecting to MCP server at {MCP_SERVER_URL} ...")
    try:
        await connect_to_mcp()
        print(f"✅ MCP session established")
        print(f"🌐 Bridge HTTP on http://localhost:{BRIDGE_PORT}")
        print(f"   Open labs/lab5-mcp/ui.html in your browser\n")
    except Exception as e:
        print(f"❌ Could not connect to MCP server: {e}")
        print(f"   Make sure mcp_server.py is running:")
        print(f"   python3 labs/lab5-mcp/mcp_server.py --sse\n")
    yield
    # Clean up MCP session on shutdown
    if _exit_stack:
        await _exit_stack.aclose()
        print("MCP session closed.")


# ── Starlette app ─────────────────────────────────────────────────────────────

app = Starlette(
    lifespan=lifespan,
    routes=[
        Route("/devices",   handle_devices),
        Route("/status",    handle_status),
        Route("/bgp",       handle_bgp),
        Route("/interface", handle_interface),
        Route("/ping",      handle_ping),
        Route("/command",   handle_command),
        Route("/topology",  handle_topology),
    ],
)

# Allow the browser to call this server from a local file (file://)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"])


if __name__ == "__main__":
    print("=" * 60)
    print("  Lab 5 — HTTP → MCP Bridge")
    print("=" * 60)
    print(f"  MCP server:  {MCP_SERVER_URL}")
    print(f"  Bridge HTTP: http://localhost:{BRIDGE_PORT}")
    print("=" * 60)
    uvicorn.run(app, host="localhost", port=BRIDGE_PORT, log_level="warning")
