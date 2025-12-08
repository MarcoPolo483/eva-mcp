"""
Base Tool Interface for EVA-MCP Server.
All tools must inherit from BaseTool and implement the required methods.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional, Type
from pydantic import BaseModel


class BaseTool(ABC):
    """
    Abstract base class for all MCP tools.
    
    Subclasses must implement:
    - name: Unique tool identifier
    - description: Human-readable description
    - input_schema: Pydantic model for input validation
    - execute(): Tool execution logic
    
    Optional:
    - output_schema: Pydantic model for output validation
    - required_roles: List of roles needed to execute (empty = public)
    - initialize(): Setup connections, load config
    - cleanup(): Cleanup resources
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """
        Unique tool name (e.g., 'cosmos_db_query').
        Must be unique across all tools.
        """
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """
        Human-readable description of tool functionality.
        Should explain what the tool does and when to use it.
        """
        pass
    
    @property
    @abstractmethod
    def input_schema(self) -> Type[BaseModel]:
        """
        Pydantic model defining tool input parameters.
        Used for automatic validation and schema generation.
        """
        pass
    
    @property
    def output_schema(self) -> Optional[Type[BaseModel]]:
        """
        Pydantic model defining tool output structure (optional).
        If None, tool returns unstructured dict.
        """
        return None
    
    @property
    def required_roles(self) -> list[str]:
        """
        List of roles required to execute this tool.
        Empty list = public tool (no authentication required).
        Example: ['admin', 'developer']
        """
        return []
    
    async def initialize(self) -> None:
        """
        Initialize tool resources (connections, config, etc.).
        Called once during tool registry loading.
        Override if tool needs setup.
        """
        pass
    
    @abstractmethod
    async def execute(self, args: BaseModel, user_id: Optional[str] = None) -> dict[str, Any]:
        """
        Execute tool with validated arguments.
        
        Args:
            args: Validated input parameters (instance of input_schema)
            user_id: ID of user executing tool (None for anonymous)
        
        Returns:
            dict: Tool execution result (validated against output_schema if defined)
        
        Raises:
            Exception: On execution failure (logged and returned to client)
        """
        pass
    
    async def cleanup(self) -> None:
        """
        Cleanup tool resources (close connections, etc.).
        Called during server shutdown.
        Override if tool needs cleanup.
        """
        pass
