# EVA Model Context Protocol Server (eva-mcp)

**Comprehensive Specification for Autonomous Implementation**

---

## 1. Vision & Business Value

### What This Service Delivers

EVA-MCP provides **Model Context Protocol (MCP)** server integration for EVA Suite, enabling AI agents to discover and invoke tools dynamically:

- **Tool Discovery**: List available tools with schemas (name, description, parameters)
- **Tool Execution**: Call tools with validated arguments and receive structured responses
- **Resource Management**: Read/write resources (files, database records, API data)
- **Context Sharing**: Share context between AI agents and external systems
- **OAuth 2.1 Authentication**: Secure tool access with Azure AD B2C integration
- **HTTP Streaming**: Bidirectional streaming for real-time tool interactions

### Success Metrics

- **Tool Discovery Latency**: < 100ms to list all available tools
- **Tool Execution Success Rate**: 99%+ (failures due to invalid args, not MCP protocol)
- **Concurrent Clients**: Support 100+ simultaneous MCP client connections
- **OAuth Token Refresh**: Automatic refresh < 1 second before expiration
- **Resource Read/Write**: < 500ms for typical file/database operations

### Business Impact

- **Agent Composability**: Any compliant agent runtime (VS Code, OpenWebUI, Cursor, Windsurf) can use EVA tools
- **Runtime Portability**: Same agent logic works in cloud (Azure Container Apps), local (WSL2), or VS Code
- **Security & Governance**: RBAC per tool, audit logging, secrets isolation via Azure Key Vault
- **Tooling Marketplace**: Curated MCP tool packs (Azure governance, documentation, localization) for customers

---

## 2. Architecture Overview

### MCP Protocol Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                     AI Agent Runtime (Client)                       │
│                  (VS Code, OpenWebUI, Custom Agent)                 │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  MCP Client Session                                           │ │
│  │  ├─ Initialize: Establish HTTP/SSE connection                 │ │
│  │  ├─ List Tools: GET /tools → JSON array of tool schemas       │ │
│  │  ├─ Call Tool: POST /tools/execute → Execute with args        │ │
│  │  ├─ List Resources: GET /resources → Available files/data     │ │
│  │  └─ Read Resource: GET /resources/{uri} → Resource content    │ │
│  └───────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                   ↕ HTTP/SSE (Streamable HTTP)
┌─────────────────────────────────────────────────────────────────────┐
│                     EVA-MCP Server (eva-mcp)                        │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  MCP Server Session Handler                                   │ │
│  │  ├─ Session Init: Validate client, establish context          │ │
│  │  ├─ Tool Registry: Load all EVA tools (Cosmos DB, Azure, Git)│ │
│  │  ├─ OAuth Provider: Token refresh, client registration        │ │
│  │  ├─ Tool Executor: Validate args, call tool, return result    │ │
│  │  └─ Resource Manager: CRUD operations on files/database       │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  EVA Tools (Registered in MCP Server)                         │ │
│  │  ├─ Cosmos DB Admin: Query/insert/update documents            │ │
│  │  ├─ Azure Resource Manager: Deploy/query/update resources     │ │
│  │  ├─ Git Operations: Clone/commit/push/pull repositories       │ │
│  │  ├─ Documentation Search: RAG query across docs/              │ │
│  │  ├─ Localization: Translate strings (EN ↔ FR)                 │ │
│  │  └─ Telemetry: Send metrics to Application Insights           │ │
│  └───────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                   ↕ Azure SDK / REST APIs
┌─────────────────────────────────────────────────────────────────────┐
│                     Azure Backend Services                          │
│  ├─ Cosmos DB (eva-core domain entities)                           │
│  ├─ Azure AI Search (eva-rag document index)                       │
│  ├─ Azure OpenAI (GPT-4o for tool generation)                      │
│  ├─ Azure Resource Manager (infrastructure deployments)            │
│  ├─ Azure Key Vault (secrets, OAuth tokens)                        │
│  └─ Application Insights (tool execution traces)                   │
└─────────────────────────────────────────────────────────────────────┘
```

**Key Concepts**:

- **MCP Client**: Any application consuming tools via MCP protocol (VS Code, OpenWebUI, etc.)
- **MCP Server**: EVA-MCP service exposing tools via HTTP/SSE
- **Tool**: Atomic operation (e.g., "Query Cosmos DB", "Deploy Azure resource") with JSON schema
- **Resource**: File or data accessible via URI (e.g., `file:///docs/README.md`, `cosmos://tenants/tenant-1`)
- **Session**: Stateful connection between client and server (OAuth tokens, context)

