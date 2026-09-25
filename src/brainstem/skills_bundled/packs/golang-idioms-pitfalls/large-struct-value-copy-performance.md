---
name: large-struct-value-copy-performance
description: Diagnose unexpected CPU overhead or profiler-visible allocations caused by passing a large struct by value through function calls instead of by pointer.
triggers: ["profiler shows time in struct copy", "passing struct by value is slow", "large struct performance overhead", "should this be a pointer receiver", "unexpected memcopy in cpu profile"]
permissions: ["READ"]
---

## Symptom
A CPU profile (pprof) or benchmark shows a surprising amount of time
attributed to `runtime.duffcopy`, `runtime.memmove`, or simply a function
whose body looks trivial but whose self-time is disproportionately high; or a
hot-path function that takes a struct parameter and calls several other
functions with the same struct, each triggering a full copy of every field.
This tends to appear only once a struct grows past a handful of fields (or
gains a large embedded array/fixed-size buffer field), and is easy to miss in
code review since `func Process(cfg Config)` looks identical whether `Config`
has 3 fields or 30.

## Likely causes
1. **A struct grew organically over time** (fields added for new features)
   without anyone revisiting whether it's still cheap to pass by value --
   what started as a small, genuinely-fine-to-copy struct with 2-3 fields
   accumulates enough fields (or a large fixed-size array field) that every
   value-parameter call now copies hundreds of bytes or more.
2. **A struct is passed by value through several layers of call chain**
   (e.g. `Handler -> Service -> Validator -> Formatter`), each taking it as a
   value parameter -- even if each individual copy is small, the cumulative
   cost across a hot path called at high request volume adds up to
   measurable CPU and cache pressure that a single-call microbenchmark
   wouldn't reveal.
3. **Range loop over a slice of structs using the value form (`for _, item
   := range items`)** copies each element into `item` on every iteration --
   for a slice of large structs iterated frequently, this is a real,
   measurable copy cost that using an index (`for i := range items`) and
   referencing `items[i]`, or ranging over a slice of pointers, avoids.
4. **A method is defined with a value receiver on a large struct "for
   consistency" with smaller types in the same package**, without
   considering that value receivers copy the entire struct on every method
   call, not just at explicit parameter-passing sites.

## Diagnose
- Run `go test -bench=. -benchmem` on the hot path and check the
  `allocs/op` and `B/op` columns -- an increase correlated with a struct's
  size is a direct signal, though note a pure stack copy (no escape to heap)
  won't show as an allocation, only as CPU time.
- Profile with `go tool pprof -top` on a CPU profile from load; look for
  `runtime.duffcopy` or high self-time in functions that otherwise do little
  besides pass the struct along -- `duffcopy` specifically indicates the
  compiler generated an inlined struct-copy routine, a strong tell.
- Check the struct's size directly with `unsafe.Sizeof(MyStruct{})` in a
  throwaway test or via `fieldalignment`/`structlayout` tooling -- structs
  above roughly a cache-line or two (64-128+ bytes) passed by value in hot
  paths are worth scrutinizing; this is a heuristic, not a hard rule, so
  confirm with the profiler rather than optimizing on size alone.
- Grep the struct's usages for how many function signatures take it by value
  (`Config` vs `*Config`) across the call chain in question, to see whether
  the copy is happening once or repeatedly down a deep call stack.

## Fix
Switch the struct to being passed (and received) by pointer through the hot
path, and correspondingly make its methods use a pointer receiver so a
single copy happens at most once, at construction:
```go
type RequestContext struct {
    // ...30 fields...
}
// before: copies the whole struct at every call in the chain
func Handle(ctx RequestContext) { validate(ctx); format(ctx) }
// after: one shared instance, no repeated copying
func Handle(ctx *RequestContext) { validate(ctx); format(ctx) }
```
For range loops over slices of large structs where the loop only reads
fields, iterate by index and reference `items[i]` directly, or store
`[]*Item` in the first place if items are frequently passed around
individually after being pulled from the slice.

## Pitfalls
- Converting every struct to pointer-passing as a blanket policy trades a
  small, fixed stack-copy cost for potential heap escapes and GC pressure --
  a small struct (a couple of machine words) is often *cheaper* to copy on
  the stack than to heap-allocate and dereference through a pointer; profile
  before converting rather than assuming pointers are always faster.
- Switching a struct to a pointer receiver for performance while some
  existing methods still use a value receiver creates the mixed-receiver
  inconsistency that itself causes separate interface-satisfaction bugs --
  convert the whole method set together (see the sibling nil-interface/value-
  receiver pitfalls in the adjacent backend pack) rather than one method at a
  time.
- Passing a pointer to a struct that's subsequently mutated by a callee, when
  the caller expected value semantics (an implicit copy-on-call safety net)
  -- switching to pointers changes aliasing behavior, not just performance,
  so audit whether any callee in the chain currently relies on getting its
  own independent copy.

## Verify
Add or update a `go test -bench` benchmark that exercises the hot path with
a realistic call depth, run it with `-benchmem` before and after switching to
pointer-passing, and confirm both `ns/op` drops and (if the struct was
escaping to the heap under the value-passing version) `B/op`/`allocs/op` are
unchanged or improved -- a benchmark, not a one-off profile snapshot, so the
improvement is repeatable and guards against regression.
