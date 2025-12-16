# EVA-MCP: Model Context Protocol Server

**EVA-MCP** exposes EVA Suite tools to AI agents via the Model Context Protocol (MCP) over HTTP/SSE.

## Features

- **Tool Discovery**: List available tools with JSON schemas (< 100ms)
- **Tool Execution**: Execute tools with validated arguments (99%+ success)
- **RBAC**: Role-based access control per tool
- **Dynamic Loading**: Tools auto-discovered from `src/eva_mcp/tools/`
- **FastAPI Server**: HTTP/SSE endpoints for MCP clients

## Phase 1: MCP Server Foundation

### Implemented Components

1. **FastAPI MCP Server** (`src/eva_mcp/server.py`)
   - `POST /mcp/initialize` - Create session
   - `GET /mcp/tools` - List tools with schemas
   - `POST /mcp/tools/execute` - Execute tool with args
   - `GET /health` - Health check

2. **Tool Registry** (`src/eva_mcp/tools/registry.py`)
   - Dynamic tool loading
   - RBAC filtering
   - Lifecycle management

3. **Base Tool Interface** (`src/eva_mcp/tools/base.py`)
   - Abstract base class for all tools
   - Input/output schema validation
   - Standard lifecycle (initialize, execute, cleanup)

4. **Example Tools**
   - `cosmos_db_query` - Query Cosmos DB by tenant ID
   - `azure_resource_list` - List Azure resources
   - `git_status` - Get Git repository status

## Quick Start

### 1. Install Dependencies

```bash
poetry install --no-root
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your Azure credentials
```

### 3. Run Server

```bash
poetry run python -m eva_mcp.server
```

Server starts on `http://localhost:8080`

### 4. Test with curl

```bash
# Initialize session
curl -X POST http://localhost:8080/mcp/initialize \
  -H "Content-Type: application/json" \
  -d '{"client_id": "test-client"}'

# List tools
curl http://localhost:8080/mcp/tools \
  -H "X-Session-Id: <session-id>"

# Execute tool
curl -X POST http://localhost:8080/mcp/tools/execute \
  -H "Content-Type: application/json" \
  -H "X-Session-Id: <session-id>" \
  -d '{"tool_name": "git_status", "arguments": {"repo_dir": "."}}'
```

## Testing

```bash
# Run all tests with coverage
poetry run pytest --cov=src/eva_mcp --cov-report=term-missing

# Run specific test file
poetry run pytest tests/test_server.py -v
```

## Project Structure

```
eva-mcp/
├── src/eva_mcp/
│   ├── server.py          # FastAPI MCP server
│   ├── config.py          # Configuration management
│   └── tools/
│       ├── base.py        # BaseTool ABC
│       ├── registry.py    # Tool registry
│       ├── cosmos_db_query.py
│       ├── azure_resource_list.py
│       └── git_status.py
├── tests/                 # Unit tests
├── docs/
│   └── SPECIFICATION.md   # Complete requirements
├── pyproject.toml
└── .env.example
```

## Development

### Adding a New Tool

1. Create file in `src/eva_mcp/tools/your_tool.py`
2. Inherit from `BaseTool`
3. Implement required properties and methods
4. Tool is auto-discovered on server startup

```python
from eva_mcp.tools.base import BaseTool
from pydantic import BaseModel, Field

class YourToolInput(BaseModel):
    param: str = Field(description="Parameter description")

class YourTool(BaseTool):
    name = "your_tool"
    description = "Tool description"
    input_schema = YourToolInput
    required_roles = ["admin"]  # Or [] for public
    
    async def execute(self, args, user_id=None):
        return {"result": f"Executed with {args.param}"}
```

## Next Steps (Phase 2+)

- [ ] OAuth 2.1 authentication with Azure AD B2C
- [ ] Application Insights distributed tracing
- [ ] Additional tools (15+ total)
- [ ] Deploy to Azure Container Apps
- [ ] Load testing (100+ concurrent clients)

## Documentation

- **Full Specification**: `docs/SPECIFICATION.md`
- **Memory File**: `.eva-memory.json`
- **Copilot Instructions**: `.github/copilot-instructions.md`

## License

EVA Suite - Internal Use Only

<!-- Phase 3 enforcement system test -->
