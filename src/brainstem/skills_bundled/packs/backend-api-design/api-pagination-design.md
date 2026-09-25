---
name: api-pagination-design
description: Diagnose and fix pagination bugs (skipped/duplicated items, slow deep pages) caused by offset-based pagination on data that changes, and decide when cursor pagination is actually needed.
triggers: ["pagination skips items", "duplicate items pagination", "offset pagination slow", "cursor pagination", "pagination bug", "page 2 shows same items as page 1"]
permissions: ["READ"]
---

## Symptom
Users report seeing the same item on two consecutive pages, or missing
items that never appeared on any page, especially on lists that update
frequently (feeds, notifications, admin tables with concurrent writes);
separately, "page 50 of 1000" style deep pagination gets progressively
slower.

## Likely causes
1. **Offset/limit pagination (`OFFSET 200 LIMIT 20`) on a list ordered by
   a mutable or non-unique field**, where rows are inserted/deleted
   between page requests -- the offset shifts relative to the underlying
   data, causing skips or duplicates.
2. **Sorting by a non-unique column** (e.g. `created_at` with several
   rows sharing the same timestamp) without a tiebreaker, so the
   database's ordering among equal-value rows isn't guaranteed stable
   across queries, again causing skip/duplicate at page boundaries.
3. **`OFFSET` performance degradation**: the database still has to scan
   and discard all skipped rows before returning the page, so offset
   pagination gets linearly slower the deeper you page.
4. **Client-side re-fetching page 1 alongside later pages** (e.g. an
   infinite-scroll bug) without deduplicating by ID, showing genuine
   duplicates in the UI even though the API itself paginated correctly.

## Diagnose
- Check the ORDER BY clause: is it on a column that can have duplicate
  values, and if so, is there a secondary tiebreaker (e.g. `ORDER BY
  created_at, id`)?
- Reproduce with a script that inserts/deletes rows between two page
  fetches against real offset pagination and confirm whether items are
  skipped/duplicated -- this confirms cause 1 concretely rather than by
  inspection alone.
- For slow deep pages, check query plans/timing at low vs. high offsets
  on the same endpoint to confirm the degradation is offset-driven.
- For UI-visible duplicates with infinite scroll, check whether the
  client merges pages by concatenation or by deduplicating on item ID.

## Fix
- Switch to **cursor-based pagination**: encode the last-seen item's sort
  key (and a unique tiebreaker, e.g. `id`) into an opaque cursor, and
  query `WHERE (created_at, id) > (last_created_at, last_id) ORDER BY
  created_at, id LIMIT n` -- this is stable under concurrent inserts/
  deletes because it's anchored to a specific row, not a shifting offset.
- Always sort by a combination that's unique (add the primary key as a
  tiebreaker) even if you keep offset pagination for a low-stakes,
  rarely-mutated list.
- On the client, deduplicate merged pages by item ID regardless of
  pagination strategy, as a defense-in-depth measure against edge cases.
- For admin/reporting UIs that genuinely need "jump to page N" (which
  cursors don't support well), keep offset pagination but document that
  it's for relatively static/small datasets, not high-churn feeds.

## Pitfalls
- Cursor pagination breaks "jump to an arbitrary page number" UX --
  don't adopt it for a UI that specifically needs page-number navigation
  without also redesigning that UX (e.g. to "load more" or infinite
  scroll).
- An opaque cursor that's just base64 of raw sort-key values can leak
  internal details (exact timestamps, internal IDs) and lets clients
  construct invalid cursors -- validate/sign cursors if they cross a
  trust boundary, don't trust them blindly.
- Changing pagination strategy on a public API is a breaking change for
  any client parsing `page`/`offset` query params -- treat it under
  `rest-api-versioning-strategy`, not as a silent fix.

## Verify
Run the same concurrent insert/delete-during-pagination reproduction from
the diagnose step against the fixed (cursor-based) implementation and
confirm no item appears on two pages or is skipped across the full
traversal.
