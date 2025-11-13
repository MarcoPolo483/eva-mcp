# eva-mcp Test Failure Analysis

## Summary
eva-mcp has 20 total tests. Currently **10 tests pass** and **10 tests fail** with timeout errors (5000ms). All failing tests involve reading multiple JSON-RPC messages from Node.js PassThrough streams.

## Test Results
```
✅ PASSING (10 tests):
- registry.test.ts (3 tests) - Registry operations
- jsonrpc-framing.test.ts (2 tests) - Single message framing
- jsonrpc-bad-length.test.ts (2 tests) - Error handling
- sandbox.test.ts (3 tests) - File system security

❌ FAILING (10 tests - all timeout at 5000ms):
- server-core.test.ts (3 tests)
  - handles initialize and shutdown
  - lists tools and calls echo
  - returns method not found for unknown method
- server-errors.test.ts (3 tests)
  - tools/call unknown tool returns isError result
  - resources/read without uri yields JSON-RPC error
  - prompts/get without name yields JSON-RPC error
- resources-listing.test.ts (1 test)
  - returns newline-separated listing
- resources-prompts.test.ts (2 tests)
  - lists and reads file resources
  - lists and gets prompts
- server-shutdown-loop.test.ts (1 test)
  - ignores subsequent messages post-shutdown
```

## Root Cause

### The Pattern
All failing tests follow this pattern:
1. Create a PassThrough stream for input
2. Write multiple framed JSON-RPC messages to the stream
3. Call `input.end()` to signal end of stream
4. Start the MCP server's `run()` loop which reads messages
5. Server successfully reads and processes the FIRST message
6. Server tries to read the SECOND message but hangs forever

### Technical Details

**Server's run loop** (src/server.ts):
```typescript
async run(): Promise<void> {
  while (true) {
    const msg = await this.rpc.read();  // Calls FramedJSONRPC.read()
    if (!msg) break;  // Should break when stream ends
    await this.handle(msg);
    if (this.shuttingDown) break;
  }
}
```

**FramedJSONRPC.read()** (src/util/jsonrpc.ts):
```typescript
async read(): Promise<JSONRPCRequest | undefined> {
  const headers = await readHeaders(this.input);  // Calls readLine() in loop
  if (!headers) return undefined;
  const len = parseInt(headers["content-length"], 10);
  const buf = await readBytes(this.input, len);
  return JSON.parse(buf.toString("utf8"));
}
```

**readLine()** helper (src/util/jsonrpc.ts):
```typescript
function readLine(stream: Readable): Promise<Buffer | null> {
  return new Promise((resolve) => {
    let acc: Buffer[] = [];
    function onData(chunk: Buffer) {
      acc.push(chunk);
      const buf = Buffer.concat(acc);
      const idx = buf.indexOf("\n");
      if (idx !== -1) {
        const line = buf.subarray(0, idx + 1);
        const rest = buf.subarray(idx + 1);
        stream.pause();
        if (rest.length > 0) stream.unshift(rest);
        stream.off("data", onData);
        stream.off("end", onEnd);
        resolve(line);
      }
    }
    function onEnd() {
      stream.off("data", onData);
      resolve(null);  // Should trigger server loop to break
    }
    stream.on("data", onData);
    stream.on("end", onEnd);
    stream.resume();  // Start emitting data events
  });
}
```

### The Problem

When a PassThrough stream has `end()` called on it:
1. All data is written to internal buffer
2. Stream emits 'end' event asynchronously
3. First message reads successfully via 'data' events
4. After first message completes, `readLine()` is called again for second message
5. **But the stream's 'end' event was already emitted and won't emit again**
6. `stream.resume()` is called but **no more 'data' events are emitted** because:
   - The stream has already ended
   - Event listeners registered AFTER 'end' was emitted never receive it
7. The Promise in `readLine()` never resolves → timeout

### Why Working Tests Pass

Tests that work (jsonrpc-framing.test.ts) send only ONE message:
```typescript
input.end(frame(req));  // Write one message and end
const r = await rpc.read();  // Read one message, stream ends, done
```

Tests that fail send TWO+ messages:
```typescript
input.write(msg1);
input.write(msg2);
input.end();  // End happens while server is still processing msg1
await srv.run();  // Tries to read msg2 but stream already ended
```

## Attempted Solutions (All Failed)

### 1. Check `readableEnded` Before Listening
```typescript
if (stream.readableEnded && stream.readableLength === 0) {
  resolve(null);
  return;
}
```
**Result:** Stream ends after first message, second message never read.

### 2. Start Server Before Writing
```typescript
const runPromise = srv.run();
await setImmediate();
input.write(msg1);
input.write(msg2);
input.end();
await runPromise;
```
**Result:** Same timeout - race condition with stream end event.

### 3. Write All Data in One Operation
```typescript
const combined = Buffer.concat([msg1, msg2]);
input.end(combined);
```
**Result:** Same timeout - stream still ends too early.

