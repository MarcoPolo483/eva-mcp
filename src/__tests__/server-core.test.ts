import { describe, it, expect } from "vitest";
import { PassThrough, Readable } from "node:stream";
import { MCPServer } from "../server.js";

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

describe("MCPServer core", () => {
  it("handles initialize and shutdown", async () => {
    const msg1 = frame({ jsonrpc: "2.0", id: 1, method: "initialize", params: {} });
    const msg2 = frame({ jsonrpc: "2.0", id: 2, method: "shutdown", params: {} });
    const combined = Buffer.concat([msg1, msg2]);
    
    // Use Readable.from to create a proper readable stream from buffer
    const input = Readable.from([combined]);
    const output = new PassThrough();
    const srv = new MCPServer({ inStream: input, outStream: output });
    
    await srv.run();

    const first = nextMessage(output);
    expect(first.id).toBe(1);
    expect(first.result?.capabilities?.tools?.list).toBe(true);
    const second = nextMessage(output);
    expect(second.id).toBe(2);
  });

  it("lists tools and calls echo", async () => {
    const msg1 = frame({ jsonrpc: "2.0", id: 1, method: "tools/list" });
    const msg2 = frame({ jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: "echo", arguments: { text: "hi" } } });
    const combined = Buffer.concat([msg1, msg2]);
    
    const input = Readable.from([combined]);
    const output = new PassThrough();
    const srv = new MCPServer({ inStream: input, outStream: output });
    
    await srv.run();
    
    const list = nextMessage(output);
    expect(list.result.tools.some((t: any) => t.name === "echo")).toBe(true);
    const call = nextMessage(output);
    expect(call.result.content[0].text).toBe("hi");
  });

  it("returns method not found for unknown method", async () => {
    const input = Readable.from([frame({ jsonrpc: "2.0", id: 3, method: "unknown/method" })]);
    const output = new PassThrough();
    const srv = new MCPServer({ inStream: input, outStream: output });
    
    await srv.run();
    
    const msg = nextMessage(output);
    expect(msg.error.code).toBe(-32601);
  });
});