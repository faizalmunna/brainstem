---
name: slice-aliasing-append-overwrite
description: Debug corrupted or unexpectedly mutated slice data caused by appending to a sub-slice that still shares a backing array with another live slice.
triggers: ["slice data got overwritten unexpectedly", "append corrupted another slice", "slice aliasing bug", "data changed after appending to different slice", "unexpected mutation shared backing array"]
permissions: ["READ"]
---

## Symptom
A slice's contents change unexpectedly after code appends to what looks like
an unrelated slice -- e.g. after appending to `sub := full[2:4]`, values in
`full` itself (or in another slice derived from it) appear corrupted or
overwritten, even though nothing directly assigned to `full`. This is often
intermittent-looking because whether it manifests depends on the slice's
capacity at the time, not just its length.

## Likely causes
1. **Re-slicing (`s[a:b]`) produces a new slice header that shares the same
   underlying backing array** as the original, so writes through either
   slice (including via `append` when capacity allows growth in place) are
   visible through both -- this is documented Go behavior, not a bug in the
   language, but it's routinely missed.
2. **`append` on a sub-slice with remaining capacity writes into the parent's
   backing array past the sub-slice's own length**, silently clobbering
   elements that the parent slice still considers "in bounds" -- this only
   happens when `cap(sub) > len(sub)`, so it's easy to miss in a quick test
   where the slice happened to be exactly full.
3. **A function takes a `[]T` parameter, appends to it, and returns it,** but
   the caller keeps using the original slice variable too -- if the append
   didn't need to grow (reallocate), the caller's original variable and the
   function's returned slice still alias the same array, so both "see" the
   appended write in the overlap region, but only one of them (the returned
   one) has the updated length -- leading to confusing partial-visibility
   bugs.
4. **Slicing a large buffer to hand out small "views" (e.g. `buf[i:i+n]` in a
   parsing loop) and retaining more than one such view across loop
   iterations**, where a later iteration's write (directly or via append)
   lands inside an earlier view's range because they share the same backing
   array.

## Diagnose
- Identify every place a sub-slice is created via `s[a:b]` (or `s[a:]`) from
  a shared slice that is also retained/used elsewhere after that point.
- For each `append` on a sub-slice, check `cap(sub)` vs `len(sub)` at that
  point -- if `cap > len`, that `append` can write into the parent's backing
  array without allocating a new one, and specifically the three-index slice
  form `s[a:b:b]` (setting cap == len) would have prevented it.
- Reproduce deterministically: print `len`, `cap`, and the first few elements
  of both the parent and the sub-slice immediately before and after the
  suspect `append` -- confirm elements in the parent changed at the offset
  corresponding to the appended value(s).
- Use `go vet` and the race detector as a first pass, though note this class
  of bug is a plain aliasing/capacity issue, not a data race -- it can
  reproduce single-threaded and deterministically once capacity conditions
  are right, so don't assume `-race` silence clears it.

## Fix
When a sub-slice must not be allowed to grow into its parent's backing array,
cap its capacity explicitly at slice time using the full three-index slice
expression, which sets the resulting slice's capacity equal to its length so
any `append` is forced to allocate a fresh backing array:
```go
sub := full[2:4:4] // cap(sub) == len(sub) == 2; append can't touch full's array
sub = append(sub, x) // always reallocates, full is untouched
```
When the intent is genuinely to share and mutate through both views on
purpose, make that explicit in a comment at the point of slicing, since it's
indistinguishable from a bug otherwise. When a function appends to a slice
parameter and returns it, always have callers reassign the returned value and
stop using the pre-call variable (`s = appendThing(s, x)`, never keep using
the old `s` afterward) -- this is exactly why `append`'s signature forces a
return value instead of mutating in place.

## Pitfalls
- Defensively copying every slice "just in case" (`append([]T{}, s...)`)
  eliminates the bug class but can be a real performance cost in hot paths
  processing large buffers -- reserve full copies for slices that are
  actually retained long-term or handed to concurrent code, and use the
  three-index slice form for the narrower, cheaper fix when only append-
  safety is needed.
- The three-index slice form only protects against `append` growing in place
  -- it does not protect against direct index writes (`sub[0] = x`) into
  positions that still alias the parent, because those positions are shared
  regardless of capacity.
- Believing `copy()` was used when it wasn't -- `copy(dst, src)` copies
  *values* into `dst`'s existing backing array up to `min(len(dst),
  len(src))` and does not allocate a new array or change `dst`'s length,
  which itself is a common source of a similar-looking but distinct bug
  (silently truncated copies).

## Verify
Write a unit test that creates the parent slice, derives the sub-slice the
same way production code does, appends to the sub-slice, and asserts the
parent slice's untouched elements are still equal to their original values
(not just that the sub-slice's own contents are correct) -- this specifically
catches the aliasing case that a test only checking the sub-slice's own
output would miss.
