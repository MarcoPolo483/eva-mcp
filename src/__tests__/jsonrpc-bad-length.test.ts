import { describe, it, expect } from "vitest";
import { PassThrough } from "node:stream";
import { FramedJSONRPC } from "../util/jsonrpc.js";

function raw(headers: string, body = ""): Buffer {
  return Buffer.concat([Buffer.from(headers), Buffer.from(body)]);
}

describe("FramedJSONRPC invalid Content-Length handling", () => {
  it("returns undefined and drains when Content-Length <= 0", async () => {
    const input = new PassThrough();
    const output = new PassThrough();
    const rpc = new FramedJSONRPC(input, output);

    // Invalid: negative length
    input.end(raw("Content-Length: -5\r\n\r\n", "hello"));
    const r = await rpc.read();
    expect(r).toBeUndefined();
  });

  it("returns undefined when Content-Length not a number", async () => {
    const input = new PassThrough();
    const output = new PassThrough();
    const rpc = new FramedJSONRPC(input, output);

    // Invalid: NaN
    input.end(raw("Content-Length: nope\r\n\r\n", "{}"));
    const r = await rpc.read();
    expect(r).toBeUndefined();
  });
});