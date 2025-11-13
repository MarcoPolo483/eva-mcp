import { describe, it, expect } from "vitest";
import { PassThrough } from "node:stream";
import { FramedJSONRPC } from "../util/jsonrpc.js";

function frame(obj: any): Buffer {
  const s = JSON.stringify(obj);
  const h = `Content-Length: ${Buffer.byteLength(s)}\r\n\r\n`;
  return Buffer.concat([Buffer.from(h), Buffer.from(s)]);
}

describe("FramedJSONRPC", () => {
  it("reads and writes framed messages", async () => {
    const input = new PassThrough();
    const output = new PassThrough();
    const rpc = new FramedJSONRPC(input, output);

    const req = { jsonrpc: "2.0", id: 1, method: "ping", params: {} };
    input.end(frame(req));

    const r = await rpc.read();
    expect(r?.method).toBe("ping");

    rpc.write({ jsonrpc: "2.0", id: 1, result: { ok: true } });
    const out = output.read() as Buffer;
    expect(String(out)).toMatch(/Content-Length: /);
    expect(String(out)).toMatch(/"result":\{"ok":true\}/);
  });

  it("handles parse errors gracefully", async () => {
    const input = new PassThrough();
    const output = new PassThrough();
    const rpc = new FramedJSONRPC(input, output);

    const bad = Buffer.concat([Buffer.from("Content-Length: 5\r\n\r\n"), Buffer.from("{oops")]);
    input.end(bad);
    const r = await rpc.read();
    expect((r as any)?.method).toBe("__internal_parse_error__");
  });
});