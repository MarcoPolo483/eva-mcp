import { describe, it, expect } from "vitest";
import { ToolRegistry, ResourceRegistry, PromptRegistry } from "../runtime/registry.js";

describe("Registries cover success and error paths", () => {
  it("ToolRegistry: register/list/call and missing tool error result", async () => {
    const tools = new ToolRegistry();
    tools.register(
      { name: "add", description: "sum two", inputSchema: {} },
      async (args: any) => {
        const a = Number(args?.a ?? 0);
        const b = Number(args?.b ?? 0);
        return { content: [{ type: "text", text: String(a + b) }] };
      }
    );

    expect(tools.list().some(t => t.name === "add")).toBe(true);

    const ok = await tools.call("add", { a: 2, b: 3 });
    expect(ok.content[0].text).toBe("5");

    const missing = await tools.call("nope", {});
    expect(missing.isError).toBe(true);
    expect(missing.content[0].text).toMatch(/not found/i);
  });

  it("ResourceRegistry: register/list/read and error on unknown", async () => {
    const res = new ResourceRegistry();
    res.register({ uri: "mem://", name: "mem" }, async (uri: string) => {
      if (uri === "mem:///") return { uri, mimeType: "text/plain", text: "list" };
      return { uri, mimeType: "text/plain", text: "content:" + uri };
    });

    expect(res.list().length).toBe(1);
    const r1 = await res.read("mem:///x");
    expect(r1.text).toMatch(/content:mem:\/\/\/x/);

    await expect(res.read("other:///x")).rejects.toThrow(/not found/i);
  });

  it("PromptRegistry: get ok and error on missing", () => {
    const pr = new PromptRegistry();
    pr.register({ name: "greet", description: "greet", variables: [{ name: "name", required: true }] }, "Hello {{name}}!");
    const p = pr.get("greet", { name: "Ada" });
    expect(p.content).toBe("Hello Ada!");
    expect(() => pr.get("missing", {})).toThrow(/not found/i);
  });
});