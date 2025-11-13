import { resolve, sep } from "node:path";
import { stat, readdir, readFile } from "node:fs/promises";

export type Sandbox = {
  root: string;
  list: (max: number) => Promise<string[]>;
  read: (path: string) => Promise<{ path: string; content: string }>;
};

export function createSandbox(root?: string): Sandbox {
  const base = resolve(root ?? process.env.EVA_MCP_WORKSPACE ?? process.cwd());

  async function safeResolve(p: string): Promise<string> {
    const abs = resolve(base, p);
    if (!abs.startsWith(base + sep) && abs !== base) {
      throw new Error("Path outside workspace");
    }
    return abs;
  }

  async function list(max: number): Promise<string[]> {
    const out: string[] = [];
    async function walk(dir: string) {
      const items = await readdir(dir, { withFileTypes: true });
      for (const it of items) {
        if (out.length >= max) return;
        const full = resolve(dir, it.name);
        const rel = full.slice(base.length + 1);
        if (it.isDirectory()) {
          await walk(full);
        } else if (it.isFile()) {
          out.push(rel);
        }
      }
    }
    await walk(base);
    return out;
  }

  async function read(p: string) {
    const abs = await safeResolve(p);
    const st = await stat(abs);
    if (!st.isFile()) throw new Error("Not a file");
    const content = await readFile(abs, "utf8");
    return { path: p, content };
  }

  return { root: base, list, read };
}