---

## 3. Technical Stack

### Primary Technologies

- **Protocol**: Model Context Protocol (MCP) via HTTP + Server-Sent Events (SSE)
- **Language**: Python 3.11+ (async/await with `asyncio`)
- **Framework**: FastAPI 0.104+ (for HTTP endpoints)
- **MCP SDK**: `mcp` Python package (from Anthropic: `pip install mcp`)
- **Authentication**: OAuth 2.1 (Azure AD B2C), Bearer tokens, session tokens
- **Streaming**: `mcp.client.streamable_http` (bidirectional HTTP streaming)
- **Secrets**: Azure Key Vault (OAuth client secrets, Azure API keys)
- **Observability**: Application Insights (tool execution traces, latency metrics)

### MCP Python Package Structure

```python
from mcp import ClientSession, ServerSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
```

### Dependencies

```toml
[tool.poetry.dependencies]
python = "^3.11"
fastapi = "^0.104.0"
uvicorn = "^0.24.0"
mcp = "^1.0.0"              # Model Context Protocol SDK
pydantic = "^2.5.0"
aiohttp = "^3.9.0"
azure-identity = "^1.15.0"
azure-keyvault-secrets = "^4.7.0"
azure-cosmos = "^4.5.0"
azure-mgmt-resource = "^23.0.0"
applicationinsights = "^0.11.10"
```

---

## 4. MCP Server Implementation

### 4.1 Server Initialization

**File**: `src/eva_mcp/server.py`

**Responsibilities**:
- Initialize FastAPI application
- Load tool registry (all available EVA tools)
- Configure OAuth provider (Azure AD B2C)
- Setup Application Insights tracing

**Implementation**:
```python
from fastapi import FastAPI, HTTPException, Header
from contextlib import asynccontextmanager
from mcp import ServerSession
from mcp.server.streamable_http import streamablehttp_server

from eva_mcp.tools.registry import ToolRegistry
from eva_mcp.auth.oauth import OAuthProvider
from eva_mcp.config import Settings

settings = Settings()
tool_registry = ToolRegistry()
oauth_provider = OAuthProvider(settings)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Load all tools
    await tool_registry.load_tools()
    print(f"Loaded {len(tool_registry.tools)} tools")
    
    yield
    
    # Shutdown: Cleanup
    await tool_registry.close()

app = FastAPI(
    title="EVA Model Context Protocol Server",
    version="1.0.0",
    lifespan=lifespan
)

# MCP Server Session Storage (in-memory for demo, Redis for production)
sessions: dict[str, ServerSession] = {}

@app.post("/mcp/initialize")
async def initialize_mcp_session(
    client_id: str,
    authorization: str = Header(None)
):
    """
    Initialize MCP session with client.
    Returns session ID for subsequent requests.
    """
    # Validate OAuth token if provided
    user_id = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer "):]
        user_id = await oauth_provider.validate_token(token)
    
    # Create new MCP server session
    session_id = str(uuid.uuid4())
    
    # Create ServerSession (MCP SDK)
    read_stream, write_stream = create_bidirectional_stream()
    session = ServerSession(read_stream, write_stream)
    
    # Initialize session with client capabilities
    await session.initialize()
    
    sessions[session_id] = {
        "session": session,
        "user_id": user_id,
        "client_id": client_id,
        "created_at": datetime.utcnow()
    }
    
    return {"session_id": session_id, "status": "initialized"}

@app.get("/mcp/tools")
async def list_tools(session_id: str = Header(None)):
    """
    List all available tools with schemas.
    Returns JSON array of tool definitions.
    """
    if not session_id or session_id not in sessions:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    session_data = sessions[session_id]
    user_id = session_data["user_id"]
    
    # Get tools accessible by this user (RBAC filtering)
    tools = await tool_registry.get_tools_for_user(user_id)
    
    tool_specs = []
    for tool in tools:
        tool_specs.append({
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.input_schema.model_json_schema(),
            "outputSchema": tool.output_schema.model_json_schema() if tool.output_schema else None
        })
    
    return {"tools": tool_specs}

@app.post("/mcp/tools/execute")
async def execute_tool(
    session_id: str = Header(None),
    tool_name: str = None,
    arguments: dict = None
):
    """
    Execute a tool with provided arguments.
    Returns tool execution result or error.
    """
    if not session_id or session_id not in sessions:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    session_data = sessions[session_id]
    mcp_session = session_data["session"]
    user_id = session_data["user_id"]
    
    # Get tool from registry
    tool = tool_registry.get_tool(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
    
    # Check user has permission to execute tool
    if not await tool_registry.user_can_execute(user_id, tool_name):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    # Validate arguments against tool schema
    try:
        validated_args = tool.input_schema.model_validate(arguments)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid arguments: {e}")
    
    # Execute tool
    try:
        result = await tool.execute(validated_args, user_id=user_id)
        
        # Trace execution in Application Insights
        await trace_tool_execution(tool_name, user_id, validated_args, result, success=True)
        
        return {
            "content": result,
            "isError": False
        }
    except Exception as e:
        # Trace error
        await trace_tool_execution(tool_name, user_id, validated_args, None, success=False, error=str(e))
        
        return {
            "content": {"error": str(e)},
            "isError": True
        }
```

