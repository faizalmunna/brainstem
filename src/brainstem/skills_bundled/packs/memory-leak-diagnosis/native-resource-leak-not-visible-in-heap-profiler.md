---
name: native-resource-leak-not-visible-in-heap-profiler
description: A process runs out of file descriptors, sockets, or native memory even though a heap profiler shows normal, stable managed-memory usage, because the leak is in unmanaged/native resources the profiler doesn't track.
triggers: ["file descriptor leak heap looks fine", "native memory leak managed heap normal", "too many open files despite low heap usage", "socket leak not visible in profiler"]
permissions: ["READ"]
---

## Symptom

A process eventually crashes or fails (with "too many open files," a
socket exhaustion error, or an out-of-memory error reported at the OS
level) even though the runtime's own heap profiler shows normal, stable
managed-memory usage throughout -- the leak is happening in a resource
category the managed heap profiler simply doesn't track.

## Likely causes

- **File handles, sockets, or database connections are opened but not
  reliably closed on every code path** (especially error/exception
  paths that skip a cleanup step that only runs on the success path),
  leaking OS-level resources that a managed-heap profiler has no
  visibility into.
- **A native library or extension (a C/C++ binding, an FFI call)
  allocates memory outside the managed runtime's heap**, and that
  native allocation is never freed due to a bug in the binding code or a
  missing explicit disposal call.
- **A "using"/"with"/try-with-resources-style disposal pattern was meant
  to guarantee cleanup but was implemented incorrectly** (a resource
  created outside the disposal scope, or a scope that doesn't actually
  cover an exception path), so cleanup doesn't run in all necessary
  cases despite the pattern being present in the code.
- **A connection pool or resource pool has a bug or misconfiguration**
  causing it to create new native connections/handles faster than it
  returns them to the pool for reuse, growing the total open count over
  time even though the managed wrapper objects around them are properly
  garbage collected.

## Diagnose

1. Check OS-level resource usage (open file descriptor count via `lsof`
   or the platform equivalent, open socket count, native memory via OS
   process memory tools) over time, confirming growth there specifically
   while managed heap stays flat.
2. Audit code paths that open native resources (files, sockets, database
   connections, native library handles) for whether cleanup is
   guaranteed on every exit path, including exceptions, not just the
   success path.
3. For native library/FFI usage specifically, check whether the binding
   requires explicit disposal calls and whether those calls are actually
   being made consistently.
4. Check connection/resource pool configuration and actual behavior
   (connections created vs. returned) to identify pool-level leaks
   distinct from individual code-path leaks.

## Fix

Use language-level guaranteed-cleanup constructs (try-with-resources,
`using`, context managers, `defer`) consistently for every native
resource acquisition, verified to actually cover exception paths, not
just the happy path. For native library/FFI code, ensure every
allocation has a corresponding, reliably-executed disposal call,
ideally wrapped in the same guaranteed-cleanup pattern rather than
relying on manual discipline at every call site. Fix any connection/
resource pool bugs causing it to leak native handles outside of proper
pool accounting.

## Pitfalls

Don't assume a managed-heap profiler showing "no leak" means there's no
memory problem at all -- native/OS-level resources are a completely
separate category requiring separate tooling (OS process monitors,
native memory profilers, file descriptor counters) to diagnose.

## Verify

After the fix, monitor OS-level resource counts (file descriptors,
sockets, native memory) under sustained load over an extended period and
confirm they stabilize rather than continuing to grow. Deliberately
trigger the previously-leaking error/exception code path in a test
environment and confirm the resource is now correctly released even in
that specific scenario.
