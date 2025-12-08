"""
Tool Registry for EVA-MCP Server.
Dynamically discovers and loads tools from the tools/ directory.
Manages tool lifecycle and RBAC enforcement.
"""

import importlib
import inspect
import logging
from pathlib import Path
from typing import Optional

from eva_mcp.tools.base import BaseTool
from eva_mcp.auth.rbac import get_user_roles

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registry for all MCP tools.
    
    Responsibilities:
    - Dynamically discover tools in tools/ directory
    - Load and initialize tools
    - Filter tools based on user roles (RBAC)
    - Manage tool lifecycle (init, cleanup)
    """
    
    def __init__(self):
        self.tools: dict[str, BaseTool] = {}
        self.tool_permissions: dict[str, list[str]] = {}  # tool_name -> required_roles
    
    async def load_tools(self) -> None:
        """
        Dynamically discover and load all tools from tools/ directory.
        Scans for Python files, imports modules, finds BaseTool subclasses.
        """
        tools_dir = Path(__file__).parent
        
        logger.info(f"Scanning for tools in: {tools_dir}")
        
        # Scan all .py files in tools/ directory
        for tool_file in tools_dir.glob("*.py"):
            # Skip private files and base.py
            if tool_file.name.startswith("_") or tool_file.name == "base.py":
                continue
            
            module_name = f"eva_mcp.tools.{tool_file.stem}"
            
            try:
                # Import module
                module = importlib.import_module(module_name)
                
                # Find all BaseTool subclasses in module
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    # Check if it's a BaseTool subclass (but not BaseTool itself)
                    if issubclass(obj, BaseTool) and obj is not BaseTool:
                        # Instantiate tool
                        tool = obj()
                        
                        # Initialize tool (setup connections, load config)
                        await tool.initialize()
                        
                        # Register tool
                        self.tools[tool.name] = tool
                        self.tool_permissions[tool.name] = tool.required_roles
                        
                        logger.info(
                            f"✓ Loaded tool: {tool.name} "
                            f"(roles: {tool.required_roles if tool.required_roles else 'public'})"
                        )
            
            except Exception as e:
                logger.error(f"✗ Failed to load tool from {tool_file}: {e}")
        
        logger.info(f"Loaded {len(self.tools)} tools total")
    
    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """
        Get tool by name.
        
        Args:
            tool_name: Unique tool identifier
        
        Returns:
            BaseTool instance or None if not found
        """
        return self.tools.get(tool_name)
    
    async def get_tools_for_user(self, user_id: Optional[str]) -> list[BaseTool]:
        """
        Get list of tools accessible by user (based on RBAC).
        
        Args:
            user_id: User ID (None for anonymous users)
        
        Returns:
            List of tools user can access
        """
        if not user_id:
            # Anonymous user: only public tools
            return [tool for tool in self.tools.values() if not tool.required_roles]
        
        # Get user roles (in Phase 1, simplified - all authenticated users get all tools)
        # In Phase 2, this will query Cosmos DB for actual user roles
        user_roles = await self._get_user_roles(user_id)
        
        accessible_tools = []
        for tool in self.tools.values():
            if not tool.required_roles:
                # Public tool
                accessible_tools.append(tool)
            elif any(role in user_roles for role in tool.required_roles):
                # User has at least one required role
                accessible_tools.append(tool)
        
        return accessible_tools
    
    async def user_can_execute(self, user_id: Optional[str], tool_name: str) -> bool:
        """
        Check if user has permission to execute tool.
        
        Args:
            user_id: User ID (None for anonymous)
            tool_name: Tool to check
        
        Returns:
            True if user can execute, False otherwise
        """
        tool = self.get_tool(tool_name)
        if not tool:
            return False
        
        if not tool.required_roles:
            # Public tool - anyone can execute
            return True
        
        if not user_id:
            # Anonymous user cannot execute protected tools
            return False
        
        # Get user roles and check permissions
        user_roles = await self._get_user_roles(user_id)
        return any(role in user_roles for role in tool.required_roles)
    
    async def _get_user_roles(self, user_id: str) -> list[str]:
        """
        Get user roles from Cosmos DB.
        
        Phase 2: Uses real Cosmos DB integration via rbac.get_user_roles().
        
        Args:
            user_id: User ID (from OAuth token sub claim)
        
        Returns:
            List of role strings (e.g., ['admin', 'developer'])
        """
        # Phase 2: Real Cosmos DB integration
        return await get_user_roles(user_id)
    
    async def close(self) -> None:
        """
        Cleanup all tools (close connections, etc.).
        Called during server shutdown.
        """
        logger.info("Cleaning up tools...")
        
        for tool_name, tool in self.tools.items():
            try:
                await tool.cleanup()
                logger.info(f"✓ Cleaned up tool: {tool_name}")
            except Exception as e:
                logger.error(f"✗ Failed to cleanup tool {tool_name}: {e}")
        
        logger.info("Tool cleanup complete")
