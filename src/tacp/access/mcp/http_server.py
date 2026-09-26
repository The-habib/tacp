"""HTTP MCP server entry points for TACP."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from tacp.access.mcp.server import McpServer
    from tacp.control.auth import TokenService

from tacp.access.mcp.transports.streamable_http import (
    start_streamable_http_server,
)


def run_http_server(
    mcp_server: McpServer,
    host: str = "127.0.0.1",
    port: int = 8765,
    token_service: Optional[TokenService] = None,
    auth_required: bool = False,
) -> None:
    """Run synchronous Streamable HTTP MCP server loop."""
    httpd = start_streamable_http_server(
        mcp_server=mcp_server,
        host=host,
        port=port,
        token_service=token_service,
        auth_required=auth_required,
    )
    sys.stderr.write(f"[INFO] TACP Streamable HTTP MCP server listening at http://{host}:{port}/mcp\n")
    if auth_required:
        sys.stderr.write("[INFO] Bearer token authentication is ENABLED.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        sys.stderr.write("[INFO] TACP HTTP MCP server stopped.\n")
