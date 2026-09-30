---
name: output-format-not-machine-parseable
description: A CLI tool only produces human-readable formatted output with no structured format option, forcing scripts to fragile-parse text meant for visual reading.
triggers: ["cli output hard to parse in script", "no json output option cli", "scraping cli text output fragile", "cli tool machine readable format missing"]
permissions: ["READ"]
---

## Symptom

A script or automation pipeline needs to extract specific data from a
command-line tool's output, but the tool only provides human-formatted
output (aligned columns, decorative borders, color codes) with no
structured alternative -- forcing the script to parse the human-oriented
text with regular expressions that break whenever the tool's formatting
changes even slightly.

## Likely causes

- **The tool was designed primarily for interactive human use** and
  structured/machine-readable output was never considered a requirement,
  since the original use cases didn't involve scripting.
- **Output formatting (column widths, spacing) is generated dynamically
  based on content** (aligning columns to the widest value), making it
  inherently unstable for text-based parsing since the exact spacing
  varies run to run based on data.
- **A structured output option exists but is incomplete** -- it might
  cover some commands/fields but not others, forcing scripts to fall
  back to text-parsing for the uncovered cases anyway.
- **No stable, versioned schema exists even for an available structured
  output format**, so a future tool update could change field names or
  structure without warning, breaking scripts that depend on the
  "structured" format just as much as the text format would.

## Diagnose

1. Identify what data the script actually needs to extract and confirm
   whether it exists in any structured form the tool currently offers.
2. Check the tool's documentation/help output for any existing `--json`,
   `--format`, or similar structured-output flag.
3. If a structured format partially exists, identify specifically which
   commands or fields aren't covered, requiring text-parsing fallback.
4. Test the current text-parsing approach against different terminal
   widths/data volumes to confirm and quantify its actual fragility.

## Fix

Add a structured output format option (JSON is the most broadly
compatible and easy to consume from virtually any scripting language)
covering every command's output comprehensively, not just a subset.
Treat the structured output format as a versioned, stable contract
(similar to an API) with its own compatibility/deprecation discipline
for future changes, distinct from the human-readable format which can
change freely for cosmetic reasons. Document the structured format
explicitly so script authors have a stable reference rather than
reverse-engineering it from example output.

## Pitfalls

Don't couple the structured output's field names/structure to the
human-readable display's column headers -- keep them independent, so
improving the human-readable display's wording doesn't accidentally
break every script depending on the structured format's field names.

## Verify

Convert the script's fragile text-parsing logic to consume the new
structured output format and confirm it extracts the needed data
correctly and reliably across multiple runs with varying data. Confirm
the structured format remains stable across at least one subsequent tool
version update that changes the human-readable display cosmetically.
