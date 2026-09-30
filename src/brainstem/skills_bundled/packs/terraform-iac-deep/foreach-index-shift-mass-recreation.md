---
name: foreach-index-shift-mass-recreation
description: Terraform plans to destroy and recreate every resource in a count-based list because inserting or removing one item shifted all subsequent numeric indices.
triggers: ["terraform wants to recreate every resource in the list", "count index shift terraform", "removing item from list destroys everything", "terraform plan destroys entire count block", "switch count to for_each"]
permissions: ["READ"]
---

## Symptom
A small, intended change -- adding one item to a list, or removing one
item from the middle of a list used to drive `count` -- produces a
`terraform plan` that wants to destroy and recreate every resource
*after* that position in the list, not just the one that actually changed,
even though most of those resources' configuration didn't logically
change at all.

## Likely causes
1. **The resource uses `count = length(var.some_list)` with the list
   indexed positionally**, so Terraform's resource addresses are
   `resource.name[0]`, `resource.name[1]`, etc. -- purely positional, with
   no identity tied to the list item's actual content. Removing or
   inserting an item at position N shifts every item after it to a new
   index, and Terraform sees that as "the resource previously at index N
   now has different attributes" for every shifted index, not as "one
   item was added/removed."
2. **A `for_each` was used but keyed on something unstable** -- e.g.
   `for_each = toset(range(length(var.list)))` (still numeric/positional
   under the hood) rather than keying on a stable identifier from the
   data itself (a name, an ID), so it inherits the same positional
   fragility as `count` despite using `for_each` syntax.
3. **The list source itself reorders non-deterministically** -- e.g. a
   list built from a data source or map conversion that doesn't guarantee
   stable ordering across runs, so even without any intentional edit,
   Terraform can compute a different index-to-item mapping between plans.
4. **A module wrapping the resource internally uses `count`** even though
   the caller's interface looks stable, so the fragility is hidden one
   layer down and only surfaces as "why did changing one input recreate
   everything downstream."

## Diagnose
- Run `terraform plan` and check the resource addresses in the diff --
  `-/+` entries at `[3]`, `[4]`, `[5]` etc. immediately after a single
  list-item change, where the *count* of affected resources roughly
  matches "everything after the insertion/removal point," is the
  signature of positional-index fragility.
- Check the resource/module block's `count` or `for_each` expression
  directly -- `count = length(...)` or a `for_each` keyed by
  `range(...)` or a bare list confirms positional indexing; `for_each`
  keyed by a map or `toset()` of stable string identifiers rules it out.
- Run `terraform state list` before and after the change and diff the
  resource addresses -- if addresses like `[2]` map to a different
  logical item than before (confirm via `terraform state show
  'resource.name[2]'` pre- and post-change), that's direct proof of the
  index-shift, not just a suspicion from the plan summary.

## Fix
Convert the resource (or the module call) from `count` to `for_each`
keyed on a stable, content-derived identifier -- typically converting the
driving list into a map keyed by a natural key (name, ID) via something
like `for_each = { for item in var.list : item.name => item }` -- so each
resource's Terraform address is tied to the item's identity rather than
its position. This means inserting or removing one item only affects that
one resource's create/destroy, leaving every other item's resource
address (and therefore its state) completely undisturbed regardless of
where it sits in the list. When migrating existing `count`-based
resources to `for_each` on a live state, pair the config change with
`terraform state mv` for each existing resource (moving `resource.name[N]`
to `resource.name["key"]`) so the migration itself doesn't trigger a mass
destroy/recreate.

## Pitfalls
- Switching `count` to `for_each` in configuration without migrating
  existing state via `terraform state mv` first causes Terraform to see
  the old positional addresses as gone and the new keyed addresses as
  entirely new resources -- destroying and recreating everything once, on
  the very change meant to prevent future destroys/recreates.
- Keying `for_each` on a value that can itself change (e.g. a
  human-editable display name) reintroduces instability one level up --
  renaming that field is then indistinguishable from "delete old resource,
  create new one" from Terraform's perspective; prefer an immutable
  identifier as the key.

## Verify
After converting to `for_each` and migrating state, make the same class
of change that previously caused mass recreation (add or remove one item
from the middle of the list) and confirm `terraform plan` shows exactly
one resource being created or destroyed -- with every other existing
resource address unchanged and showing no diff at all.
