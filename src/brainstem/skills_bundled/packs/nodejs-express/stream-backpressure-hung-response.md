---
name: stream-backpressure-hung-response
description: Diagnose a file or proxy stream response that hangs, truncates, or balloons memory because backpressure from a slow client isn't being respected.
triggers: ["download hangs partway through", "large file response never completes", "stream memory usage keeps growing", "pipe not draining", "response truncated on slow connection"]
permissions: ["READ"]
---

## Symptom
An endpoint that streams a large response (a file download, a generated
report, a proxied upstream response) either hangs indefinitely partway
through for some clients, completes with a truncated/corrupted body, or
causes the server's memory usage to spike specifically when clients are
on slow connections -- while the same endpoint works fine in local
testing over a fast loopback connection.

## Likely causes
1. **Manual `data`/`end` event handling instead of `.pipe()` (or
   `stream.pipeline()`)**, writing to `res` on every `data` event with no
   regard for `res.write()`'s return value -- when `res.write()` returns
   `false` (the client's TCP receive buffer is full and can't accept more
   right now), continuing to call `write()` anyway buffers everything in
   process memory instead of pausing the source stream.
2. **A transform in the middle of the pipeline that doesn't propagate
   backpressure correctly** -- a custom `Transform` stream that
   buffers internally, or an older/misbehaving library stream that
   doesn't correctly signal "I'm full" upstream, breaking backpressure
   even when `.pipe()` is used everywhere else.
3. **Errors from one stream in a manually-wired pipe not being
   handled**, so a downstream error (a broken client connection, a
   failed upstream fetch) leaves the source stream still flowing with
   nothing consuming it, or leaves it paused forever with no error
   propagated to end the response -- `.pipe()` alone does not forward
   error events, so an unhandled `error` on either side can leave the
   pair in a stuck state.
4. **The response is buffered into memory before being sent**
   (`fs.readFile` + `res.send(buffer)` instead of
   `fs.createReadStream().pipe(res)`), which isn't a backpressure bug
   per se but produces the same symptom profile (memory spikes
   proportional to concurrent large downloads) and is often what people
   mean when they say "streaming is broken."

## Diagnose
- Check whether the code uses `.pipe()`/`stream.pipeline()` or a manual
  `stream.on('data', chunk => res.write(chunk))` loop -- the manual form
  is the first thing to look for, since it's the most common way
  backpressure gets silently dropped.
- Reproduce with an artificially slow client: throttle the connection
  (browser devtools network throttling, or `curl --limit-rate 10k`) while
  watching the server's memory (`process.memoryUsage().heapUsed` /
  `rss`) and the source stream's paused state
  (`sourceStream.isPaused()` if using manual piping) -- growing memory
  paired with the source stream never pausing confirms backpressure isn't
  being respected.
- For a hang specifically, check whether an `error` listener exists on
  every stream in the chain (source, any transforms, and the
  response) -- an unhandled `error` event on a readable stream throws and
  can crash the process, while a swallowed error on a piped-to stream can
  leave the source in a state where it's neither flowing nor properly
  closed.
- Check whether the client disconnecting mid-download is handled: kill
  the client connection partway through a download and confirm the
  server-side stream actually stops reading from its source (a database
  cursor, an upstream HTTP response) instead of continuing to pull data
  into memory for a response nobody is receiving anymore.

## Fix
- Use `.pipe()` for simple pass-through cases (`readStream.pipe(res)`),
  or `stream.pipeline(source, ...transforms, res, callback)` (from
  `node:stream`) for anything with more than one stage -- `pipeline`
  additionally handles cleanup and error propagation across every stream
  in the chain automatically, which manual wiring reliably gets wrong.
- If a manual write loop is unavoidable, respect `res.write()`'s boolean
  return value: when it returns `false`, call `sourceStream.pause()`,
  and resume it on the response's `drain` event
  (`res.once('drain', () => sourceStream.resume())`) -- this is exactly
  what `.pipe()` does internally, made explicit.
- Attach an `error` handler on every stream in the chain, not just the
  response -- for a `pipeline()`-based flow, its callback receives errors
  from any stage; for manual `.pipe()`, add `.on('error', ...)` to each
  stream individually since `.pipe()` doesn't forward errors between
  them.
- Handle client disconnects explicitly with `res.on('close', () =>
  sourceStream.destroy())` so an abandoned response stops pulling from
  its source (closes a DB cursor, aborts an upstream fetch) instead of
  continuing to consume resources for a response nobody will receive.

## Pitfalls
- Switching to `.pipe()` but leaving old `data`/`end` listeners attached
  to the same source stream elsewhere in the code puts the stream into
  flowing mode from two independent consumers, causing chunks to be
  split unpredictably between them -- a stream should have exactly one
  consumer.
- Using `stream.pipeline()` but ignoring its callback's error argument
  reintroduces the "unhandled error leaves things in a stuck or crashed
  state" problem `pipeline` is meant to solve -- always handle the
  callback, even if only to log and ensure the response is ended.
- Calling `sourceStream.destroy()` on client disconnect without checking
  whether it's already ended can throw or double-fire cleanup logic in
  some stream implementations -- guard with a check on the stream's
  `destroyed`/`readableEnded` state, or wrap destroy calls to be
  idempotent.

## Verify
Download a large (multi-hundred-MB) response through a deliberately
throttled connection while monitoring server memory: RSS should stay
roughly flat rather than growing to approach the full response size, the
download should complete with the correct byte count/checksum, and
killing the client mid-download should be visible in server logs as the
source stream being destroyed rather than continuing silently.
