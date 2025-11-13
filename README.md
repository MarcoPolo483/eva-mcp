# eva-mcp (Enterprise Edition)

A dependency-free Node MCP server (stdio) implementing:
- JSON-RPC 2.0 with Content-Length framing
- MCP methods:
  - initialize, shutdown
  - tools/list, tools/call
  - resources/list, resources/read
  - prompts/list, prompts/get
- Tool, Resource, Prompt registries
- Secure file resource access rooted at EVA_MCP_WORKSPACE (default: cwd)
- Structured logging to stderr (never pollutes stdout/protocol)
- ESLint v9 flat config, Prettier, Vitest 80%+ coverage, Husky

Quick start
```bash
npm ci
npm run build
node dist/server.js
# The process speaks MCP over stdio; use your MCP-compatible client.
```

Built-in tools
- ping: { message?: string } → echoes
- echo: { text: string } → echoes text
- time: {} → returns ISO timestamp

Resources (file://)
- resources/list → lists files under EVA_MCP_WORKSPACE (depth-first)
- resources/read → returns text content

Prompts
- Simple templating with {{var}} replacement
- prompts/list → names and variables
- prompts/get → resolved content

Security
- File access is sandboxed under EVA_MCP_WORKSPACE; path traversal is blocked.
- Error details are concise by default; server logs stack traces to stderr.

Testing
```bash
npm run test:coverage
```

License
MIT