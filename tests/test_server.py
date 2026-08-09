from mcp.server import MCPServer

from reaper_mcp.server import mcp


def test_server_uses_mcp_sdk_v2():
    assert isinstance(mcp, MCPServer)
