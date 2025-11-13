import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { PassThrough } from "node:stream";
import { MCPServer } from "../server.js";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

function frame(obj: any): Buffer {
  const s = JSON.stringify(obj);
  const h = `Content-Length: ${Buffer.byteLength(s)}\r\n\r\n`;
  return Buffer.concat([Buffer.from(h), Buffer.from(s)]);
}
function readOne(stream: PassThrough) {
  const raw = stream.read() as Buffer;
  const s = String(raw);
  const idx = s.indexOf("\r\n\r\n");
  return JSON.parse(s.slice(idx + 4));
}

describe("File resource listing via resources/read file:///", () => {
  let dir: string;
  beforeAll(() => {
    dir = mkdtempSync(join(tmpdir(), "eva-mcp-res-"));
    writeFileSync(join(dir, "a.txt"), "hello");
    writeFileSync(join(dir, "b.md"), "world");
    process.env.EVA_MCP_WORKSPACE = dir;
  });
  afterAll(() => {
    rmSync(dir, { recursive: true, force: true });
    delete process.env.EVA_MCP_WORKSPACE;
  });

  it("returns newline-separated listing", async () => {
    const input = new PassThrough();
    const output = new PassThrough();
    const srv = new MCPServer({ inStream: input, outStream: output });

    setImmediate(() => {
      input.write(frame({ jsonrpc: "2.0", id: 1, method: "resources/read", params: { uri: "file:///" } }));
      input.end();
    });

    await srv.run();
    const resp = readOne(output);
    const listing = String(resp.result.text);
    expect(listing).toMatch(/a\.txt/);
    expect(listing).toMatch(/b\.md/);
  });
});