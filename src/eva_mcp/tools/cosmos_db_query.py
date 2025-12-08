"""
Cosmos DB Query Tool for EVA-MCP Server.
Queries Cosmos DB documents by tenant ID with SQL-like syntax.
"""

import logging
from typing import Any, Optional

from azure.cosmos.aio import CosmosClient
from pydantic import BaseModel, Field

from eva_mcp.config import settings
from eva_mcp.tools.base import BaseTool

logger = logging.getLogger(__name__)


# ============================================================================
# Input/Output Schemas
# ============================================================================

class CosmosQueryInput(BaseModel):
    """Input schema for Cosmos DB query tool."""
    tenant_id: str = Field(description="Tenant ID to filter documents (required for tenant isolation)")
    container: str = Field(
        default="prod-data",
        description="Cosmos DB container name (default: prod-data)"
    )
    query: str = Field(
        description="SQL query WITHOUT WHERE tenantId clause (added automatically)",
        examples=["c.type = 'user'", "c.status = 'active' AND c.createdAt > '2025-01-01'"]
    )
    max_items: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of items to return (1-100)"
    )


class CosmosQueryOutput(BaseModel):
    """Output schema for Cosmos DB query results."""
    items: list[dict[str, Any]] = Field(description="Query result items")
    count: int = Field(description="Number of items returned")
    continuation_token: Optional[str] = Field(
        default=None,
        description="Token for pagination (if more results available)"
    )


# ============================================================================
# Cosmos DB Query Tool
# ============================================================================

class CosmosDBQueryTool(BaseTool):
    """
    Query Cosmos DB documents by tenant ID.
    
    Executes SQL-like queries with automatic tenant isolation.
    Validates tenant_id to ensure multi-tenant data security.
    """
    
    name = "cosmos_db_query"
    description = (
        "Query Cosmos DB documents by tenant ID. "
        "Executes SQL queries with automatic tenant isolation. "
        "Returns filtered results with count and optional pagination token."
    )
    input_schema = CosmosQueryInput
    output_schema = CosmosQueryOutput
    required_roles = ["admin", "developer"]  # Protected tool
    
    def __init__(self):
        self.cosmos_client: Optional[CosmosClient] = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """
        Initialize Cosmos DB client connection.
        """
        if not settings.cosmos_db_connection_string:
            logger.warning(
                "Cosmos DB connection string not configured - "
                "tool will fail at execution time"
            )
            return
        
        try:
            self.cosmos_client = CosmosClient.from_connection_string(
                settings.cosmos_db_connection_string
            )
            self._initialized = True
            logger.info("✓ Cosmos DB client initialized")
        
        except Exception as e:
            logger.error(f"✗ Failed to initialize Cosmos DB client: {e}")
            raise
    
    async def execute(
        self,
        args: CosmosQueryInput,
        user_id: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Execute Cosmos DB query with tenant isolation.
        
        Args:
            args: Validated query parameters
            user_id: User executing query (for audit logging)
        
        Returns:
            Query results with items, count, and optional continuation token
        
        Raises:
            Exception: If Cosmos DB is not configured or query fails
        """
        if not self._initialized or not self.cosmos_client:
            raise Exception(
                "Cosmos DB not configured. "
                "Set COSMOS_CONNECTION_STRING in environment."
            )
        
        logger.info(
            f"Querying Cosmos DB: tenant={args.tenant_id}, "
            f"container={args.container}, user={user_id}"
        )
        
        try:
            # Get database and container clients
            database = self.cosmos_client.get_database_client(settings.cosmos_database_name)
            container = database.get_container_client(args.container)
            
            # Build query with tenant isolation
            # CRITICAL: Always filter by tenantId for multi-tenant security
            full_query = (
                f"SELECT * FROM c "
                f"WHERE c.tenantId = @tenantId AND ({args.query})"
            )
            
            logger.debug(f"Executing query: {full_query}")
            
            # Execute query with parameterized tenant_id (SQL injection protection)
            items = []
            query_iterator = container.query_items(
                query=full_query,
                parameters=[{"name": "@tenantId", "value": args.tenant_id}],
                max_item_count=args.max_items
            )
            
            # Fetch results
            async for item in query_iterator:
                items.append(item)
                
                # Stop if we reached max_items
                if len(items) >= args.max_items:
                    break
            
            result = {
                "items": items,
                "count": len(items),
                "continuation_token": None  # Phase 1: Simplified (no pagination)
            }
            
            logger.info(f"✓ Query returned {len(items)} items")
            
            return result
        
        except Exception as e:
            logger.error(f"✗ Cosmos DB query failed: {e}")
            raise Exception(f"Cosmos DB query failed: {str(e)}")
    
    async def cleanup(self) -> None:
        """
        Close Cosmos DB client connection.
        """
        if self.cosmos_client:
            await self.cosmos_client.close()
            logger.info("✓ Cosmos DB client closed")
