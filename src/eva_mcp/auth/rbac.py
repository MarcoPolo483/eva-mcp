"""
RBAC (Role-Based Access Control) for EVA-MCP Server.
Queries user roles from Cosmos DB and manages role caching.
"""

import logging
from typing import Optional
from datetime import datetime, timedelta

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

from eva_mcp.config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# Role Cache
# ============================================================================

class RoleCache:
    """
    In-memory cache for user roles with TTL.
    
    Reduces Cosmos DB queries for frequently accessed users.
    Default TTL: 10 minutes.
    """
    
    def __init__(self, ttl_seconds: int = 600):
        self.ttl = timedelta(seconds=ttl_seconds)
        self._cache: dict[str, tuple[list[str], datetime]] = {}
    
    def get(self, user_id: str) -> Optional[list[str]]:
        """Get cached roles for user if not expired."""
        if user_id in self._cache:
            roles, cached_at = self._cache[user_id]
            if datetime.utcnow() - cached_at < self.ttl:
                logger.debug(f"Role cache hit: {user_id} → {roles}")
                return roles
            else:
                # Expired
                del self._cache[user_id]
        return None
    
    def set(self, user_id: str, roles: list[str]) -> None:
        """Cache roles for user."""
        self._cache[user_id] = (roles, datetime.utcnow())
        logger.debug(f"Role cache set: {user_id} → {roles}")
    
    def clear(self, user_id: Optional[str] = None) -> None:
        """Clear cache for specific user or all users."""
        if user_id:
            self._cache.pop(user_id, None)
            logger.debug(f"Role cache cleared: {user_id}")
        else:
            self._cache.clear()
            logger.debug("Role cache cleared (all users)")


# ============================================================================
# Global Role Cache Instance
# ============================================================================

_role_cache = RoleCache(ttl_seconds=600)  # 10 minutes


# ============================================================================
# User Role Retrieval
# ============================================================================

async def get_user_roles(user_id: str) -> list[str]:
    """
    Get user roles from Cosmos DB.
    
    Queries the 'users' container in Cosmos DB for the user document
    and extracts the 'roles' array. Results are cached for 10 minutes.
    
    Args:
        user_id: User ID (from OAuth token 'sub' claim)
    
    Returns:
        List of role strings (e.g., ['admin', 'developer'])
        Returns empty list if user not found or roles not configured.
    
    Example user document in Cosmos DB:
    {
        "id": "user-123",
        "userId": "user-123",
        "email": "user@example.com",
        "roles": ["developer", "admin"],
        "tenantId": "tenant-abc"
    }
    """
    # Check cache first
    cached_roles = _role_cache.get(user_id)
    if cached_roles is not None:
        return cached_roles
    
    # Check if Cosmos DB is configured
    if not settings.cosmos_db_connection_string:
        logger.warning(
            f"Cosmos DB not configured - returning default roles for {user_id}"
        )
        # Default: authenticated users get 'developer' role
        default_roles = ["developer"]
        _role_cache.set(user_id, default_roles)
        return default_roles
    
    try:
        # Initialize Cosmos DB client
        # Note: Using connection string for simplicity in Phase 2
        # Phase 3+ can migrate to Azure Identity with RBAC
        client = CosmosClient.from_connection_string(
            settings.cosmos_db_connection_string
        )
        
        database = client.get_database_client(settings.cosmos_db_database)
        container = database.get_container_client("users")
        
        # Query for user document
        # Using userId field (not id) to avoid partition key issues
        query = "SELECT * FROM c WHERE c.userId = @userId"
        parameters = [{"name": "@userId", "value": user_id}]
        
        items = list(container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True,
            max_item_count=1
        ))
        
        if not items:
            logger.warning(f"User not found in Cosmos DB: {user_id}")
            # Return default role for authenticated but unconfigured users
            default_roles = ["developer"]
            _role_cache.set(user_id, default_roles)
            return default_roles
        
        user_doc = items[0]
        
        # Extract roles
        roles = user_doc.get("roles", [])
        
        if not isinstance(roles, list):
            logger.error(
                f"Invalid roles format for {user_id}: {type(roles)}. "
                "Expected list of strings."
            )
            roles = []
        
        # Validate role strings
        roles = [r for r in roles if isinstance(r, str)]
        
        logger.info(f"✓ Retrieved roles for {user_id}: {roles}")
        
        # Cache roles
        _role_cache.set(user_id, roles)
        
        return roles
    
    except Exception as e:
        logger.error(f"Failed to retrieve roles for {user_id}: {e}")
        # Return empty list on error (fail closed - deny access)
        return []


async def clear_role_cache(user_id: Optional[str] = None) -> None:
    """
    Clear role cache for specific user or all users.
    
    Useful for testing or when user roles change.
    
    Args:
        user_id: User ID to clear cache for, or None to clear all
    """
    _role_cache.clear(user_id)


async def set_role_cache_ttl(ttl_seconds: int) -> None:
    """
    Update role cache TTL.
    
    Args:
        ttl_seconds: New TTL in seconds
    """
    global _role_cache
    _role_cache.ttl = timedelta(seconds=ttl_seconds)
    logger.info(f"✓ Role cache TTL updated: {ttl_seconds}s")
