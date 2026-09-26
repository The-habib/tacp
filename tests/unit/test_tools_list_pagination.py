"""Unit tests for tools/list pagination and category filtering."""

from pathlib import Path
from tacp.access.mcp.protocol import McpRequest
from tacp.access.mcp.server import create_mcp_server
from tacp.infrastructure.config import TacpConfig
from tacp.infrastructure.database import Database

def test_tools_list_pagination_and_filter(tmp_path):
    config = TacpConfig.load()
    db = Database(tmp_path / "mcp_test.db")
    db.connect()
    server = create_mcp_server(config, db)

    # 1. Full list
    req_all = McpRequest(id=1, method="tools/list", params={})
    resp_all = server.handle_request(req_all)
    all_tools = resp_all.result["tools"]
    assert len(all_tools) > 10

    # 2. Paginated (limit=5)
    req_p1 = McpRequest(id=2, method="tools/list", params={"limit": 5, "cursor": 0})
    resp_p1 = server.handle_request(req_p1)
    tools_p1 = resp_p1.result["tools"]
    assert len(tools_p1) == 5
    assert "nextCursor" in resp_p1.result
    assert resp_p1.result["nextCursor"] == "5"

    # 3. Next page (cursor=5, limit=5)
    req_p2 = McpRequest(id=3, method="tools/list", params={"limit": 5, "cursor": 5})
    resp_p2 = server.handle_request(req_p2)
    tools_p2 = resp_p2.result["tools"]
    assert len(tools_p2) == 5
    assert tools_p1[0]["name"] != tools_p2[0]["name"]

    # 4. Filter by category (e.g. 'patch' or 'system')
    req_filt = McpRequest(id=4, method="tools/list", params={"category": "system"})
    resp_filt = server.handle_request(req_filt)
    filt_tools = resp_filt.result["tools"]
    assert len(filt_tools) > 0
    assert all("system" in t["name"].lower() or "system" in t["description"].lower() for t in filt_tools)
