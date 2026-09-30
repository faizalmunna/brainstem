---
name: duplicate-records-shared-across-train-test-split
description: Validation metrics look unusually strong because identical or near-identical records exist in both the training and test partitions of the dataset.
triggers: ["validation accuracy too high to trust", "duplicate rows in train and test set", "model memorized test examples", "near duplicate leakage between splits"]
permissions: ["READ"]
---

## Symptom

Validation/test metrics are unusually high and suspiciously stable
across retraining runs, but real-world performance on genuinely new
examples is meaningfully worse -- and unlike the classic "high accuracy"
leakage symptom, this one often survives even careful feature auditing
because nothing looks wrong with any individual feature; the problem is
which *rows* ended up where.

## Likely causes

- **Exact duplicate rows exist in the raw dataset before any split was
  performed** (common with data collected from multiple overlapping
  sources, repeated scrapes, or re-ingested batches), and a naive random
  split distributes copies of the same row across both train and test,
  so the model is partially evaluated on examples it directly memorized.
- **Near-duplicates exist rather than exact duplicates** -- the same
  underlying event or entity recorded with minor variation (slightly
  different formatting, a corrected typo, a re-submitted form), which
  simple exact-match deduplication won't catch but which still let the
  model "recognize" test examples it has effectively already seen.
- **The split was performed at the row level when the data has a natural
  grouping key** (multiple rows per user, multiple crops of the same
  image, multiple sentences from the same document), and rows from the
  same group landed on both sides of the split, which behaves like
  near-duplication because grouped rows are highly correlated.
- **Data augmentation was applied before the split rather than after**,
  so augmented variants of a single original example (rotated images,
  paraphrased text) end up split across train and test, again letting
  the model see near-identical content on both sides.

## Diagnose

1. Run exact-duplicate detection across the full dataset (hash each
   row's feature content) and report how many duplicate rows exist and,
   critically, how many span the train/test boundary.
2. For near-duplicates, use a similarity method appropriate to the data
   type (fuzzy string matching / edit distance for text, perceptual
   hashing for images, cosine similarity on embeddings for either) and
   flag test-set rows with a near-duplicate above a defined similarity
   threshold in the training set.
3. Check whether the dataset has a natural entity/group key (user ID,
   document ID, source image ID) and verify whether the same key appears
   on both sides of the split.
4. If augmentation is part of the pipeline, check pipeline order: confirm
   whether augmentation happens before or after the split by tracing
   which script/step runs first.

## Fix

Deduplicate the raw dataset before splitting (exact duplicates) and apply
near-duplicate detection with a defined similarity threshold to remove or
consolidate near-identical records prior to splitting as well. Where the
data has a natural grouping key, split at the group level (all rows for
a given user/document/source-image entirely in train or entirely in
test) using a grouped split rather than a plain row-level random split.
Move any data augmentation step to occur strictly after the split, and
only apply it to the training partition, never generating augmented
variants from data that also appears in the test set.

## Pitfalls

Don't rely on exact-match deduplication alone and declare the dataset
clean -- near-duplicates are the more common and more dangerous case in
practice (a customer support ticket resubmitted with one word changed, a
product photo re-uploaded at a different resolution), and exact hashing
will miss all of them while still allowing the same inflated-metric
symptom to persist.

## Verify

After deduplicating and re-splitting at the appropriate grouping level,
rerun the near-duplicate similarity check specifically across the
train/test boundary and confirm no test-set row has a near-duplicate
above threshold in the training set. Retrain and confirm the validation
metric drops to a level consistent with genuinely novel data, then
cross-check that drop against real production performance to confirm the
corrected validation number is now the trustworthy one.
