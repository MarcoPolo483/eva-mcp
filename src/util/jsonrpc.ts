import { Readable, Writable } from "node:stream";
import type { JSONRPCRequest, JSONRPCResponse, Json } from "../protocol/types.js";

export class FramedJSONRPC {
  constructor(private readonly input: Readable, private readonly output: Writable) { }

  // Read one framed JSON object (Content-Length protocol)
  async read(): Promise<JSONRPCRequest | undefined> {
    const headers = await readHeaders(this.input);
    if (!headers) return undefined;
    const lenStr = headers["content-length"];
    const len = lenStr ? parseInt(lenStr, 10) : NaN;
    if (!Number.isFinite(len) || len <= 0) {
      logErr("Invalid Content-Length:", lenStr);
      await drainBody(this.input);
      return undefined;
    }
    const buf = await readBytes(this.input, len);
    try {
      const req = JSON.parse(buf.toString("utf8"));
      return req;
    } catch (e: any) {
      logErr("JSON parse error:", e?.message);
      return {
        jsonrpc: "2.0",
        id: null,
        method: "__internal_parse_error__",
        params: { message: e?.message || "Parse error" }
      };
    }
  }

  write(obj: JSONRPCResponse | JSONRPCRequest) {
    const s = JSON.stringify(obj);
    const h = `Content-Length: ${Buffer.byteLength(s, "utf8")}\r\n\r\n`;
    this.output.write(h);
    this.output.write(s);
  }
}

function readLine(stream: Readable): Promise<Buffer | null> {
  return new Promise((resolve) => {
    let chunks: Buffer[] = [];
    let total = 0;
    let done = false;

    const cleanup = () => {
      if (done) return;
      done = true;
      stream.off("readable", onReadable);
      stream.off("end", onEnd);
    };

    const resolveWith = (line: Buffer | null) => {
      chunks = [];
      total = 0;
      cleanup();
      resolve(line);
    };

    const tryResolve = (): boolean => {
      let offset = 0;
      for (const chunk of chunks) {
        const idx = chunk.indexOf(0x0a); // '\n'
        if (idx !== -1) {
          const lineLen = offset + idx + 1;
          const buffer = Buffer.concat(chunks, total);
          const line = buffer.subarray(0, lineLen);
          const rest = buffer.subarray(lineLen);
          if (rest.length) stream.unshift(rest);
          resolveWith(line);
          return true;
        }
        offset += chunk.length;
      }
      return false;
    };

    const onReadable = () => {
      if (done) return;
      let chunk: Buffer | null;
      while ((chunk = stream.read()) !== null) {
        chunks.push(chunk);
        total += chunk.length;
        if (tryResolve()) {
          return;
        }
      }
      if (!done && stream.readableEnded && chunks.length === 0) {
        resolveWith(null);
      }
    };

    const onEnd = () => {
      if (done) return;
      if (!tryResolve()) {
        resolveWith(null);
      }
    };

    stream.on("readable", onReadable);
    stream.on("end", onEnd);

    onReadable();
    if (!done && stream.readableEnded) {
      onEnd();
    }
  });
}

async function readHeaders(stream: Readable): Promise<Record<string, string> | null> {
  const headers: Record<string, string> = {};
  while (true) {
    const line = await readLine(stream);
    if (line === null) return null;
    const s = line.toString("utf8");
    if (s === "\r\n") break;
    const idx = s.indexOf(":");
    if (idx !== -1) {
      const key = s.slice(0, idx).trim().toLowerCase();
      const value = s.slice(idx + 1).trim();
      headers[key] = value;
    }
  }
  return headers;
}

async function readBytes(stream: Readable, len: number): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    let chunks: Buffer[] = [];
    let total = 0;
    let done = false;

    const cleanup = () => {
      if (done) return;
      done = true;
      stream.off("readable", onReadable);
      stream.off("end", onEnd);
      stream.off("error", onError);
    };

    const resolveWith = (buffer: Buffer) => {
      chunks = [];
      total = 0;
      cleanup();
      resolve(buffer);
    };

    const rejectWith = (err: Error) => {
      chunks = [];
      total = 0;
      cleanup();
      reject(err);
    };

    const onReadable = () => {
      if (done) return;
      let chunk: Buffer | null;
      while ((chunk = stream.read()) !== null) {
        chunks.push(chunk);
        total += chunk.length;
        if (total >= len) {
          const buffer = Buffer.concat(chunks, total);
          const exact = buffer.subarray(0, len);
          const rest = buffer.subarray(len);
          if (rest.length) stream.unshift(rest);
          resolveWith(exact);
          return;
        }
      }
    };

    const onEnd = () => {
      if (done) return;
      rejectWith(new Error("Stream ended"));
    };

    const onError = (err: Error) => {
      if (done) return;
      rejectWith(err);
    };

    stream.on("readable", onReadable);
    stream.on("end", onEnd);
    stream.on("error", onError);

    onReadable();
    if (!done && stream.readableEnded) {
      onEnd();
    }
  });
}

async function drainBody(stream: Readable) {
  // Best-effort drain current body (used on invalid length)
  await new Promise((resolve) => {
    stream.once("readable", resolve);
  });
}

function logErr(...args: any[]) {
  try {
    const msg = ["[eva-mcp]", ...args].join(" ");
    process.stderr.write(msg + "\n");
  } catch {
    // ignore
  }
}