---

### 4.2 Tool Registry

**File**: `src/eva_mcp/tools/registry.py`

**Responsibilities**:
- Dynamically discover tools in `src/eva_mcp/tools/` directory
- Load tool metadata (name, description, schemas)
- Manage tool lifecycle (init, execute, cleanup)
- RBAC: Check user permissions before tool execution

**Implementation**:
```python
from pathlib import Path
import importlib
import inspect
from typing import Dict, List, Optional
from pydantic import BaseModel

from eva_mcp.tools.base import BaseTool
from eva_mcp.auth.rbac import check_permission

class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
        self.tool_permissions: Dict[str, List[str]] = {}  # tool_name -> list of required roles
    
    async def load_tools(self):
        """
        Dynamically discover and load all tools from tools/ directory.
        """
        tools_dir = Path(__file__).parent / "tools"
        
        for tool_file in tools_dir.glob("*.py"):
            if tool_file.name.startswith("_"):
                continue  # Skip private files
            
            # Import module
            module_name = f"eva_mcp.tools.{tool_file.stem}"
            module = importlib.import_module(module_name)
            
            # Find all BaseTool subclasses
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BaseTool) and obj is not BaseTool:
                    # Instantiate tool
                    tool = obj()
                    await tool.initialize()
                    
                    self.tools[tool.name] = tool
                    self.tool_permissions[tool.name] = tool.required_roles
                    
                    print(f"Loaded tool: {tool.name} (requires roles: {tool.required_roles})")
    
    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        return self.tools.get(tool_name)
    
    async def get_tools_for_user(self, user_id: Optional[str]) -> List[BaseTool]:
        """
        Return list of tools accessible by user (based on RBAC).
        """
        if not user_id:
            # Anonymous user: only public tools
            return [tool for tool in self.tools.values() if not tool.required_roles]
        
        # Get user roles from Cosmos DB
        user_roles = await get_user_roles(user_id)
        
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
        """
        tool = self.get_tool(tool_name)
        if not tool:
            return False
        
        if not tool.required_roles:
            # Public tool
            return True
        
        if not user_id:
            # Anonymous user cannot execute protected tools
            return False
        
        user_roles = await get_user_roles(user_id)
        return any(role in user_roles for role in tool.required_roles)
    
    async def close(self):
        """
        Cleanup all tools.
        """
        for tool in self.tools.values():
            await tool.cleanup()
```

---

### 4.3 Base Tool Interface

**File**: `src/eva_mcp/tools/base.py`

**Responsibilities**:
- Define standard interface for all EVA tools
- Input/output schema validation
- Error handling
- Tracing integration

