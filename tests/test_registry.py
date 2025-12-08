"""
Unit tests for tool registry.
"""

import pytest
from eva_mcp.tools.registry import ToolRegistry
from eva_mcp.tools.base import BaseTool
from pydantic import BaseModel


class MockToolInput(BaseModel):
    """Mock input schema for test tool."""
    value: str


class MockTool(BaseTool):
    """Mock tool for testing."""
    
    name = "mock_tool"
    description = "Mock tool for testing"
    input_schema = MockToolInput
    required_roles = ["test_role"]
    
    async def execute(self, args, user_id=None):
        return {"result": f"Executed with {args.value}"}


@pytest.mark.asyncio
async def test_registry_initialization():
    """Test registry initializes without errors."""
    registry = ToolRegistry()
    assert registry.tools == {}
    assert registry.tool_permissions == {}


@pytest.mark.asyncio
async def test_registry_loads_tools():
    """Test registry loads tools from tools/ directory."""
    registry = ToolRegistry()
    await registry.load_tools()
    
    # Should load 3 tools: cosmos_db_query, azure_resource_list, git_status
    assert len(registry.tools) == 3
    assert "cosmos_db_query" in registry.tools
    assert "azure_resource_list" in registry.tools
    assert "git_status" in registry.tools


@pytest.mark.asyncio
async def test_get_tool():
    """Test getting tool by name."""
    registry = ToolRegistry()
    await registry.load_tools()
    
    tool = registry.get_tool("git_status")
    assert tool is not None
    assert tool.name == "git_status"
    
    # Non-existent tool
    assert registry.get_tool("nonexistent") is None


@pytest.mark.asyncio
async def test_get_tools_for_anonymous_user():
    """Test anonymous users only get public tools."""
    registry = ToolRegistry()
    await registry.load_tools()
    
    # Anonymous user (user_id=None)
    tools = await registry.get_tools_for_user(None)
    
    # All current tools require roles, so anonymous users get none
    assert len(tools) == 0


@pytest.mark.asyncio
async def test_get_tools_for_authenticated_user():
    """Test authenticated users get tools based on roles."""
    registry = ToolRegistry()
    await registry.load_tools()
    
    # Authenticated user (Phase 1: all authenticated users get admin + developer)
    tools = await registry.get_tools_for_user("test-user")
    
    # Should get all 3 tools
    assert len(tools) == 3
    tool_names = {tool.name for tool in tools}
    assert "cosmos_db_query" in tool_names
    assert "azure_resource_list" in tool_names
    assert "git_status" in tool_names


@pytest.mark.asyncio
async def test_user_can_execute_public_tool():
    """Test anyone can execute public tools."""
    registry = ToolRegistry()
    
    # Manually register a public tool
    public_tool = MockTool()
    public_tool.required_roles = []
    registry.tools["public_tool"] = public_tool
    registry.tool_permissions["public_tool"] = []
    
    # Anonymous user can execute public tool
    assert await registry.user_can_execute(None, "public_tool") is True
    
    # Authenticated user can execute public tool
    assert await registry.user_can_execute("test-user", "public_tool") is True


@pytest.mark.asyncio
async def test_user_can_execute_protected_tool():
    """Test only users with roles can execute protected tools."""
    registry = ToolRegistry()
    await registry.load_tools()
    
    # Anonymous user cannot execute protected tools
    assert await registry.user_can_execute(None, "cosmos_db_query") is False
    assert await registry.user_can_execute(None, "git_status") is False
    
    # Authenticated user can execute (Phase 1: all get admin + developer roles)
    assert await registry.user_can_execute("test-user", "cosmos_db_query") is True
    assert await registry.user_can_execute("test-user", "git_status") is True


@pytest.mark.asyncio
async def test_user_can_execute_nonexistent_tool():
    """Test checking permissions for non-existent tool returns False."""
    registry = ToolRegistry()
    await registry.load_tools()
    
    assert await registry.user_can_execute("test-user", "nonexistent") is False


@pytest.mark.asyncio
async def test_registry_cleanup():
    """Test registry cleanup closes all tools."""
    registry = ToolRegistry()
    await registry.load_tools()
    
    # Cleanup should not raise errors
    await registry.close()
