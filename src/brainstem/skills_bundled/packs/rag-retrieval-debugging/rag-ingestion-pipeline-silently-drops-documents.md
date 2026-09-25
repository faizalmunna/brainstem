---
name: rag-ingestion-pipeline-silently-drops-documents
description: Some source documents never make it into the retrievable index because the ingestion pipeline fails silently on certain file types or sizes.
triggers: ["document exists but RAG can't find it at all", "some PDFs never get indexed", "ingestion job succeeded but chunk count looks too low", "certain file types missing from the vector store", "no error but document isn't searchable"]
permissions: ["READ"]
---

## Symptom
A user or engineer confirms a specific document exists in the source repository/bucket and should be searchable, but no query -- however phrased, however exact-match the terms -- retrieves anything from it. This is distinct from a ranking or chunking problem because the document isn't in the index at all; a direct metadata query for that document's ID against the vector store returns zero chunks, and typically the ingestion job's own logs and exit status show "success" with no visible error.

## Likely causes
1. **A specific file type or encoding silently fails text extraction** -- a scanned/image-only PDF with no embedded text layer, a password-protected document, or a corrupted file causes the extraction library to return an empty string or throw an exception that's caught and swallowed (logged at debug level or not at all) rather than surfaced as a pipeline failure, so the job reports overall success while that one document contributes zero chunks.
2. **A file-size or page-count limit in the extraction or chunking library truncates or skips oversized documents** without an explicit error, especially in serverless/lambda-style ingestion jobs with memory or execution-time limits that cause a large document's processing to time out and get skipped rather than retried or flagged.
3. **A batch/bulk ingestion job continues past individual-item failures by design** (a reasonable pattern for throughput) but doesn't aggregate and surface a per-document failure count/list anywhere visible, so a small but nonzero failure rate across every ingestion run goes unnoticed indefinitely.
4. **The document was updated or moved at the source after being listed for ingestion but before the job read it** (a race condition in incremental/scheduled ingestion), causing a fetch failure that's treated as "skip and continue" rather than "retry or alert."

## Diagnose
- Query the vector store directly for chunk count grouped by source document ID across the full expected document list (from the source repository/bucket listing) and diff it against the expected list -- documents with zero chunks are directly identified this way rather than by chasing individual complaints.
- Re-run the extraction step alone (outside the full pipeline) against the specific missing document and check for an empty-string result, a thrown exception, or a suspiciously fast completion time relative to the document's size -- any of these narrows to an extraction-stage failure.
- Check ingestion job logs specifically for per-document error/warning lines, including at a lower log level than what's normally reviewed (debug/info vs. only error) -- confirms whether the failure was logged but not surfaced, versus not logged at all.
- For a scanned/image-based PDF suspicion, open the specific document and check whether text is selectable/copyable -- a document with no selectable text confirms an OCR gap rather than an extraction bug.

## Fix
Make document-level ingestion failures loud rather than swallowed: have the ingestion pipeline emit a structured per-document success/failure record (not just an aggregate job-level status), and alert or block on any nonzero failure count rather than treating "job completed" as "job succeeded for every document." For scanned/image-only documents, add an OCR fallback step triggered when text extraction returns near-empty content, rather than silently accepting an empty result as valid. Add explicit size/format validation with clear rejection (not silent skip) for genuinely unsupported cases, and route rejected documents to a visible dead-letter list for manual follow-up rather than dropping them from the pipeline's awareness entirely.

## Pitfalls
- Adding logging for extraction failures but only at a verbosity level nobody actually monitors defeats the purpose -- failure visibility needs to reach whatever channel/dashboard is actually watched (the same one used for job-level success/failure), not just exist somewhere in log storage.
- Retrying failed documents automatically without a cap or backoff can mask a permanently-broken document (corrupted file, permanently password-protected) as a transient failure that never resolves, quietly consuming ingestion job time on every run indefinitely -- cap retries and surface permanent failures distinctly from transient ones.

## Verify
Run the diff between the expected source document list and the vector store's indexed document list and confirm it's empty (every source document has at least one chunk); intentionally introduce a known-bad document (an image-only PDF) into a test ingestion run and confirm the pipeline now surfaces an explicit failure/OCR-fallback path rather than completing silently with that document missing.
