import type { ToolRegistry } from "./registry.js";

export function registerBuiltInTools(reg: ToolRegistry) {
  reg.register(
    { name: "ping", description: "Ping the server", inputSchema: { type: "object", properties: { message: { type: "string" } } } },
    async (args) => {
      const m = (args as any)?.message ?? "pong";
      return { content: [{ type: "text", text: String(m) }] };
    }
  );

  reg.register(
    { name: "echo", description: "Echo text", inputSchema: { type: "object", properties: { text: { type: "string" } }, required: ["text"] } },
    async (args) => {
      const t = (args as any)?.text;
      return { content: [{ type: "text", text: String(t ?? "") }] };
    }
  );

  reg.register(
    { name: "time", description: "Get server time", inputSchema: { type: "object", properties: {} } },
    async (_args, ctx) => {
      return { content: [{ type: "text", text: ctx.now() }] };
    }
  );
}