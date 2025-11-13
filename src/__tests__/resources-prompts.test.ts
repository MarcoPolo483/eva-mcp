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
function nextMessage(stream: PassThrough): any {
  const raw = stream.read() as Buffer;
  const headerEnd = raw.indexOf("\r\n\r\n");
  if (headerEnd === -1) {
    throw new Error("Invalid frame: missing header terminator");
  }
  const header = raw.subarray(0, headerEnd).toString();
  const lengthMatch = header.match(/Content-Length:\s*(\d+)/i);
  if (!lengthMatch) {
    throw new Error("Invalid frame: missing Content-Length");
  }
  const contentLength = Number.parseInt(lengthMatch[1] ?? "0", 10);
  const bodyStart = headerEnd + 4;
  const bodyEnd = bodyStart + contentLength;
  const body = raw.subarray(bodyStart, bodyEnd).toString();
  const remainder = raw.subarray(bodyEnd);
  if (remainder.length > 0) {
    stream.unshift(remainder);
  }
  return JSON.parse(body);
}

describe("Resources and Prompts", () => {
  let dir: string;

  beforeAll(() => {
    dir = mkdtempSync(join(tmpdir(), "eva-mcp-"));
    writeFileSync(join(dir, "a.txt"), "hello");
    writeFileSync(join(dir, "b.txt"), "world");
    process.env.EVA_MCP_WORKSPACE = dir;
  });

  afterAll(() => {
    rmSync(dir, { recursive: true, force: true });
    delete process.env.EVA_MCP_WORKSPACE;
  });

  it("lists and reads file resources", async () => {
    const input = new PassThrough();
    const output = new PassThrough();
    const srv = new MCPServer({ inStream: input, outStream: output });
    setImmediate(() => {
      input.write(frame({ jsonrpc: "2.0", id: 1, method: "resources/list" }));
      input.write(frame({ jsonrpc: "2.0", id: 2, method: "resources/read", params: { uri: "file:///a.txt" } }));
      input.end();
    });
    await srv.run();

    const list = nextMessage(output);
    expect(list.result.resources.some((r: any) => r.uri.startsWith("file:///"))).toBe(true);

    const read = nextMessage(output);
    expect(read.result.text).toBe("hello");
  });

  it("lists and gets prompts", async () => {
    const input = new PassThrough();
    const output = new PassThrough();
    const srv = new MCPServer({ inStream: input, outStream: output });
    setImmediate(() => {
      input.write(frame({ jsonrpc: "2.0", id: 1, method: "prompts/list" }));
      input.write(frame({ jsonrpc: "2.0", id: 2, method: "prompts/get", params: { name: "summarize", variables: { text: "abc" } } }));
      input.end();
    });
    await srv.run();

    const list = nextMessage(output);
    expect(list.result.prompts.some((p: any) => p.name === "summarize")).toBe(true);

    const get = nextMessage(output);
    const msg = get.result.prompt.messages[0];
    expect(msg.content).toMatch(/abc/);
  });
});