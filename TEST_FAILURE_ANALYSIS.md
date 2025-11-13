# eva-mcp Test Failure Analysis

## Summary

- All 20 Vitest specs now pass locally on Windows 11 with Node.js 18 (`npm test`).
- Regression was traced to framed JSON-RPC reads that failed once the underlying stream ended while buffered data was still pending.
- Updated stream helpers and tests confirm multi-message scenarios no longer hang or mis-parse.

## Test Results

- [x] `registry.test.ts` (3) – Registry operations
- [x] `jsonrpc-framing.test.ts` (2) – Single message framing
- [x] `jsonrpc-bad-length.test.ts` (2) – Invalid length handling
- [x] `sandbox.test.ts` (3) – Filesystem sandboxing
- [x] `server-core.test.ts` (3) – Initialize/shutdown + tool call flow
- [x] `server-errors.test.ts` (3) – Error propagation scenarios
- [x] `resources-listing.test.ts` (1) – Resource listing newline semantics
- [x] `resources-prompts.test.ts` (2) – Resource reads and prompt retrieval
- [x] `server-shutdown-loop.test.ts` (1) – Ignores post-shutdown messages

## Root Cause

PassThrough-backed streams emit `end` immediately after their buffer drains. The prior `readLine`/`readBytes` helpers subscribed to `data`/`end` events afresh for each frame. When the second frame was requested, the stream had already surfaced `end`, so no additional `data` events fired and the promise never settled. Tests repeatedly timed out while awaiting the second response.

## Implemented Fixes

1. **Buffered stream readers** (`src/util/jsonrpc.ts`)
   - `readLine` and `readBytes` now accumulate chunks during `readable` notifications, scan for delimiters/lengths, and `unshift` any extra bytes before resolving.
   - Handles already-ended streams by processing remaining buffered data synchronously, avoiding hangs once `readableEnded` is true.
2. **Test harness updates**
   - Helper parsers in `server-core.test.ts`, `resources-prompts.test.ts`, and `server-shutdown-loop.test.ts` now honor `Content-Length`, returning leftovers to the `PassThrough` so subsequent reads see clean frames.
3. **Full suite verification**
   - `npm test` executes the entire Vitest suite successfully after the refactor.

## Validation

- Command: `npm test`
- Result: 20 passed, 0 failed (Vitest 2.1.9)
- Coverage: 93.24% statements / 78.28% branches / 91.66% functions / 93.24% lines (`npm test -- --coverage`)

## Follow-up

- None pending. Keep the buffered reader contract in mind if additional stream consumers are added; they should reuse the `FramedJSONRPC` helpers to avoid duplicating framing logic.
