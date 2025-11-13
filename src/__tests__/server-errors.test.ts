import { describe, it, expect } from "vitest";
import { PassThrough } from "node:stream";
import { MCPServer } from "../server.js";

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

describe("Server error responses for missing params and unknown tools", () => {
  it("tools/call unknown tool returns isError result", async () => {
    const input = new PassThrough();
    const output = new PassThrough();
    const srv = new MCPServer({ inStream: input, outStream: output });

    setImmediate(() => {
      input.write(frame({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "nope", arguments: {} } }));
      input.end();
    });

    await srv.run();
    const resp = readOne(output);
    expect(resp.result.isError).toBe(true);
    expect(resp.result.content[0].text).toMatch(/Tool not found/);
  });

  it("resources/read without uri yields JSON-RPC error", async () => {
    const input = new PassThrough();
    const output = new PassThrough();
    const srv = new MCPServer({ inStream: input, outStream: output });

    setImmediate(() => {
      input.write(frame({ jsonrpc: "2.0", id: 2, method: "resources/read", params: {} }));
      input.end();
    });

    await srv.run();
    const resp = readOne(output);
    expect(resp.error).toBeDefined();
    expect(resp.error.code).toBe(-32000);
    expect(resp.error.message).toMatch(/uri required/);
  });

  it("prompts/get without name yields JSON-RPC error", async () => {
    const input = new PassThrough();
    const output = new PassThrough();
    const srv = new MCPServer({ inStream: input, outStream: output });

    setImmediate(() => {
      input.write(frame({ jsonrpc: "2.0", id: 3, method: "prompts/get", params: {} }));
      input.end();
    });

    await srv.run();
    const resp = readOne(output);
    expect(resp.error).toBeDefined();
    expect(resp.error.code).toBe(-32000);
    expect(resp.error.message).toMatch(/name required/);
  });
});