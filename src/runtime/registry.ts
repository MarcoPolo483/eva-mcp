import type { Json, ToolDef, ToolResult, ResourceDef, PromptDef } from "../protocol/types.js";

export type ToolHandler = (args: Json | undefined, ctx: { now: () => string }) => Promise<ToolResult> | ToolResult;

export class ToolRegistry {
  private tools = new Map<string, { def: ToolDef; handler: ToolHandler }>();

  register(def: ToolDef, handler: ToolHandler) {
    this.tools.set(def.name, { def, handler });
    return this;
  }

  list(): ToolDef[] {
    return Array.from(this.tools.values()).map((t) => t.def);
  }

  async call(name: string, args: Json | undefined): Promise<ToolResult> {
    const t = this.tools.get(name);
    if (!t) {
      return { content: [{ type: "text", text: `Tool not found: ${name}` }], isError: true };
    }
    return t.handler(args, { now: () => new Date().toISOString() });
  }
}

export class ResourceRegistry {
  private resources: ResourceDef[] = [];
  private readers = new Map<string, (uri: string) => Promise<{ uri: string; mimeType?: string; text?: string }>>();

  register(def: ResourceDef, reader: (uri: string) => Promise<{ uri: string; mimeType?: string; text?: string }>) {
    this.resources.push(def);
    this.readers.set(def.uri, reader);
    return this;
  }

  list(): ResourceDef[] {
    return this.resources.slice();
  }

  async read(uri: string) {
    const match = this.resources.find((r) => r.uri === uri) ?? this.resources.find((r) => uri.startsWith(r.uri));
    if (!match) throw new Error("Resource not found");
    const reader = this.readers.get(match.uri);
    if (!reader) throw new Error("Reader missing");
    return reader(uri);
  }
}

export class PromptRegistry {
  private prompts = new Map<string, { def: PromptDef; template: string }>();

  register(def: PromptDef, template: string) {
    this.prompts.set(def.name, { def, template });
    return this;
  }

  list(): PromptDef[] {
    return Array.from(this.prompts.values()).map((p) => p.def);
  }

  get(name: string, variables: Record<string, string | number | boolean> = {}) {
    const p = this.prompts.get(name);
    if (!p) throw new Error("Prompt not found");
    const content = renderTemplate(p.template, variables);
    return { name, content };
  }
}

function renderTemplate(tpl: string, vars: Record<string, string | number | boolean>): string {
  return tpl.replace(/\{\{(\w+)\}\}/g, (_, k) => String(vars[k] ?? ""));
}