"""
FastAPI MCP Server for EVA Suite.
Implements Model Context Protocol endpoints for tool discovery and execution.
"""

import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, ValidationError

from eva_mcp.config import settings
from eva_mcp.tools.registry import ToolRegistry
from eva_mcp.auth.oauth import OAuthProvider
from eva_mcp.auth.rbac import get_user_roles

# Configure logging
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global tool registry and OAuth provider
tool_registry = ToolRegistry()
oauth_provider: Optional[OAuthProvider] = None

# In-memory session storage (Phase 1 simplification)
# Phase 2+ will use Redis or similar for distributed sessions
sessions: dict[str, dict[str, Any]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown tasks.
    """
    global oauth_provider
    
    # Startup: Initialize OAuth provider and load tools
    logger.info("Starting EVA-MCP Server...")
    
    # Initialize OAuth provider (Phase 2)
    oauth_provider = OAuthProvider()
    await oauth_provider.initialize()
    logger.info("✓ OAuth provider initialized")
    
    # Load all tools
    await tool_registry.load_tools()
    logger.info(f"✓ Loaded {len(tool_registry.tools)} tools")
    
    yield
    
    # Shutdown: Cleanup
    logger.info("Shutting down EVA-MCP Server...")
    await tool_registry.close()
    if oauth_provider:
        await oauth_provider.cleanup()
    logger.info("✓ Cleanup complete")


# Create FastAPI app
app = FastAPI(
    title="EVA Model Context Protocol Server",
    description="Exposes EVA Suite tools to AI agents via MCP over HTTP/SSE",
    version="1.0.0",
    lifespan=lifespan
)


# ============================================================================
# Request/Response Models
# ============================================================================

class InitializeRequest(BaseModel):
    """Request to initialize MCP session."""
    client_id: str
    client_name: Optional[str] = None


class InitializeResponse(BaseModel):
    """Response from session initialization."""
    session_id: str
    status: str
    server_name: str = "eva-mcp"
    server_version: str = "1.0.0"


class ToolSpec(BaseModel):
    """Tool specification with JSON schemas."""
    name: str
    description: str
    inputSchema: dict[str, Any]
    outputSchema: Optional[dict[str, Any]] = None


class ToolsResponse(BaseModel):
    """Response containing list of available tools."""
    tools: list[ToolSpec]


class ExecuteToolRequest(BaseModel):
    """Request to execute a tool."""
    tool_name: str
    arguments: dict[str, Any]


class ExecuteToolResponse(BaseModel):
    """Response from tool execution."""
    content: dict[str, Any]
    isError: bool


# ============================================================================
# MCP Endpoints
# ============================================================================

@app.post("/mcp/initialize", response_model=InitializeResponse)
async def initialize_mcp_session(
    request: InitializeRequest,
    authorization: Optional[str] = Header(None)
) -> InitializeResponse:
    """
    Initialize MCP session with client.
    
    Creates a new session and returns session ID for subsequent requests.
    Optional Bearer token for authenticated users (Phase 1: simplified auth).
    
    Args:
        request: Client initialization data
        authorization: Optional Bearer token
    
    Returns:
        Session initialization response with session_id
    """
    logger.info(f"Initializing session for client: {request.client_id}")
    
    # Extract user ID from Bearer token
    # Phase 2: Real OAuth 2.1 validation with Azure AD B2C
    user_id = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer "):]
        
        # Validate token with OAuth provider
        if oauth_provider:
            user_id = await oauth_provider.validate_token(token)
            if user_id:
                logger.info(f"✓ Authenticated user: {user_id}")
            else:
                logger.warning("Token validation failed")
                raise HTTPException(status_code=401, detail="Invalid access token")
        else:
            # Fallback if OAuth not configured (Phase 1 compatibility)
            user_id = token
            logger.warning(f"OAuth not configured - accepting token as user_id: {user_id}")
    
    # Create new session
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "user_id": user_id,
        "client_id": request.client_id,
        "client_name": request.client_name,
        "created_at": datetime.utcnow()
    }
    
    logger.info(f"✓ Session created: {session_id}")
    
    return InitializeResponse(
        session_id=session_id,
        status="initialized"
    )


@app.get("/mcp/tools", response_model=ToolsResponse)
async def list_tools(
    session_id: Optional[str] = Header(None, alias="x-session-id")
) -> ToolsResponse:
    """
    List all available tools with JSON schemas.
    
    Filters tools based on user permissions (RBAC).
    Returns tool specifications including input/output schemas.
    
    Args:
        session_id: Session ID from initialization (in X-Session-Id header)
    
    Returns:
        List of tool specifications
    
    Raises:
        HTTPException: If session is invalid
    """
    # Validate session
    if not session_id or session_id not in sessions:
        raise HTTPException(status_code=401, detail="Invalid or missing session ID")
    
    session_data = sessions[session_id]
    user_id = session_data["user_id"]
    
    logger.info(f"Listing tools for session: {session_id} (user: {user_id or 'anonymous'})")
    
    # Get tools accessible by this user (RBAC filtering)
    accessible_tools = await tool_registry.get_tools_for_user(user_id)
    
    # Build tool specifications
    tool_specs = []
    for tool in accessible_tools:
        tool_spec = ToolSpec(
            name=tool.name,
            description=tool.description,
            inputSchema=tool.input_schema.model_json_schema(),
            outputSchema=tool.output_schema.model_json_schema() if tool.output_schema else None
        )
        tool_specs.append(tool_spec)
    
    logger.info(f"✓ Returning {len(tool_specs)} tools")
    
    return ToolsResponse(tools=tool_specs)


@app.post("/mcp/tools/execute", response_model=ExecuteToolResponse)
async def execute_tool(
    request: ExecuteToolRequest,
    session_id: Optional[str] = Header(None, alias="x-session-id")
) -> ExecuteToolResponse:
    """
    Execute a tool with provided arguments.
    
    Validates arguments against tool schema, checks permissions, executes tool.
    Returns structured result or error.
    
    Args:
        request: Tool execution request with tool_name and arguments
        session_id: Session ID from initialization (in X-Session-Id header)
    
    Returns:
        Tool execution result or error
    
    Raises:
        HTTPException: If session invalid, tool not found, or permission denied
    """
    # Validate session
    if not session_id or session_id not in sessions:
        raise HTTPException(status_code=401, detail="Invalid or missing session ID")
    
    session_data = sessions[session_id]
    user_id = session_data["user_id"]
    
    logger.info(
        f"Executing tool: {request.tool_name} "
        f"(session: {session_id}, user: {user_id or 'anonymous'})"
    )
    
    # Get tool from registry
    tool = tool_registry.get_tool(request.tool_name)
    if not tool:
        logger.error(f"✗ Tool not found: {request.tool_name}")
        raise HTTPException(status_code=404, detail=f"Tool '{request.tool_name}' not found")
    
    # Check user has permission to execute tool (RBAC)
    if not await tool_registry.user_can_execute(user_id, request.tool_name):
        logger.error(f"✗ Permission denied for user {user_id} to execute {request.tool_name}")
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient permissions to execute '{request.tool_name}'"
        )
    
    # Validate arguments against tool input schema
    try:
        validated_args = tool.input_schema.model_validate(request.arguments)
    except ValidationError as e:
        logger.error(f"✗ Invalid arguments: {e}")
        return ExecuteToolResponse(
            content={"error": f"Invalid arguments: {e}"},
            isError=True
        )
    
    # Execute tool
    try:
        result = await tool.execute(validated_args, user_id=user_id)
        logger.info(f"✓ Tool executed successfully: {request.tool_name}")
        
        return ExecuteToolResponse(
            content=result,
            isError=False
        )
    
    except Exception as e:
        logger.error(f"✗ Tool execution failed: {request.tool_name} - {e}")
        return ExecuteToolResponse(
            content={"error": str(e), "tool": request.tool_name},
            isError=True
        )


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """
    Health check endpoint.
    
    Returns server status and number of loaded tools.
    """
    return {
        "status": "healthy",
        "server": "eva-mcp",
        "version": "1.0.0",
        "tools_loaded": len(tool_registry.tools),
        "active_sessions": len(sessions)
    }


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "eva_mcp.server:app",
        host=settings.mcp_server_host,
        port=settings.mcp_server_port,
        reload=True,
        log_level=settings.log_level.lower()
    )
