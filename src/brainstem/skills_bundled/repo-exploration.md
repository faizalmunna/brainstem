---
name: repo-exploration
description: How to orient in an unfamiliar repository before making changes, using the brain's query API instead of reading every file.
triggers: ["explore repo", "understand codebase", "orient", "new to this repo", "unfamiliar codebase"]
permissions: ["READ"]
---

# Repo Exploration

Before reading files directly, ask the brain first:

1. `describe_project` — name, size, languages already indexed.
2. `get_rules` — recorded conventions/rules for this repo. Follow these before improvising.
3. `check_history("<the problem you're facing>")` — has something like this happened before? Read the recorded decision/fix before re-deriving it.
4. `query_context("<your actual task, in plain language>")` — returns the smallest relevant slice of files/symbols, ranked. Start there, not with a full-repo read.
5. Only fall back to a broad file search (grep/glob) for the parts `query_context` didn't cover — and treat that as a signal the graph might need a re-index (`brainstem index`) if the repo has changed recently.

Prefer this sequence over loading large portions of the repository into context: the brain exists specifically so agents don't have to rediscover project structure from scratch every session.