**Implementation**:
```python
from abc import ABC, abstractmethod
from typing import Any, Optional, Type
from pydantic import BaseModel

class BaseTool(ABC):
    """
    Base class for all MCP tools.
    Subclasses must implement: initialize(), execute(), cleanup().
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name (must be unique)."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of tool functionality."""
        pass
    
    @property
    @abstractmethod
    def input_schema(self) -> Type[BaseModel]:
        """Pydantic model defining tool input parameters."""
        pass
    
    @property
    def output_schema(self) -> Optional[Type[BaseModel]]:
        """Pydantic model defining tool output (optional)."""
        return None
    
    @property
    def required_roles(self) -> list[str]:
        """List of roles required to execute this tool (empty = public)."""
        return []
    
    async def initialize(self):
        """Initialize tool (load config, establish connections, etc.)."""
        pass
    
    @abstractmethod
    async def execute(self, args: BaseModel, user_id: Optional[str] = None) -> dict:
        """
        Execute tool with validated arguments.
        Returns dict with tool execution result.
        """
        pass
    
    async def cleanup(self):
        """Cleanup resources (close connections, etc.)."""
        pass
```

---

### 4.4 Example Tool: Cosmos DB Query

**File**: `src/eva_mcp/tools/cosmos_db_query.py`

**Description**: Query Cosmos DB documents by tenantId

**Implementation**:
```python
from pydantic import BaseModel, Field
from azure.cosmos.aio import CosmosClient
from typing import Optional

from eva_mcp.tools.base import BaseTool
from eva_mcp.config import settings

class CosmosQueryInput(BaseModel):
    tenant_id: str = Field(description="Tenant ID to filter documents")
    container: str = Field(description="Cosmos DB container name", default="prod-data")
    query: str = Field(description="SQL query (without WHERE tenantId clause)")
    max_items: int = Field(description="Maximum items to return", default=10, ge=1, le=100)

class CosmosQueryOutput(BaseModel):
    items: list[dict]
    count: int
    continuation_token: Optional[str]

class CosmosDBQueryTool(BaseTool):
    name = "cosmos_db_query"
    description = "Query Cosmos DB documents by tenant ID. Returns filtered results."
    input_schema = CosmosQueryInput
    output_schema = CosmosQueryOutput
    required_roles = ["admin", "developer"]  # Protected tool
    
    def __init__(self):
        self.cosmos_client: Optional[CosmosClient] = None
    
    async def initialize(self):
        # Connect to Cosmos DB
        self.cosmos_client = CosmosClient.from_connection_string(
            settings.COSMOS_CONNECTION_STRING
        )
    
    async def execute(self, args: CosmosQueryInput, user_id: Optional[str] = None) -> dict:
        database = self.cosmos_client.get_database_client("eva-suite-db")
        container = database.get_container_client(args.container)
        
        # Build query with tenant isolation
        full_query = f"SELECT * FROM c WHERE c.tenantId = @tenantId AND ({args.query})"
        
        # Execute query
        items = []
        query_iterator = container.query_items(
            query=full_query,
            parameters=[{"name": "@tenantId", "value": args.tenant_id}],
            max_item_count=args.max_items
        )
        
        async for item in query_iterator:
            items.append(item)
        
        return {
            "items": items,
            "count": len(items),
            "continuation_token": None  # Simplified for demo
        }
    
    async def cleanup(self):
        if self.cosmos_client:
            await self.cosmos_client.close()
```

---

### 4.5 OAuth 2.1 Authentication

**File**: `src/eva_mcp/auth/oauth.py`

**Responsibilities**:
- Dynamic client registration with Azure AD B2C
- Token validation and refresh
- OAuth token storage in Key Vault

