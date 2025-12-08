"""
RBAC Integration Tests for EVA-MCP Server.
Tests user role retrieval from Cosmos DB and RBAC enforcement.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta

from eva_mcp.auth.rbac import (
    get_user_roles,
    clear_role_cache,
    set_role_cache_ttl,
    _role_cache
)


@pytest.fixture
def mock_settings():
    """Mock settings with test Cosmos DB configuration."""
    with patch("eva_mcp.auth.rbac.settings") as mock:
        mock.cosmos_db_connection_string = "AccountEndpoint=https://test.documents.azure.com:443/;AccountKey=test-key=="
        mock.cosmos_db_database = "eva-suite-db"
        yield mock


@pytest.fixture
async def clear_cache():
    """Clear role cache before each test."""
    _role_cache.clear()
    yield
    _role_cache.clear()


@pytest.mark.asyncio
async def test_get_user_roles_from_cosmos_db(mock_settings, clear_cache):
    """Test retrieving user roles from Cosmos DB."""
    user_doc = {
        "id": "user-123",
        "userId": "user-123",
        "email": "user@example.com",
        "roles": ["admin", "developer"],
        "tenantId": "tenant-abc"
    }
    
    with patch("eva_mcp.auth.rbac.CosmosClient") as mock_cosmos:
        # Mock Cosmos DB client
        mock_container = MagicMock()
        mock_container.query_items.return_value = [user_doc]
        
        mock_database = MagicMock()
        mock_database.get_container_client.return_value = mock_container
        
        mock_client = MagicMock()
        mock_client.get_database_client.return_value = mock_database
        
        mock_cosmos.from_connection_string.return_value = mock_client
        
        # Get user roles
        roles = await get_user_roles("user-123")
        
        assert roles == ["admin", "developer"]
        
        # Verify Cosmos DB query
        mock_container.query_items.assert_called_once()
        call_kwargs = mock_container.query_items.call_args[1]
        assert call_kwargs["query"] == "SELECT * FROM c WHERE c.userId = @userId"
        assert call_kwargs["parameters"] == [{"name": "@userId", "value": "user-123"}]


@pytest.mark.asyncio
async def test_get_user_roles_user_not_found(mock_settings, clear_cache):
    """Test handling of user not found in Cosmos DB."""
    with patch("eva_mcp.auth.rbac.CosmosClient") as mock_cosmos:
        mock_container = MagicMock()
        mock_container.query_items.return_value = []  # No user found
        
        mock_database = MagicMock()
        mock_database.get_container_client.return_value = mock_container
        
        mock_client = MagicMock()
        mock_client.get_database_client.return_value = mock_database
        
        mock_cosmos.from_connection_string.return_value = mock_client
        
        # Should return default role
        roles = await get_user_roles("unknown-user")
        
        assert roles == ["developer"]  # Default role


@pytest.mark.asyncio
async def test_get_user_roles_invalid_roles_format(mock_settings, clear_cache):
    """Test handling of invalid roles format in user document."""
    user_doc = {
        "id": "user-456",
        "userId": "user-456",
        "roles": "admin"  # Invalid: should be list, not string
    }
    
    with patch("eva_mcp.auth.rbac.CosmosClient") as mock_cosmos:
        mock_container = MagicMock()
        mock_container.query_items.return_value = [user_doc]
        
        mock_database = MagicMock()
        mock_database.get_container_client.return_value = mock_container
        
        mock_client = MagicMock()
        mock_client.get_database_client.return_value = mock_database
        
        mock_cosmos.from_connection_string.return_value = mock_client
        
        # Should return empty list for invalid format
        roles = await get_user_roles("user-456")
        
        assert roles == []


@pytest.mark.asyncio
async def test_get_user_roles_mixed_types_in_list(mock_settings, clear_cache):
    """Test handling of non-string values in roles list."""
    user_doc = {
        "id": "user-789",
        "userId": "user-789",
        "roles": ["admin", 123, None, "developer", True]
    }
    
    with patch("eva_mcp.auth.rbac.CosmosClient") as mock_cosmos:
        mock_container = MagicMock()
        mock_container.query_items.return_value = [user_doc]
        
        mock_database = MagicMock()
        mock_database.get_container_client.return_value = mock_container
        
        mock_client = MagicMock()
        mock_client.get_database_client.return_value = mock_database
        
        mock_cosmos.from_connection_string.return_value = mock_client
        
        # Should filter out non-string values
        roles = await get_user_roles("user-789")
        
        assert roles == ["admin", "developer"]


@pytest.mark.asyncio
async def test_get_user_roles_missing_roles_field(mock_settings, clear_cache):
    """Test handling of user document without roles field."""
    user_doc = {
        "id": "user-abc",
        "userId": "user-abc",
        "email": "user@example.com"
        # No 'roles' field
    }
    
    with patch("eva_mcp.auth.rbac.CosmosClient") as mock_cosmos:
        mock_container = MagicMock()
        mock_container.query_items.return_value = [user_doc]
        
        mock_database = MagicMock()
        mock_database.get_container_client.return_value = mock_container
        
        mock_client = MagicMock()
        mock_client.get_database_client.return_value = mock_database
        
        mock_cosmos.from_connection_string.return_value = mock_client
        
        # Should return empty list
        roles = await get_user_roles("user-abc")
        
        assert roles == []


@pytest.mark.asyncio
async def test_get_user_roles_cosmos_db_error(mock_settings, clear_cache):
    """Test handling of Cosmos DB query errors."""
    with patch("eva_mcp.auth.rbac.CosmosClient") as mock_cosmos:
        # Simulate connection error
        mock_cosmos.from_connection_string.side_effect = Exception("Connection failed")
        
        # Should return empty list on error (fail closed)
        roles = await get_user_roles("user-error")
        
        assert roles == []


@pytest.mark.asyncio
async def test_get_user_roles_no_cosmos_db_configured(clear_cache):
    """Test handling when Cosmos DB is not configured."""
    with patch("eva_mcp.auth.rbac.settings") as mock:
        mock.cosmos_db_connection_string = ""
        
        # Should return default role
        roles = await get_user_roles("user-123")
        
        assert roles == ["developer"]


@pytest.mark.asyncio
async def test_role_caching(mock_settings, clear_cache):
    """Test that user roles are cached."""
    user_doc = {
        "userId": "user-cache",
        "roles": ["admin"]
    }
    
    with patch("eva_mcp.auth.rbac.CosmosClient") as mock_cosmos:
        mock_container = MagicMock()
        mock_container.query_items.return_value = [user_doc]
        
        mock_database = MagicMock()
        mock_database.get_container_client.return_value = mock_container
        
        mock_client = MagicMock()
        mock_client.get_database_client.return_value = mock_database
        
        mock_cosmos.from_connection_string.return_value = mock_client
        
        # First call: should query Cosmos DB
        roles1 = await get_user_roles("user-cache")
        assert roles1 == ["admin"]
        assert mock_container.query_items.call_count == 1
        
        # Second call: should use cache
        roles2 = await get_user_roles("user-cache")
        assert roles2 == ["admin"]
        assert mock_container.query_items.call_count == 1  # No additional call


@pytest.mark.asyncio
async def test_role_cache_expiry(mock_settings, clear_cache):
    """Test that role cache expires after TTL."""
    # Set short TTL for testing
    await set_role_cache_ttl(1)  # 1 second
    
    user_doc = {
        "userId": "user-ttl",
        "roles": ["developer"]
    }
    
    with patch("eva_mcp.auth.rbac.CosmosClient") as mock_cosmos:
        mock_container = MagicMock()
        mock_container.query_items.return_value = [user_doc]
        
        mock_database = MagicMock()
        mock_database.get_container_client.return_value = mock_container
        
        mock_client = MagicMock()
        mock_client.get_database_client.return_value = mock_database
        
        mock_cosmos.from_connection_string.return_value = mock_client
        
        # First call: should query Cosmos DB
        roles1 = await get_user_roles("user-ttl")
        assert roles1 == ["developer"]
        assert mock_container.query_items.call_count == 1
        
        # Wait for cache expiry
        import asyncio
        await asyncio.sleep(1.1)
        
        # Second call: should query Cosmos DB again
        roles2 = await get_user_roles("user-ttl")
        assert roles2 == ["developer"]
        assert mock_container.query_items.call_count == 2


@pytest.mark.asyncio
async def test_clear_role_cache_single_user(mock_settings, clear_cache):
    """Test clearing cache for specific user."""
    # Manually set cache
    _role_cache.set("user-1", ["admin"])
    _role_cache.set("user-2", ["developer"])
    
    # Clear cache for user-1
    await clear_role_cache("user-1")
    
    # user-1 should be cleared, user-2 should remain
    assert _role_cache.get("user-1") is None
    assert _role_cache.get("user-2") == ["developer"]


@pytest.mark.asyncio
async def test_clear_role_cache_all_users(mock_settings, clear_cache):
    """Test clearing cache for all users."""
    # Manually set cache
    _role_cache.set("user-1", ["admin"])
    _role_cache.set("user-2", ["developer"])
    
    # Clear all cache
    await clear_role_cache()
    
    # All users should be cleared
    assert _role_cache.get("user-1") is None
    assert _role_cache.get("user-2") is None


@pytest.mark.asyncio
async def test_set_role_cache_ttl(clear_cache):
    """Test updating role cache TTL."""
    await set_role_cache_ttl(300)  # 5 minutes
    
    assert _role_cache.ttl == timedelta(seconds=300)


@pytest.mark.asyncio
async def test_rbac_filtering_with_real_roles(mock_settings, clear_cache):
    """Test RBAC filtering with roles from Cosmos DB."""
    from eva_mcp.tools.registry import ToolRegistry
    
    # Mock user with only 'developer' role
    user_doc = {
        "userId": "dev-user",
        "roles": ["developer"]
    }
    
    with patch("eva_mcp.auth.rbac.CosmosClient") as mock_cosmos:
        mock_container = MagicMock()
        mock_container.query_items.return_value = [user_doc]
        
        mock_database = MagicMock()
        mock_database.get_container_client.return_value = mock_container
        
        mock_client = MagicMock()
        mock_client.get_database_client.return_value = mock_database
        
        mock_cosmos.from_connection_string.return_value = mock_client
        
        # Create registry with tools
        registry = ToolRegistry()
        await registry.load_tools()
        
        # Get accessible tools for developer user
        accessible_tools = await registry.get_tools_for_user("dev-user")
        
        # Developer should have access to:
        # - git_status (requires 'developer')
        # - cosmos_db_query (requires 'admin' or 'developer')
        # But NOT:
        # - azure_resource_list (requires 'admin' only)
        
        tool_names = [t.name for t in accessible_tools]
        assert "git_status" in tool_names
        assert "cosmos_db_query" in tool_names
        assert "azure_resource_list" not in tool_names


@pytest.mark.asyncio
async def test_rbac_blocking_unauthorized_access(mock_settings, clear_cache):
    """Test that users without required roles cannot access tools."""
    from eva_mcp.tools.registry import ToolRegistry
    
    # Mock user with no roles
    user_doc = {
        "userId": "no-role-user",
        "roles": []
    }
    
    with patch("eva_mcp.auth.rbac.CosmosClient") as mock_cosmos:
        mock_container = MagicMock()
        mock_container.query_items.return_value = [user_doc]
        
        mock_database = MagicMock()
        mock_database.get_container_client.return_value = mock_container
        
        mock_client = MagicMock()
        mock_client.get_database_client.return_value = mock_database
        
        mock_cosmos.from_connection_string.return_value = mock_client
        
        # Create registry
        registry = ToolRegistry()
        await registry.load_tools()
        
        # User should not be able to execute protected tools
        can_execute_git = await registry.user_can_execute("no-role-user", "git_status")
        can_execute_cosmos = await registry.user_can_execute("no-role-user", "cosmos_db_query")
        can_execute_azure = await registry.user_can_execute("no-role-user", "azure_resource_list")
        
        assert not can_execute_git
        assert not can_execute_cosmos
        assert not can_execute_azure
