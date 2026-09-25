---
name: bug-history-check
description: Check whether a bug or unusual failure has already been solved before spending time re-diagnosing it.
triggers: ["debugging", "bug", "unexpected failure", "flaky test", "same error again"]
permissions: ["READ"]
---

# Bug History Check

Before spending significant time diagnosing an unusual failure:

1. Call `check_history("<short description of the symptom>")`. If a prior decision/fix is
   recorded, read it fully before starting your own investigation — it may name a root
   cause, a rejected fix that didn't work, or a known limitation worth not re-fighting.
2. If nothing relevant comes back, proceed with normal debugging.
3. Once you find the actual root cause and fix, call `record_decision(title, body, tags)`
   with enough detail that a future agent's `check_history` call on similar symptoms
   would surface it — include the symptom, the root cause, and the fix, not just "fixed it."

This is what turns one-off debugging into reusable project memory instead of every agent
re-discovering the same bug independently.
