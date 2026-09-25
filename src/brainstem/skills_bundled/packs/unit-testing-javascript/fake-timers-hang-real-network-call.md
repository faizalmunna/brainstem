---
name: fake-timers-hang-real-network-call
description: A test calls jest.useFakeTimers or vi.useFakeTimers and then hangs indefinitely or times out because a real network request under the hood never resolves.
triggers: ["jest useFakeTimers test hangs", "vi.useFakeTimers test never finishes", "test times out with fake timers", "fetch never resolves with fake timers", "jest fake timers freezes async request"]
permissions: ["READ"]
---

## Symptom
As soon as `jest.useFakeTimers()`/`vi.useFakeTimers()` is enabled for a
test, the test hangs until it hits the overall test timeout, even though
the same test passed before fake timers were introduced. The code under
test makes what looks like a normal `await fetch(...)`/HTTP client call,
and nothing about the test's own assertions looks related to timers.

## Likely causes
- **The HTTP client library uses a real timer internally for its request
  timeout/retry-backoff logic** (many fetch polyfills, axios adapters, and
  retry libraries schedule a `setTimeout` to abort or retry a request), so
  faking timers globally intercepts that internal timer too -- the real
  network call is still in flight, but the mechanism that would eventually
  time it out or drive its retry loop never fires because fake time never
  advances.
- **The test never actually mocks the network call**, assuming that faking
  timers alone is enough to make an async test deterministic -- fake
  timers control `setTimeout`/`setInterval`/`Date`, not sockets or
  `fetch`, so an unmocked real request still goes out and still depends on
  real wall-clock/network behavior to ever settle.
- **Fake timers are enabled globally for the whole file/suite** (in a
  `beforeEach` with no scoping) including tests that were never meant to
  touch timer-dependent code, so an unrelated integration-style test in
  the same file inherits fake timers it doesn't need and doesn't account
  for.
- **Legacy fake timers are used (`jest.useFakeTimers('legacy')` or an old
  Jest default) which patch a different, broader set of timing APIs** than
  modern fake timers, catching more of the underlying HTTP/networking
  stack's internals than the test author expected.

## Diagnose
1. Comment out `useFakeTimers()` for the specific failing test only and
   confirm the test then completes (pass or fail) instead of hanging --
   this isolates the hang to the fake-timer interaction rather than a
   genuine network/logic bug.
2. Check whether the test actually mocks the network layer (`jest.mock`
   on the HTTP client, `msw`, `nock`, or a fetch mock) -- if the real
   `fetch`/`axios` call is unmocked, that is the first thing to fix
   regardless of the timer issue.
3. Check which fake timer mode is active (`jest.useFakeTimers()` default
   vs. `{ legacy: true }`, or Vitest's `shouldAdvanceTime`/`toFake` option
   list) and what APIs it patches -- confirm whether it's patching more
   than `setTimeout`/`setInterval`/`Date` for this project's Jest/Vitest
   version.
4. Add a short real-time watchdog (`--testTimeout=5000` or similar) so a
   hang fails fast with a stack trace pointing at the pending
   handle/promise, instead of waiting for the full default timeout on
   every run while iterating on the fix.

## Fix
Mock the network layer explicitly instead of letting a real request run
under fake timers -- use `msw`, `nock`, or a mocked HTTP client so the
response resolves synchronously/deterministically and there's no real
socket for an internal timer to be waiting on. When timer-dependent code
and network calls genuinely need to be tested together, scope fake timers
narrowly with `jest.useFakeTimers({ doNotFake: ['nextTick'] })`-style
configuration (Jest) or Vitest's `toFake` allowlist to only the specific
timer APIs the test needs faked, and enable/disable them per test
(`beforeEach`/`afterEach` in the specific describe block) rather than
globally for the whole file. If the code under test's own retry/backoff
timer needs to be driven forward, do so explicitly and incrementally
(`jest.advanceTimersByTimeAsync(ms)` / `vi.advanceTimersByTimeAsync(ms)`)
interleaved with awaiting the mocked network promise, so both the timer
and the promise queue make progress together instead of the timer running
far ahead of or independent from the mocked response.

## Pitfalls
Don't reach for `jest.advanceTimersByTime(999999)` as a blunt "just skip
to the end" fix -- with an unmocked real network call still pending, no
amount of fake-timer advancement resolves it, and with a mocked call, a
huge single jump can fire multiple retry/backoff cycles at once in ways
that don't match real timing behavior and can hide bugs in the actual
backoff logic. Also don't leave fake timers enabled for the rest of the
file "since it's already set up" -- unrelated tests later in the same
file inherit them silently and can develop the same hang the next time
someone adds a new async call without realizing timers are faked.

## Verify
Run the specific test alone with a short explicit timeout
(`--testTimeout=3000`) after applying the fix and confirm it completes
well under that budget rather than passing only because the default
timeout is long. Then run the full file together to confirm no other test
in the same file was relying on the now-scoped-down fake timer
configuration.
