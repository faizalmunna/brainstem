---
name: mongodb-embedding-vs-referencing-schema-choice
description: Decide between embedding and referencing when a new MongoDB relationship's access pattern doesn't clearly fit the schema chosen for an existing similar one.
triggers: ["should I embed or reference in mongodb", "one to many relationship mongodb schema", "document keeps growing should I split it out", "mongodb schema design for related data", "normalize or embed this relationship"]
permissions: ["READ"]
---

## Symptom
A team is adding a new relationship to an existing MongoDB schema (a new
"has-many" or "belongs-to" association) and is unsure whether to embed
it as a subdocument/array or reference it via an ID and a separate
collection -- often because an *existing* relationship in the same
schema was modeled one way, and copying that precedent for the new
relationship produces a design that turns out to be wrong once real
usage patterns emerge (too-large documents, or excessive joins), because
the two relationships don't actually share the same access pattern.

## Likely causes
1. **Defaulting to "how we did it last time" instead of evaluating this
   specific relationship's read/write pattern** -- embedding and
   referencing aren't a single project-wide style choice, they're a
   per-relationship decision based on cardinality, growth, and how data
   is queried together.
2. **Not distinguishing relationship cardinality and growth bound** --
   a one-to-few relationship with a hard natural cap (e.g. a product's
   variants) behaves very differently from a one-to-many-unbounded
   relationship (e.g. a user's order history), and the same embedding
   choice that works for the former breaks down for the latter (see
   `mongodb-unbounded-array-hits-document-size-limit`).
3. **Optimizing for how data is displayed rather than how it's written
   and queried** -- embedding often looks natural because it mirrors a
   UI's "show this together" view, but the write pattern (how often the
   embedded part changes independently of the parent) and query pattern
   (whether the embedded part is ever queried/filtered on its own) are
   what actually determine whether embedding holds up.
4. **Not considering that the decision can differ for the same logical
   relationship depending on direction** -- e.g. "show a blog post with
   its comments" favors embedding comments in the post for one-shot
   reads, but "show all comments by a user across posts" favors comments
   as their own collection referencing both post and user -- the same
   relationship can need different physical representations (including
   controlled duplication) depending on which query dominates.

## Diagnose
- For the specific relationship in question, explicitly answer: what is
  the maximum realistic cardinality (bounded and small, bounded but
  large, or genuinely unbounded)? Unbounded or large-and-growing
  strongly favors referencing.
- Check whether the "many" side is ever queried, filtered, sorted, or
  paginated independently of its parent -- if yes, that's a strong
  signal for a separate collection with its own index, since embedded
  array elements can't be indexed/queried as efficiently as top-level
  documents (see `mongodb-deep-nesting-forces-array-scan`).
- Check how often the "many" side changes relative to the parent -- high
  -frequency independent writes to an embedded subdocument mean every
  write touches (and potentially resizes/relocates) the entire parent
  document, which has its own cost even before hitting the size limit.
- Check whether the dominant read pattern needs the parent and the
  related data together in a single round-trip (favoring embedding or
  denormalization) versus needing the related data independently far
  more often than together (favoring referencing).

## Fix
- Embed when the relationship is naturally bounded (small, known
  maximum count), read together with the parent far more often than
  queried independently, and doesn't need independent indexing --
  this gets single-document read locality with no join cost.
- Reference (separate collection + ID, with an index on the reference
  field) when the relationship is unbounded or large, needs independent
  querying/sorting/filtering, or is written to at high frequency
  independent of the parent -- accept the extra query/`$lookup` cost in
  exchange for avoiding document-size and write-amplification problems.
- For relationships that are queried both ways with meaningfully
  different dominant patterns, consider deliberate controlled
  duplication: store a summary/reference in both directions (e.g. a
  post embeds a small "recent comments" preview while the full comment
  history lives in its own collection), explicitly deciding which
  representation is the source of truth and which is a denormalized
  convenience updated on write.
- Document the reasoning per relationship (not just the choice) in
  schema documentation or code comments, since the same-looking decision
  ("this is a has-many, just like that other one") is exactly what leads
  future engineers to copy a pattern that doesn't fit their specific
  access pattern.

## Pitfalls
- Treating embedding vs. referencing as a one-time, project-wide
  convention rather than a per-relationship decision -- consistency for
  its own sake produces schema choices that fit some relationships and
  actively hurt others.
- Choosing based on today's data volume without projecting growth --
  a relationship that's small and embeddable now but has no natural
  cap (e.g. "comments on a post" for a post that could go viral) needs
  to be evaluated against its *unbounded* case, not its current typical
  case.
- Switching an existing embedded relationship to referenced (or vice
  versa) without a real migration plan -- this changes both the write
  path and every read path querying that data, and needs the same
  care as any other schema migration (backfill, dual-write period,
  cutover), not a quick in-place edit.

## Verify
For the relationship in question, write out the top 2-3 actual queries
against it (not hypothetical ones) and confirm each can be satisfied
efficiently (indexed, no unbounded document growth, no excessive
`$lookup` fan-out) under the chosen embed/reference design at a
realistic projected data volume and cardinality, not just against
today's small dataset.
