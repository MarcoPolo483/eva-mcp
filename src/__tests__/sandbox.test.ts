import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { mkdtempSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createSandbox } from "../util/sandbox.js";

describe("Sandbox security and listing", () => {
  let dir: string;
  beforeAll(() => {
    dir = mkdtempSync(join(tmpdir(), "eva-mcp-sb-"));
    mkdirSync(join(dir, "sub"));
    writeFileSync(join(dir, "a.txt"), "A");
    writeFileSync(join(dir, "sub", "b.txt"), "B");
  });
  afterAll(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it("blocks path traversal outside workspace", async () => {
    const sb = createSandbox(dir);
    await expect(sb.read("../outside.txt")).rejects.toThrow(/outside workspace/i);
  });

  it("lists recursively but respects max cap", async () => {
    const sb = createSandbox(dir);
    const list1 = await sb.list(1);
    expect(list1.length).toBe(1);
    const list2 = await sb.list(10);
    // Should include both a.txt and sub/b.txt (order unspecified)
    expect(list2.join(",")).toMatch(/a\.txt/);
    expect(list2.join(",")).toMatch(/sub[\/\\]b\.txt/); // Allow both / and \ separators
  });

  it("errors when reading a directory", async () => {
    const sb = createSandbox(dir);
    await expect(sb.read("sub")).rejects.toThrow(/Not a file/);
  });
});