**Implementation**:
```python
import aiohttp
from typing import Optional
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from azure.identity.aio import DefaultAzureCredential
from azure.keyvault.secrets.aio import SecretClient

from eva_mcp.config import Settings

class OAuthProvider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.kv_client = SecretClient(
            vault_url=settings.KEY_VAULT_URL,
            credential=DefaultAzureCredential()
        )
        self.oauth_clients: dict[str, OAuthClientInformationFull] = {}
    
    async def register_client(self, client_id: str, server_url: str) -> OAuthClientInformationFull:
        """
        Perform dynamic client registration with OAuth server.
        """
        # Discover OAuth metadata
        metadata_url = f"{server_url}/.well-known/oauth-authorization-server"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(metadata_url) as resp:
                if resp.status != 200:
                    raise Exception(f"Failed to fetch OAuth metadata from {metadata_url}")
                
                metadata = await resp.json()
        
        # Register client
        registration_url = metadata.get("registration_endpoint")
        if not registration_url:
            raise Exception("OAuth server does not support dynamic client registration")
        
        client_metadata = {
            "client_name": f"eva-mcp-{client_id}",
            "redirect_uris": [f"{self.settings.MCP_SERVER_URL}/oauth/callback"],
            "grant_types": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_method": "client_secret_post"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(registration_url, json=client_metadata) as resp:
                if resp.status != 201:
                    raise Exception(f"Client registration failed: {await resp.text()}")
                
                client_info = await resp.json()
        
        # Store client secret in Key Vault
        await self.kv_client.set_secret(
            f"mcp-client-{client_id}-secret",
            client_info["client_secret"]
        )
        
        # Cache client info
        oauth_client_info = OAuthClientInformationFull(**client_info, issuer=metadata_url)
        self.oauth_clients[client_id] = oauth_client_info
        
        return oauth_client_info
    
    async def validate_token(self, access_token: str) -> Optional[str]:
        """
        Validate OAuth access token.
        Returns user ID if valid, None otherwise.
        """
        # Call Azure AD B2C userinfo endpoint
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.settings.AZURE_AD_B2C_ISSUER}/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            ) as resp:
                if resp.status != 200:
                    return None
                
                userinfo = await resp.json()
                return userinfo.get("sub")  # User ID
    
    async def refresh_token(self, client_id: str, refresh_token: str) -> OAuthToken:
        """
        Refresh OAuth access token using refresh token.
        """
        client_info = self.oauth_clients.get(client_id)
        if not client_info:
            raise Exception(f"Client {client_id} not registered")
        
        # Get client secret from Key Vault
        client_secret = await self.kv_client.get_secret(f"mcp-client-{client_id}-secret")
        
        # Exchange refresh token for new access token
        async with aiohttp.ClientSession() as session:
            async with session.post(
                client_info.token_endpoint,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_info.client_id,
                    "client_secret": client_secret.value
                }
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"Token refresh failed: {await resp.text()}")
                
                token_data = await resp.json()
        
        return OAuthToken(**token_data)
```

---

## 5. MCP Client Integration (OpenWebUI Reference)

**OpenWebUI Pattern** (from `utils/mcp/client.py`):

```python
class MCPClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = None

    async def connect(self, url: str, headers: Optional[dict] = None):
        async with AsyncExitStack() as exit_stack:
            try:
                self._streams_context = streamablehttp_client(url, headers=headers)
                transport = await exit_stack.enter_async_context(self._streams_context)
                read_stream, write_stream, _ = transport

                self._session_context = ClientSession(read_stream, write_stream)
                self.session = await exit_stack.enter_async_context(self._session_context)
                
                with anyio.fail_after(10):
                    await self.session.initialize()
                
                self.exit_stack = exit_stack.pop_all()
            except Exception as e:
                await asyncio.shield(self.disconnect())
                raise e

    async def list_tool_specs(self) -> Optional[dict]:
        if not self.session:
            raise RuntimeError("MCP client is not connected.")

        result = await self.session.list_tools()
        tools = result.tools

        tool_specs = []
        for tool in tools:
            tool_specs.append({
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema
            })

        return tool_specs

    async def call_tool(self, function_name: str, function_args: dict) -> Optional[dict]:
        if not self.session:
            raise RuntimeError("MCP client is not connected.")

        result = await self.session.call_tool(function_name, function_args)
        if not result:
            raise Exception("No result returned from MCP tool call.")

        result_dict = result.model_dump(mode="json")
        result_content = result_dict.get("content", {})

        if result.isError:
            raise Exception(result_content)
        else:
            return result_content
```

**Key Insights from OpenWebUI**:
- MCP clients use `streamablehttp_client` for HTTP/SSE transport
- `ClientSession` handles protocol-level message exchange
- Tool execution is async with `await session.call_tool(name, args)`
- Error handling: `result.isError` flag + error content
- Session management: `AsyncExitStack` for cleanup

---

## 6. Quality Gates (All Must Pass)

### 1. Tool Discovery: < 100ms
- **Metric**: Time to list all available tools
- **Tool**: Custom benchmark script
- **Evidence**: 95th percentile < 100ms for 50+ tools

