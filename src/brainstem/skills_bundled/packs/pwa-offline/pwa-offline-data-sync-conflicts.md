---
name: pwa-offline-data-sync-conflicts
description: Design conflict resolution for a PWA that lets users make changes offline and syncs them later, so simultaneous/offline edits don't silently overwrite each other.
triggers: ["offline sync conflict", "background sync data loss", "offline changes overwritten", "pwa sync strategy", "indexeddb sync backend"]
permissions: ["READ"]
---

## Symptom
A user makes a change while offline (or on another device), the app
syncs later, and either the offline change is silently lost (overwritten
by a newer server value that doesn't know about it), or the reverse -- the
offline change silently overwrites a legitimate change made elsewhere in
the meantime, with no indication to the user that a conflict occurred at
all.

## Likely causes
1. **Last-write-wins syncing with no conflict detection**, so whichever
   write reaches the server last (by wall-clock arrival time, not
   necessarily the more "correct" or intentional one) simply overwrites
   the other, with no record that a conflict existed.
2. **No versioning/timestamp carried with the locally-queued change**, so
   the sync process can't tell whether the server's current value has
   changed since the offline edit was made, and therefore can't detect a
   real conflict versus a safe update.
3. **Offline changes queued and replayed in an order that doesn't match
   the user's actual intent** (e.g. a delete queued before an edit to the
   same item, replayed in a different order than the user experienced
   them locally).
4. **No user-facing signal when a conflict is silently resolved
   automatically**, so users lose trust in the app's offline behavior
   after discovering (usually the hard way) that a change they made
   didn't stick.

## Diagnose
- Identify what data model version/timestamp information (if any) is
  attached to queued offline changes and to the server's stored values,
  to determine whether conflict *detection* is even possible with the
  current data shape.
- Reproduce a genuine conflict scenario deliberately: make an offline
  edit on one client while making a different edit to the same record via
  another client/session, then bring the offline client back online and
  observe what actually happens to both edits.
- Check the order in which queued offline actions are replayed against
  the order the user actually performed them, especially across action
  types (edits, deletes, creates) on the same record.

## Fix
- Attach a version identifier (a monotonic version number, or a
  last-modified timestamp) to both the locally-queued change and check it
  against the server's current version at sync time, so the sync process
  can distinguish "safe to apply" (server hasn't changed since) from
  "genuine conflict" (server has a newer version than what the offline
  edit was based on).
- For detected conflicts, choose an explicit resolution strategy
  appropriate to the data: field-level merge for independent fields
  changed on each side, an explicit user-facing conflict-resolution
  prompt for genuinely incompatible changes to the same field, or a
  documented, deliberate last-write-wins policy *specifically* for data
  where that's actually an acceptable trade-off (not a default applied
  everywhere without consideration).
- Preserve and replay queued offline actions in the order the user
  actually performed them, and handle action-type conflicts explicitly
  (e.g. replaying an edit queued after a delete of the same record should
  be recognized and handled, not silently resurrect or corrupt the
  record).
- Surface sync results to the user, especially when a conflict was
  resolved automatically in a way that discarded one side -- even a
  simple "some offline changes couldn't be applied, review here" is
  better than silent data loss.

## Pitfalls
- Implementing conflict *detection* without a clear resolution UX still
  leaves users confused about what happened, just with better diagnostic
  information -- design the user-facing side of conflict resolution
  deliberately, not just the technical detection mechanism.
- Field-level automatic merging works well for genuinely independent
  fields but can produce an incoherent combined result for fields that
  are logically related (merging two edits to overlapping parts of a
  rich-text document, for example) -- know which fields are safe to
  auto-merge and which genuinely need explicit user resolution.

## Verify
Reproduce the original concurrent-edit scenario from the diagnose step
against the fix and confirm both changes are either correctly merged, or
the user is explicitly prompted to resolve the conflict -- not that one
side silently disappears.