### 4. Use Readable.from()
```typescript
const input = Readable.from([combined]);
```
**Result:** Same timeout - Readable.from() emits data then ends immediately.

### 5. Synchronous Read Fallback
```typescript
const trySync = () => {
  let chunk;
  while ((chunk = stream.read(1)) !== null) {
    // try to read buffered data
  }
};
```
**Result:** Infinite loops and worse failures.

## Key Observations

1. **Timing Issue:** The 'end' event fires during or immediately after the first message is processed, before the second read attempt
2. **Event Listener Registration:** `readLine()` registers new 'end' listeners each time it's called, but if the stream has already ended, those listeners never fire
3. **No Buffered Data Access:** Once a stream ends and 'data' events have been emitted, calling `resume()` again doesn't re-emit events for remaining buffered data
4. **Stream State:** After `unshift()` puts data back onto the stream, that data should be available, but the ended state prevents new 'data' events

## Possible Solutions (Not Yet Attempted)

### Option A: Fix readLine() to Handle Ended Streams
Check if stream has ended AND has buffered data, and read synchronously:
```typescript
function readLine(stream: Readable): Promise<Buffer | null> {
  // If stream ended but has readable data, read synchronously
  if (stream.readableEnded) {
    const available = stream.read();
    if (available === null) return Promise.resolve(null);
    // Process available buffer looking for newline
    // ...
  }
  // Otherwise use event-based reading as before
}
```

### Option B: Refactor Tests to Keep Stream Alive
Don't call `input.end()` until AFTER all messages should be read:
```typescript
const runPromise = srv.run();
input.write(msg1);
await waitForResponse(output, 1);
input.write(msg2);
await waitForResponse(output, 2);
input.end();
await runPromise;
```

### Option C: Use Different Stream Type
Replace PassThrough with a custom Readable that:
- Buffers all messages upfront
- Emits them on-demand as read() is called
- Only emits 'end' after all messages are consumed

### Option D: Implement Read-Ahead Buffer
Modify FramedJSONRPC to read all available data into an internal buffer before processing:
```typescript
class FramedJSONRPC {
  private buffer: Buffer = Buffer.alloc(0);
  
  async read(): Promise<JSONRPCRequest | undefined> {
    // First, drain all available data from stream into buffer
    await this.fillBuffer();
    // Then parse from buffer instead of stream
    return this.parseFromBuffer();
  }
}
```

## Files Involved

- `src/util/jsonrpc.ts` - Stream reading logic (readLine, readBytes, readHeaders)
- `src/server.ts` - MCPServer.run() message loop
- `src/__tests__/server-core.test.ts` - Main failing test file
- `src/__tests__/server-errors.test.ts` - Error handling tests (failing)
- `src/__tests__/resources-*.test.ts` - Resource tests (failing)
- `src/__tests__/server-shutdown-loop.test.ts` - Shutdown test (failing)
- `src/__tests__/jsonrpc-framing.test.ts` - Single message tests (PASSING - reference)

## Environment

- Node.js: Latest LTS
- OS: Windows 11
- Test Runner: Vitest 2.1.9
- Stream Type: Node.js PassThrough from 'node:stream'

## Additional Context

### Windows Path Fix (Successful)
One fix WAS successfully applied to sandbox.test.ts for Windows path separators:
```typescript
// Changed from: /sub\/b\.txt/
// Changed to: /sub[\/\\]b\.txt/
```
This shows the test suite CAN be fixed, and the infrastructure works.

### Working Example Pattern
The jsonrpc-framing.test.ts shows the CORRECT pattern:
```typescript
it("reads and writes framed messages", async () => {
  const input = new PassThrough();
  const output = new PassThrough();
  const rpc = new FramedJSONRPC(input, output);

  const req = { jsonrpc: "2.0", id: 1, method: "ping", params: {} };
  input.end(frame(req));  // ONE message only

  const r = await rpc.read();
  expect(r?.method).toBe("ping");
  // Stream ends, read returns undefined on next call, test completes
});
```

## Questions for Investigation

1. Why doesn't `stream.unshift()` make data available for subsequent `resume()` calls after the stream has ended?
2. Is there a way to detect "stream ended but has unread buffered data"?
3. Should the tests be rewritten to keep streams alive, or should the stream reader be fixed?
4. What's the intended use case - are MCP servers expected to handle pre-written batches of messages, or always live streams?
5. Could a custom stream wrapper solve this by buffering and re-emitting properly?

## Success Criteria

All 20 tests passing without timeouts, maintaining the existing test intent of:
- Sending multiple JSON-RPC messages through a stream
- Verifying the server processes them in order
- Verifying correct responses are written to output stream
- Testing error handling and shutdown sequences

## Priority

Medium-High - This is blocking the eva-mcp repository from having a working test suite, but the actual MCP server code likely works fine with real stdin/stdout streams that don't end prematurely.