### 2. Tool Execution Success Rate: 99%+
- **Metric**: Successful executions / total executions
- **Tool**: Application Insights custom metric
- **Evidence**: Dashboard showing 99%+ success rate over 7 days

### 3. Concurrent Clients: 100+
- **Metric**: Number of simultaneous MCP client connections
- **Tool**: Load testing with `locust`
- **Evidence**: Load test report showing 100 clients @ 50 req/s

### 4. OAuth Token Refresh: < 1s
- **Metric**: Time to refresh expired token
- **Tool**: Custom timer in OAuth provider
- **Evidence**: 99th percentile < 1 second

### 5. Resource Read/Write: < 500ms
- **Metric**: Latency for file/database operations
- **Tool**: Application Insights dependency tracking
- **Evidence**: P95 < 500ms for Cosmos DB, Blob Storage

### 6. Tool Schema Validation: 100%
- **Metric**: Invalid arguments rejected before execution
- **Tool**: Pydantic validation errors
- **Evidence**: Zero tool execution failures due to invalid args

### 7. RBAC Enforcement: 100%
- **Metric**: Unauthorized executions blocked
- **Tool**: Manual testing with different user roles
- **Evidence**: Test report showing all unauthorized attempts blocked

### 8. Test Coverage: 90%+
- **Metric**: Code coverage for MCP server logic
- **Tool**: `pytest-cov`
- **Evidence**: Coverage report showing 90%+ for `src/eva_mcp/`

### 9. Documentation: 100% Complete
- **Sections**: Tool catalog, OAuth setup, deployment guide
- **Evidence**: All docs exist with examples

### 10. Secrets Management: Zero Secrets in Code
- **Tool**: `trufflehog`, manual review
- **Evidence**: No Azure keys, OAuth secrets in Git history

### 11. Tracing: 100% Tool Executions
- **Metric**: Every tool execution logged to Application Insights
- **Tool**: Application Insights trace query
- **Evidence**: Query returns 100% execution traces

### 12. Error Recovery: < 5s
- **Metric**: Time to recover from MCP client disconnect
- **Tool**: Custom disconnect/reconnect test
- **Evidence**: Client reconnects and resumes in < 5 seconds

---

## 7. Implementation Phases (4 Phases, 6 Weeks)

### Phase 1: MCP Server Foundation (Weeks 1-2)

**Goal**: Basic MCP server with tool discovery and execution

**Tasks**:
1. Setup FastAPI project structure
2. Implement MCP server session handler (`/mcp/initialize`, `/mcp/tools`, `/mcp/tools/execute`)
3. Create tool registry with dynamic tool loading
4. Build base tool interface (`BaseTool` ABC)
5. Write 3 example tools:
   - `cosmos_db_query`: Query Cosmos DB by tenant ID
   - `azure_resource_list`: List Azure resources
   - `git_status`: Get Git repository status
6. Unit tests: 80%+ coverage for server, registry, base tool

**Deliverables**:
- MCP server operational (FastAPI running on port 8080)
- Tool registry discovers and loads tools
- 3 example tools working
- Unit tests passing

**Evidence**:
- `curl http://localhost:8080/mcp/tools` returns tool list
- `pytest` shows 80%+ coverage
- Tool execution returns valid JSON

---

### Phase 2: OAuth 2.1 Integration (Weeks 3-4)

**Goal**: Secure tool access with Azure AD B2C OAuth

**Tasks**:
1. Implement OAuth provider (`oauth.py`)
2. Dynamic client registration with Azure AD B2C
3. Token validation and refresh logic
4. Store OAuth client secrets in Azure Key Vault
5. RBAC: Tool permission checking based on user roles
6. Update MCP server to validate Bearer tokens
7. Integration tests: OAuth flow (register → authorize → token → refresh)

**Deliverables**:
- OAuth 2.1 authentication working
- Client registration with Azure AD B2C
- Token refresh before expiration
- RBAC enforced for protected tools

**Evidence**:
- OAuth flow completes successfully
- Protected tools reject unauthorized users
- Token refresh works without manual intervention
- Key Vault stores client secrets

---

### Phase 3: Tool Library Expansion (Week 5)

**Goal**: Build comprehensive tool library for EVA Suite

