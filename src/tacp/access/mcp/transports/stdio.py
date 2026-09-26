"""Stdio Transport for local MCP clients."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, TextIO

if TYPE_CHECKING:
    from tacp.access.mcp.server import McpServer


def run_stdio_transport(
    mcp_server: McpServer,
    in_stream: Optional[TextIO] = None,
    out_stream: Optional[TextIO] = None,
) -> None:
    """Launch stdio MCP server loop."""
    mcp_server.run_stdio(reader=in_stream, writer=out_stream)
