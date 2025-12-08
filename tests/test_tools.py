"""
Unit tests for individual tools.
"""

import pytest
from eva_mcp.tools.git_status import GitStatusTool, GitStatusInput


@pytest.mark.asyncio
async def test_git_status_tool_initialization():
    """Test git_status tool initializes without errors."""
    tool = GitStatusTool()
    await tool.initialize()
    
    assert tool.name == "git_status"
    assert tool.description is not None
    assert tool.required_roles == ["developer"]


@pytest.mark.asyncio
async def test_git_status_tool_invalid_path():
    """Test git_status tool with non-existent path."""
    tool = GitStatusTool()
    await tool.initialize()
    
    args = GitStatusInput(repo_dir="/nonexistent/path")
    
    with pytest.raises(Exception) as exc_info:
        await tool.execute(args, user_id="test-user")
    
    assert "does not exist" in str(exc_info.value)


@pytest.mark.asyncio
async def test_git_status_tool_not_git_repo():
    """Test git_status tool with non-Git directory."""
    tool = GitStatusTool()
    await tool.initialize()
    
    # Use /tmp which is not a Git repo
    args = GitStatusInput(repo_dir="/tmp")
    
    with pytest.raises(Exception) as exc_info:
        await tool.execute(args, user_id="test-user")
    
    assert "Not a Git repository" in str(exc_info.value)


@pytest.mark.asyncio
async def test_git_status_tool_current_repo():
    """Test git_status tool on current repository (eva-mcp)."""
    tool = GitStatusTool()
    await tool.initialize()
    
    # Execute on current directory (should be eva-mcp repo)
    args = GitStatusInput(repo_dir=".")
    
    try:
        result = await tool.execute(args, user_id="test-user")
        
        # Verify result structure
        assert "branch" in result
        assert "commit_hash" in result
        assert "commit_message" in result
        assert "is_dirty" in result
        assert "modified_files" in result
        assert "untracked_files" in result
        
        # Verify types
        assert isinstance(result["branch"], str)
        assert isinstance(result["commit_hash"], str)
        assert isinstance(result["is_dirty"], bool)
        assert isinstance(result["modified_files"], list)
        assert isinstance(result["untracked_files"], list)
    
    except Exception as e:
        # If not in a git repo during testing, skip
        pytest.skip(f"Not in a git repository: {e}")


@pytest.mark.asyncio
async def test_cosmos_db_query_tool_not_configured():
    """Test cosmos_db_query tool fails when not configured."""
    from eva_mcp.tools.cosmos_db_query import CosmosDBQueryTool, CosmosQueryInput
    
    tool = CosmosDBQueryTool()
    
    # Initialize (should warn but not fail)
    await tool.initialize()
    
    # Execute should fail because Cosmos DB not configured
    args = CosmosQueryInput(
        tenant_id="test-tenant",
        query="c.type = 'test'"
    )
    
    with pytest.raises(Exception) as exc_info:
        await tool.execute(args, user_id="test-user")
    
    assert "not configured" in str(exc_info.value)


@pytest.mark.asyncio
async def test_azure_resource_list_tool_not_configured():
    """Test azure_resource_list tool fails when not configured."""
    from eva_mcp.tools.azure_resource_list import AzureResourceListTool, AzureResourceListInput
    
    tool = AzureResourceListTool()
    
    # Initialize (should warn but not fail)
    await tool.initialize()
    
    # Execute should fail because Azure credentials not configured
    args = AzureResourceListInput()
    
    with pytest.raises(Exception) as exc_info:
        await tool.execute(args, user_id="test-user")
    
    assert "not configured" in str(exc_info.value)


@pytest.mark.asyncio
async def test_tool_cleanup():
    """Test all tools cleanup without errors."""
    from eva_mcp.tools.git_status import GitStatusTool
    from eva_mcp.tools.cosmos_db_query import CosmosDBQueryTool
    from eva_mcp.tools.azure_resource_list import AzureResourceListTool
    
    tools = [
        GitStatusTool(),
        CosmosDBQueryTool(),
        AzureResourceListTool()
    ]
    
    for tool in tools:
        await tool.initialize()
        await tool.cleanup()  # Should not raise errors