**Tasks**:
1. Cosmos DB tools:
   - `cosmos_db_query`: Query documents
   - `cosmos_db_insert`: Insert document
   - `cosmos_db_update`: Update document
   - `cosmos_db_delete`: Delete document
2. Azure Resource Manager tools:
   - `azure_resource_list`: List resources in subscription
   - `azure_resource_deploy`: Deploy ARM template
   - `azure_resource_delete`: Delete resource group
3. Git operations tools:
   - `git_clone`: Clone repository
   - `git_commit`: Commit changes
   - `git_push`: Push to remote
4. Documentation search:
   - `docs_search`: RAG query across docs/
   - `docs_summarize`: Summarize document
5. Localization:
   - `translate`: EN ↔ FR translation
6. Telemetry:
   - `send_metric`: Send custom metric to Application Insights

**Deliverables**:
- 15+ production-ready tools
- All tools tested (unit + integration)
- Tool catalog documentation

**Evidence**:
- All tools return valid results
- Test report shows 100% passing
- Tool catalog lists all tools with examples

---

### Phase 4: Production Hardening (Week 6)

**Goal**: Deploy to Azure, observability, monitoring

**Tasks**:
1. Dockerize MCP server (`Dockerfile`, `docker-compose.yml`)
2. Deploy to Azure Container Apps
3. Configure Application Insights (distributed tracing, custom metrics)
4. Setup Grafana dashboards:
   - Tool execution latency
   - Success/failure rate
   - Concurrent client connections
5. Load testing (`locust` with 100+ clients)
6. Write deployment guide (DEPLOYMENT.md)
7. Write tool catalog (TOOLS.md)
8. Final security scan (trufflehog, Dependabot)

**Deliverables**:
- MCP server deployed to Azure Container Apps
- Application Insights tracing operational
- Grafana dashboards showing metrics
- All 12 quality gates passed

**Evidence**:
- Azure Portal shows running container
- Application Insights traces visible
- Grafana dashboards populated
- Load test report showing 100+ clients

---

## 8. References

### MCP Protocol
- **Official Docs**: https://modelcontextprotocol.io/
- **Python SDK**: https://github.com/anthropics/mcp-python
- **Specification**: https://spec.modelcontextprotocol.io/

### Reference Implementations
- **OpenWebUI MCP Client**: `OpenWebUI/backend/open_webui/utils/mcp/client.py`
- **OpenWebUI Middleware Integration**: `OpenWebUI/backend/open_webui/utils/middleware.py` (lines 1325-1451)
- **OpenWebUI Tool Server Config**: `OpenWebUI/backend/open_webui/routers/configs.py` (lines 142-265)

### Azure Services
- **Azure AD B2C OAuth**: https://learn.microsoft.com/azure/active-directory-b2c/
- **Azure Key Vault**: https://learn.microsoft.com/azure/key-vault/
- **Application Insights**: https://learn.microsoft.com/azure/azure-monitor/app/app-insights-overview

### EVA Architecture
- **MCP & Agent Strategy**: `eva-orchestrator/docs/reference/mcp-and-agents-overview.md`
- **EVA Orchestrator**: Workspace orchestration and session management

---

## 9. Tool Catalog (Example Tools)

### Cosmos DB Tools

**cosmos_db_query**
- **Description**: Query Cosmos DB documents by tenant ID
- **Input**: `tenant_id`, `container`, `query`, `max_items`
- **Output**: `items[]`, `count`, `continuation_token`
- **Required Roles**: `admin`, `developer`

**cosmos_db_insert**
- **Description**: Insert new document into Cosmos DB
- **Input**: `tenant_id`, `container`, `document`
- **Output**: `id`, `created_at`
- **Required Roles**: `admin`, `developer`

### Azure Resource Manager Tools

**azure_resource_list**
- **Description**: List all Azure resources in subscription
- **Input**: `resource_group` (optional), `resource_type` (optional)
- **Output**: `resources[]` (id, name, type, location)
- **Required Roles**: `admin`

**azure_resource_deploy**
- **Description**: Deploy ARM template to resource group
- **Input**: `resource_group`, `template_url`, `parameters`
- **Output**: `deployment_id`, `status`, `outputs`
- **Required Roles**: `admin`

