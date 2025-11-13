import { describe, it, expect } from "vitest";
import { PassThrough } from "node:stream";
import { MCPServer } from "../server.js";

function frame(obj: any): Buffer {
  const s = JSON.stringify(obj);
  const h = `Content-Length: ${Buffer.byteLength(s)}\r\n\r\n`;
  return Buffer.concat([Buffer.from(h), Buffer.from(s)]);
}
function readAll(stream: PassThrough) {
  const bufs: Buffer[] = [];
  let chunk: Buffer | null;
  while ((chunk = stream.read() as Buffer | null)) {
    bufs.push(chunk);
  }
  let remaining = Buffer.concat(bufs);
  const messages: any[] = [];
  while (remaining.length) {
    const headerEnd = remaining.indexOf("\r\n\r\n");
    if (headerEnd === -1) {
      break;
    }
    const header = remaining.subarray(0, headerEnd).toString();
    const lengthMatch = header.match(/Content-Length:\s*(\d+)/i);
    if (!lengthMatch) {
      break;
    }
    const contentLength = Number.parseInt(lengthMatch[1] ?? "0", 10);
    const bodyStart = headerEnd + 4;
    const bodyEnd = bodyStart + contentLength;
    if (remaining.length < bodyEnd) {
      break;
    }
    const body = remaining.subarray(bodyStart, bodyEnd).toString();
    messages.push(JSON.parse(body));
    remaining = remaining.subarray(bodyEnd);
  }
  return messages;
}

describe("Server stops processing after shutdown", () => {
  it("ignores subsequent messages post-shutdown", async () => {
    const input = new PassThrough();
    const output = new PassThrough();
    const srv = new MCPServer({ inStream: input, outStream: output });

    setImmediate(() => {
      input.write(frame({ jsonrpc: "2.0", id: 1, method: "initialize" }));
      input.write(frame({ jsonrpc: "2.0", id: 2, method: "shutdown" }));
      // This should NOT be handled since server will stop after shutdown
      input.write(frame({ jsonrpc: "2.0", id: 3, method: "tools/list" }));
      input.end();
    });

    await srv.run();
    const msgs = readAll(output);
    const ids = msgs.map((m: any) => m.id);
    expect(ids).toEqual([1, 2]); // no message with id 3
  });
});