import type { ResourceRegistry } from "./registry.js";
import { createSandbox } from "../util/sandbox.js";

export function registerFileResources(reg: ResourceRegistry, opts?: { root?: string; maxList?: number }) {
  const sandbox = createSandbox(opts?.root);
  const max = Math.max(1, Number(process.env.EVA_MCP_MAX_LIST ?? opts?.maxList ?? 1000));

  reg.register(
    { uri: "file:///", name: "Workspace files", description: "Files under workspace root", mimeType: "text/plain" },
    async (uri) => {
      // uri can be like file:///relative/path or file:/// for listing
      if (uri === "file:///") {
        const items = await sandbox.list(max);
        // Return a virtual concatenation as text listing
        const content = items.join("\n");
        return { uri, mimeType: "text/plain", text: content };
      }
      const rel = uri.replace("file:///", "");
      const { content } = await sandbox.read(rel);
      return { uri, mimeType: "text/plain", text: content };
    }
  );
}