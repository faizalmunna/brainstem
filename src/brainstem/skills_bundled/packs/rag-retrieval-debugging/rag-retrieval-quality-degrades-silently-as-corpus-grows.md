---
name: rag-retrieval-quality-degrades-silently-as-corpus-grows
description: Retrieval was validated once at launch but quietly gets worse over months as the document corpus grows or shifts shape, with no alert firing.
triggers: ["RAG used to work better than it does now", "answer quality slowly declining over months", "we validated retrieval at launch but never since", "search got worse as we added more documents", "no one noticed retrieval regressed"]
permissions: ["READ"]
---

## Symptom
There's no single deploy or incident to point to -- users and support tickets gradually report more "the assistant gave a wrong/irrelevant answer" complaints over weeks or months, but nothing in monitoring/dashboards flags an error, latency spike, or outage. When someone finally investigates, they discover the corpus has grown substantially (2x-10x more documents) or shifted in composition (a new document type, a new department's content, much longer documents than the original corpus) since the last time anyone measured retrieval quality, which was at initial launch.

## Likely causes
1. **Retrieval quality was validated once, pre-launch, against a fixed benchmark query set and corpus snapshot**, with no recurring evaluation cadence, so there was never a mechanism that could have caught gradual degradation -- the absence of monitoring isn't a bug in the pipeline, it's a gap in the process around it.
2. **Growing corpus size increases the chance of near-duplicate or highly-similar documents competing for the same top-k slots**, diluting precision even with an unchanged embedding model and chunking strategy, purely as a function of a denser vector space with more plausible-looking distractors.
3. **New document types or sources were added without re-tuning chunking/retrieval parameters for their shape** (e.g., a corpus of short FAQs later gains long technical manuals, hitting the long-document fragmentation failure mode silently for the new content only), so aggregate metrics look fine while a growing subset of queries fail.
4. **Top-k and similarity thresholds were tuned against the original, smaller corpus's score distribution**, and as the corpus grows, the absolute similarity scores of true positives can shift (more competition, different score distribution), silently pushing previously-adequate thresholds out of calibration.

## Diagnose
- Check whether any retrieval-specific evaluation (separate from end-to-end answer quality) has been run since launch, and if so, when -- a multi-month or multi-quarter gap with no re-evaluation is itself the finding.
- Re-run the original launch-time benchmark query set (if it still exists) against the current, grown corpus and compare precision/recall@k directly against the launch-time numbers -- a measurable drop confirms corpus growth as a factor rather than an unrelated regression.
- Segment recent failure reports/support tickets by document type or by when the relevant source document was added to the corpus; a concentration of failures in newly-added document types points to an untuned-for-new-content-shape cause rather than general dilution.
- Plot the distribution of top-1 similarity scores across a sample of recent real queries and compare it to the distribution at launch -- a systematic downward shift suggests either embedding drift or increased competition from corpus growth diluting scores.

## Fix
Establish a recurring retrieval evaluation cadence (not just a one-time launch gate): maintain a versioned, growing benchmark set of judged query/expected-chunk pairs, re-run it on a schedule (e.g., monthly, or triggered by corpus size crossing a threshold) as an automated job that reports precision/recall@k as a tracked metric over time, not a one-off report. When corpus composition changes meaningfully (a new document type, a large batch ingestion from a new source), treat it as a mini-launch requiring its own targeted evaluation slice rather than assuming the existing benchmark set still represents the corpus. Re-calibrate similarity thresholds and top-k periodically against current score distributions rather than leaving launch-time constants untouched indefinitely.

## Pitfalls
- Treating end-to-end answer quality (user thumbs up/down, support ticket volume) as a sufficient proxy for retrieval quality -- it conflates retrieval and generation failures (see the missing-retrieval-eval-metric skill) and is too noisy and lagging to catch gradual retrieval-specific decay early.
- Building a benchmark set once and never expanding it as the corpus grows -- an aging, static benchmark increasingly fails to represent the current corpus's new document types and query patterns, giving false confidence that "the eval still passes."

## Verify
After implementing recurring evaluation, confirm the job runs on schedule and produces a trend line of precision/recall@k over time with real historical data points, not just a single current reading; confirm the benchmark set has been extended to include representative queries against the newest document types added to the corpus.
