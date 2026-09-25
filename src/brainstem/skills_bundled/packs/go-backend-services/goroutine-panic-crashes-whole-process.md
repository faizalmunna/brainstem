---
name: goroutine-panic-crashes-whole-process
description: Fix a Go server that terminates entirely when a single request-handling goroutine panics, instead of isolating the failure to that one request.
triggers: ["panic in goroutine crashes server", "unhandled panic kills whole process", "one bad request crashes entire service", "recover not catching goroutine panic", "server dies on panic in handler"]
permissions: ["READ"]
---

## Symptom
A single malformed request, an unexpected nil value, or an edge case in one
handler causes the *entire* Go process to crash and exit, taking down every
other in-flight request and requiring a full restart -- rather than that one
request failing gracefully with a 500 while the rest of the server keeps
running.

## Likely causes
1. **A panic occurs in a goroutine spawned manually (`go func() {...}()`)
   with no `recover()` anywhere in that goroutine's call stack** -- `recover`
   only works when called directly inside a deferred function *in the same
   goroutine* as the panic; a `recover()` in the goroutine that spawned it
   (or anywhere else) does not catch it, and an unrecovered panic in any
   goroutine terminates the entire process, not just that goroutine.
2. **The HTTP framework's built-in panic recovery middleware is missing,
   disabled, or only wraps some routes** -- many frameworks/routers provide
   a recovery middleware by default or as an easy add-on, but a hand-rolled
   router or a manually constructed handler chain can easily omit it,
   especially for routes added after the initial setup.
3. **A panic happens in a goroutine spawned *from inside* a request handler**
   (e.g. to do background work after responding) that isn't covered by the
   request-level recovery middleware at all, since that middleware's
   `defer recover()` is scoped to the original handler goroutine, not to
   goroutines it spawns.
4. **A panic occurs during server startup/background maintenance goroutines**
   (a scheduled job, a cache refresh loop) that were never wrapped with
   their own recovery, distinct from the request path entirely.

## Diagnose
- Read the crash's stack trace (Go prints the full goroutine dump on an
  unrecovered panic) -- identify which goroutine panicked and whether it's
  the main request-handling path, a spawned background goroutine, or a
  startup routine.
- Check whether the HTTP framework/router in use has recovery middleware
  registered, and confirm it's applied globally (wrapping every route) not
  just a subset -- read the router setup code, don't assume based on the
  framework's defaults.
- Grep for every `go func` in the codebase and check each one individually
  for its own `defer`+`recover` -- request-level recovery middleware does
  not extend into these by default.
- Reproduce locally by deliberately triggering the known panic condition
  (the malformed input, the nil case) against a local server instance and
  confirm whether the whole process exits vs. just that request failing.

## Fix
Apply `recover()` at two distinct levels, since they cover different
goroutines: first, ensure the HTTP framework's panic-recovery middleware
wraps every route so a panic during request handling becomes a 500 response
instead of a process crash. Second, and independently, wrap the *body* of
every manually spawned goroutine with its own recover, since middleware-level
recovery does not reach into goroutines spawned from within a handler:
```go
go func() {
    defer func() {
        if r := recover(); r != nil {
            log.Printf("recovered panic in background task: %v\n%s", r, debug.Stack())
        }
    }()
    doBackgroundWork()
}()
```
Log the recovered value and stack trace (`runtime/debug.Stack()`) at the
point of recovery so the underlying bug is still visible and fixable, rather
than silently swallowing it -- recovery should convert a crash into a
handled, observable failure, not hide the failure entirely.

## Pitfalls
- Wrapping every single goroutine spawn site by hand is easy to miss on a
  newly added one -- consider a small helper (`safego.Go(func(){...})`) that
  wraps `go func(){}()` with the recover boilerplate built in, and require
  its use via code review/lint rather than relying on everyone remembering.
- Recovering a panic and then continuing execution as if nothing happened
  (rather than returning/aborting that unit of work) can leave the program
  in an inconsistent state -- treat a recovered panic as "this request/task
  failed," not as a resumable condition, unless the code specifically knows
  it's safe to continue.
- Recovery middleware placed after other middleware that itself might panic
  doesn't cover that earlier middleware -- panic-recovery middleware needs
  to be the outermost layer in the chain to catch panics from everything
  inside it.

## Verify
Deliberately trigger the specific panic condition (via a crafted request,
or by calling the background task with input known to panic it) against a
running instance and confirm: the process itself stays up, the specific
request/task fails with a handled error (a 500 response, or a logged
failure for a background job), and the recovered panic plus stack trace
appears in the logs.
