---
name: nil-map-write-panic-vs-nil-slice-read
description: Explain and fix a panic from writing to a nil map, distinguishing it from the safe zero-value read behavior of nil maps and nil slices.
triggers: ["panic assignment to entry in nil map", "nil map write panic", "why does reading a nil map not panic but writing does", "zero value struct field map not initialized", "nil slice vs nil map behavior difference"]
permissions: ["READ"]
---

## Symptom
The program panics with `panic: assignment to entry in nil map` at a line
that looks completely ordinary, like `m[key] = value`, and the surrounding
code gives no obvious sign anything is wrong -- often because *reading* from
that same nil map earlier in the function worked fine and returned a zero
value with no error or panic, so the map "seemed to work" right up until the
first write. This frequently shows up specifically on a struct field of map
type that was never explicitly initialized, since a zero-value struct gives
every map field a nil map, not an empty-but-usable one.

## Likely causes
1. **A struct field of map type is left at its zero value (nil) because the
   struct was constructed with a plain literal (`MyStruct{}`) or via
   `new(MyStruct)` instead of a constructor that initializes the map with
   `make`** -- the field type-checks and reads fine (nil maps support
   lookups, returning the zero value and `ok == false`), which delays the
   panic until the first attempted write, often in a different function far
   from the construction site.
2. **Confusion between nil map and nil slice semantics** -- a nil slice
   supports `append` perfectly safely (it allocates a backing array on first
   append), which trains an intuition that "nil collection, first mutating
   operation just works" -- but a nil map's write path has no equivalent
   auto-initialization; `append(nilSlice, x)` works, `nilMap[k] = v` panics,
   and this asymmetry is a frequent source of the bug once someone
   generalizes from slice behavior to maps.
3. **A function receives a map parameter and the caller passes a nil map
   (either explicitly, or implicitly via an unexported struct field never
   initialized)**, and the function writes to it without checking -- the
   function has no way to distinguish "caller passed an empty-but-valid map"
   from "caller passed nil" without an explicit nil check, since both report
   `len() == 0`.
4. **JSON/config unmarshaling into a struct where the source data omits a
   field entirely** leaves that struct's map field nil (rather than an empty
   `{}` map), and downstream code that assumes "unmarshal always gives me at
   least an empty map for an object field" writes to it directly.

## Diagnose
- Read the panic's stack trace -- it points exactly at the write (`m[k] =
  v`, or `delete` is fine on nil, only assignment panics) -- then trace
  backward to where that map variable/field was supposed to be initialized
  and confirm whether a `make(map[K]V)` call actually executed on the path
  that led here.
- Check every constructor/factory function for the containing struct: does
  it use `make()` for every map field, or does some code path construct the
  struct via a plain literal or zero value that skips initialization?
- Add a nil check immediately before the panicking write during
  investigation (`if m == nil { panic("map is nil here") }` or a debug log)
  to pin down definitively whether the map is nil at that exact point versus
  some other write-related issue (e.g. writing through a nil pointer to a
  struct that itself contains the map).
- Grep the type definition for other map-typed fields -- a struct with one
  uninitialized map field very often has siblings with the same problem that
  haven't been hit yet simply because nothing has tried to write to them.

## Fix
Always initialize map fields with `make` in the type's constructor, and treat
a bare struct literal or zero-value construction as incomplete unless the
type is specifically designed to tolerate nil maps (documented as such):
```go
type Cache struct {
    entries map[string]string
}
func NewCache() *Cache {
    return &Cache{entries: make(map[string]string)} // always initialized
}
```
For functions that accept a map parameter and must write to it, either
require the caller to pass a non-nil map (document it) and fail fast with a
clear error/panic message if nil is passed, or defensively initialize it
on first write within the function itself when nil maps are a legitimate,
expected input:
```go
func addEntry(m map[string]string, k, v string) map[string]string {
    if m == nil {
        m = make(map[string]string)
    }
    m[k] = v
    return m // caller must use the returned map, same discipline as append
}
```

## Pitfalls
- Defensively nil-checking and lazily initializing a map inside every method
  of a type that's supposed to always be constructed via its constructor
  papers over the actual bug (a construction path that bypasses the
  constructor) rather than fixing it -- prefer fixing all construction paths
  first, reserving lazy-init for genuinely optional/rare-path fields. When
  lazy-init is the right call, callers must reassign the returned map (the
  same discipline `append` requires for slices) or the initialization is
  silently dropped on the floor for that caller.
- Assuming a map field survives being copied by value the same way a slice
  does -- copying a struct containing a nil map field just copies the nil
  map header; the fix needs to happen at whichever construction site
  produces the copy, not just "somewhere upstream."
- Confusing this with concurrent map write panics (`fatal error: concurrent
  map writes`) -- that's a completely different failure (a data race
  detected by the runtime's internal map implementation, requiring a mutex
  or `sync.Map`) that happens to produce a similarly-worded but distinct
  panic message; don't reach for locking as a fix for a plain nil map.

## Verify
Write a unit test that constructs the type using every code path that
produces it in production (constructor, zero-value literal if that's ever
used, unmarshaled from JSON/config with the map field omitted), and for each
one, attempt a write to the map field immediately -- confirm it succeeds
without panicking, or if zero-value construction is intentionally
unsupported, that it fails fast with a clear, documented error rather than a
bare nil-map panic deep in unrelated code later.
