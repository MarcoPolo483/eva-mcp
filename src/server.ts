import { FramedJSONRPC } from "./util/jsonrpc.js";
import type { JSONRPCRequest, JSONRPCResponse, ToolDef, ToolResult, ResourceDef, PromptDef } from "./protocol/types.js";
import { ToolRegistry, ResourceRegistry, PromptRegistry } from "./runtime/registry.js";
import { registerBuiltInTools } from "./runtime/tools.js";
import { registerFileResources } from "./runtime/resources.js";
import { registerPrompts } from "./runtime/prompts.js";
import { PassThrough } from "node:stream";

export type ServerOptions = {
  inStream?: NodeJS.ReadableStream;
  outStream?: NodeJS.WritableStream;
  tools?: (reg: ToolRegistry) => void;
  resources?: (reg: ResourceRegistry) => void;
  prompts?: (reg: PromptRegistry) => void;
  serverName?: string;
  serverVersion?: string;
};

export class MCPServer {
  private rpc: FramedJSONRPC;
  private tools = new ToolRegistry();
  private resources = new ResourceRegistry();
  private prompts = new PromptRegistry();
  private shuttingDown = false;

  constructor(private readonly opts: ServerOptions = {}) {
    const input = (opts.inStream as any) ?? process.stdin;
    const output = (opts.outStream as any) ?? process.stdout;
    this.rpc = new FramedJSONRPC(input, output);

    // Register built-ins
    registerBuiltInTools(this.tools);
    registerFileResources(this.resources);
    registerPrompts(this.prompts);

    // Allow custom registrations
    opts.tools?.(this.tools);
    opts.resources?.(this.resources);
    opts.prompts?.(this.prompts);
  }

  async run(): Promise<void> {
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const msg = await this.rpc.read();
      if (!msg) break;
      if ((msg as any)?.method === "__internal_parse_error__") {
        this.sendError(null, -32700, "Parse error", (msg as any).params);
        continue;
      }
      await this.handle(msg as JSONRPCRequest);
      if (this.shuttingDown) break;
    }
  }

  private async handle(req: JSONRPCRequest) {
    const id = req.id ?? null;
    try {
      switch (req.method) {
        case "initialize": {
          const result = {
            protocolVersion: "2024-11-01",
            serverInfo: {
              name: this.opts.serverName ?? "eva-mcp",
              version: this.opts.serverVersion ?? "0.1.0"
            },
            capabilities: {
              tools: { list: true, call: true },
              resources: { list: true, read: true, supportedSchemes: ["file"] },
              prompts: { list: true, get: true }
            }
          };
          this.send({ jsonrpc: "2.0", id, result });
          break;
        }
        case "shutdown": {
          this.shuttingDown = true;
          this.send({ jsonrpc: "2.0", id, result: null });
          break;
        }
        case "tools/list": {
          const tools = this.tools.list();
          this.send({ jsonrpc: "2.0", id, result: { tools } });
          break;
        }
        case "tools/call": {
          const { name, arguments: args } = (req.params as any) ?? {};
          const toolRes = await this.tools.call(String(name), args);
          this.send({ jsonrpc: "2.0", id, result: toolRes });
          break;
        }
        case "resources/list": {
          const resources = this.resources.list();
          this.send({ jsonrpc: "2.0", id, result: { resources } });
          break;
        }
        case "resources/read": {
          const { uri } = (req.params as any) ?? {};
          if (!uri) throw new Error("uri required");
          const res = await this.resources.read(String(uri));
          this.send({ jsonrpc: "2.0", id, result: res });
          break;
        }
        case "prompts/list": {
          const prompts = this.prompts.list();
          this.send({ jsonrpc: "2.0", id, result: { prompts } });
          break;
        }
        case "prompts/get": {
          const { name, variables } = (req.params as any) ?? {};
          if (!name) throw new Error("name required");
          const p = this.prompts.get(String(name), (variables as any) ?? {});
          this.send({ jsonrpc: "2.0", id, result: { prompt: { name: p.name, messages: [{ role: "system", content: p.content }] } } });
          break;
        }
        default:
          this.sendError(id, -32601, "Method not found", { method: req.method });
      }
    } catch (e: any) {
      this.sendError(id, -32000, e?.message || "Server error");
      logErr("Handler error:", e?.stack || e?.message || e);
    }
  }

  private send(resp: JSONRPCResponse) {
    this.rpc.write(resp);
  }
  private sendError(id: number | string | null, code: number, message: string, data?: any) {
    this.rpc.write({ jsonrpc: "2.0", id, error: { code, message, ...(data ? { data } : {}) } });
  }
}

function logErr(...args: any[]) {
  try {
    process.stderr.write(args.join(" ") + "\n");
  } catch {
    // ignore
  }
}

// Entry (only when launched directly)
if (process.argv[1] && process.argv[1].endsWith("server.js")) {
  const srv = new MCPServer();
  // Do not await; keep process alive while reading
  void srv.run();
}