"""
Azure Resource List Tool for EVA-MCP Server.
Lists Azure resources in a subscription with optional filtering.
"""

import logging
from typing import Any, Optional

from azure.identity.aio import ClientSecretCredential
from azure.mgmt.resource.resources.aio import ResourceManagementClient
from pydantic import BaseModel, Field

from eva_mcp.config import settings
from eva_mcp.tools.base import BaseTool

logger = logging.getLogger(__name__)


# ============================================================================
# Input/Output Schemas
# ============================================================================

class AzureResourceListInput(BaseModel):
    """Input schema for Azure resource listing tool."""
    resource_group: Optional[str] = Field(
        default=None,
        description="Resource group name to filter by (optional - lists all if not provided)"
    )
    resource_type: Optional[str] = Field(
        default=None,
        description="Resource type to filter by (e.g., 'Microsoft.Storage/storageAccounts')"
    )


class AzureResource(BaseModel):
    """Schema for a single Azure resource."""
    id: str = Field(description="Resource ID")
    name: str = Field(description="Resource name")
    type: str = Field(description="Resource type")
    location: str = Field(description="Azure region")
    resource_group: Optional[str] = Field(default=None, description="Resource group name")


class AzureResourceListOutput(BaseModel):
    """Output schema for Azure resource listing."""
    resources: list[AzureResource] = Field(description="List of Azure resources")
    count: int = Field(description="Number of resources returned")


# ============================================================================
# Azure Resource List Tool
# ============================================================================

class AzureResourceListTool(BaseTool):
    """
    List Azure resources in a subscription.
    
    Retrieves resources with optional filtering by resource group and type.
    Requires Azure service principal credentials.
    """
    
    name = "azure_resource_list"
    description = (
        "List Azure resources in a subscription. "
        "Optional filters: resource group, resource type. "
        "Returns resource ID, name, type, location, and resource group."
    )
    input_schema = AzureResourceListInput
    output_schema = AzureResourceListOutput
    required_roles = ["admin"]  # Protected tool - admin only
    
    def __init__(self):
        self.credential: Optional[ClientSecretCredential] = None
        self.resource_client: Optional[ResourceManagementClient] = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """
        Initialize Azure Resource Management client.
        """
        # Check if Azure credentials are configured
        if not all([
            settings.azure_subscription_id,
            settings.azure_tenant_id,
            settings.azure_client_id,
            settings.azure_client_secret
        ]):
            logger.warning(
                "Azure credentials not fully configured - "
                "tool will fail at execution time"
            )
            return
        
        try:
            # Create service principal credential
            self.credential = ClientSecretCredential(
                tenant_id=settings.azure_tenant_id,
                client_id=settings.azure_client_id,
                client_secret=settings.azure_client_secret
            )
            
            # Create Resource Management client
            self.resource_client = ResourceManagementClient(
                credential=self.credential,
                subscription_id=settings.azure_subscription_id
            )
            
            self._initialized = True
            logger.info("✓ Azure Resource Management client initialized")
        
        except Exception as e:
            logger.error(f"✗ Failed to initialize Azure RM client: {e}")
            raise
    
    async def execute(
        self,
        args: AzureResourceListInput,
        user_id: Optional[str] = None
    ) -> dict[str, Any]:
        """
        List Azure resources with optional filtering.
        
        Args:
            args: Validated resource list parameters
            user_id: User executing query (for audit logging)
        
        Returns:
            List of Azure resources with metadata
        
        Raises:
            Exception: If Azure credentials not configured or API call fails
        """
        if not self._initialized or not self.resource_client:
            raise Exception(
                "Azure Resource Manager not configured. "
                "Set AZURE_SUBSCRIPTION_ID, AZURE_TENANT_ID, AZURE_CLIENT_ID, "
                "and AZURE_CLIENT_SECRET in environment."
            )
        
        logger.info(
            f"Listing Azure resources: rg={args.resource_group}, "
            f"type={args.resource_type}, user={user_id}"
        )
        
        try:
            resources = []
            
            # List resources (filtered by resource group if provided)
            if args.resource_group:
                # List resources in specific resource group
                resource_iterator = self.resource_client.resources.list_by_resource_group(
                    resource_group_name=args.resource_group
                )
            else:
                # List all resources in subscription
                resource_iterator = self.resource_client.resources.list()
            
            # Fetch and filter resources
            async for resource in resource_iterator:
                # Apply resource type filter if provided
                if args.resource_type and resource.type != args.resource_type:
                    continue
                
                # Extract resource group from resource ID
                # Format: /subscriptions/{sub}/resourceGroups/{rg}/providers/{provider}/{type}/{name}
                resource_group = None
                if resource.id:
                    parts = resource.id.split("/")
                    if "resourceGroups" in parts:
                        rg_index = parts.index("resourceGroups")
                        if rg_index + 1 < len(parts):
                            resource_group = parts[rg_index + 1]
                
                # Build resource object
                azure_resource = AzureResource(
                    id=resource.id,
                    name=resource.name,
                    type=resource.type,
                    location=resource.location or "unknown",
                    resource_group=resource_group
                )
                
                resources.append(azure_resource.model_dump())
            
            result = {
                "resources": resources,
                "count": len(resources)
            }
            
            logger.info(f"✓ Listed {len(resources)} Azure resources")
            
            return result
        
        except Exception as e:
            logger.error(f"✗ Azure resource listing failed: {e}")
            raise Exception(f"Azure resource listing failed: {str(e)}")
    
    async def cleanup(self) -> None:
        """
        Close Azure clients.
        """
        if self.resource_client:
            await self.resource_client.close()
            logger.info("✓ Azure Resource Management client closed")
        
        if self.credential:
            await self.credential.close()
            logger.info("✓ Azure credential closed")