### Git Operations Tools

**git_clone**
- **Description**: Clone Git repository
- **Input**: `repo_url`, `branch`, `target_dir`
- **Output**: `commit_hash`, `cloned_at`
- **Required Roles**: `developer`

**git_commit**
- **Description**: Commit changes to Git repository
- **Input**: `repo_dir`, `message`, `files[]`
- **Output**: `commit_hash`, `committed_at`
- **Required Roles**: `developer`

### Documentation Tools

**docs_search**
- **Description**: RAG search across EVA documentation
- **Input**: `query`, `max_results`
- **Output**: `results[]` (file_path, snippet, score)
- **Required Roles**: None (public)

**docs_summarize**
- **Description**: Summarize documentation file
- **Input**: `file_path`, `max_length`
- **Output**: `summary`, `key_points[]`
- **Required Roles**: None (public)

### Localization Tools

**translate**
- **Description**: Translate text between English and French
- **Input**: `text`, `source_lang`, `target_lang`
- **Output**: `translated_text`, `confidence`
- **Required Roles**: None (public)

### Telemetry Tools

**send_metric**
- **Description**: Send custom metric to Application Insights
- **Input**: `metric_name`, `value`, `properties`
- **Output**: `sent_at`, `status`
- **Required Roles**: `developer`

---

## 10. Deployment Guide

### Local Development

**1. Install Dependencies**:
```bash
cd eva-mcp
poetry install
```

**2. Configure Environment Variables**:
```bash
# .env
MCP_SERVER_URL=http://localhost:8080
COSMOS_CONNECTION_STRING=<from Azure Portal>
AZURE_AD_B2C_ISSUER=https://evab2c.b2clogin.com/evab2c.onmicrosoft.com/v2.0/.well-known/openid-configuration
KEY_VAULT_URL=https://eva-suite-kv-dev.vault.azure.net/
APPLICATION_INSIGHTS_CONNECTION_STRING=<from Azure Portal>
```

**3. Run MCP Server**:
```bash
poetry run uvicorn eva_mcp.server:app --reload --host 0.0.0.0 --port 8080
```

**4. Test Tool Discovery**:
```bash
curl http://localhost:8080/mcp/tools
```

### Azure Container Apps Deployment

**1. Build Docker Image**:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --no-dev

COPY src/ ./src/

CMD ["poetry", "run", "uvicorn", "eva_mcp.server:app", "--host", "0.0.0.0", "--port", "8080"]
```

**2. Push to Azure Container Registry**:
```bash
az acr build --registry evacr --image eva-mcp:latest .
```

**3. Deploy to Container Apps**:
```bash
az containerapp create \
  --name eva-mcp \
  --resource-group eva-suite-rg \
  --image evacr.azurecr.io/eva-mcp:latest \
  --environment eva-container-env \
  --target-port 8080 \
  --ingress external \
  --env-vars \
    MCP_SERVER_URL=https://eva-mcp.azurecontainerapps.io \
    COSMOS_CONNECTION_STRING=secretref:cosmos-connection-string \
    KEY_VAULT_URL=https://eva-suite-kv-prod.vault.azure.net/
```

**4. Configure Secrets**:
```bash
az containerapp secret set \
  --name eva-mcp \
  --resource-group eva-suite-rg \
  --secrets cosmos-connection-string=<value>
```

---

## 11. Next Steps

1. **Marco Opens eva-mcp Workspace**:
   ```powershell
   cd "C:\Users\marco\Documents\_AI Dev\EVA Suite"
   code eva-mcp
   ```

2. **Run Startup Script**:
   ```powershell
   .\_MARCO-use-this-to-tell_copilot-to-read-repo-specific-instructions.ps1
   ```

3. **Give Task**:
   ```
   Implement Phase 1: MCP Server Foundation (tool discovery and execution).
   Follow specification TO THE LETTER.
   Use OpenWebUI MCP client patterns (utils/mcp/client.py).
   Create FastAPI server with /mcp/initialize, /mcp/tools, /mcp/tools/execute endpoints.
   Build tool registry with dynamic loading.
   Write 3 example tools (Cosmos DB query, Azure resource list, Git status).
   Show curl test results + pytest coverage report when done.
   ```

---

**END OF SPECIFICATION**
