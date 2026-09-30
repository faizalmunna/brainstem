---
name: rag-cross-lingual-query-fails-against-monolingual-index
description: A query written in one language fails to retrieve relevant source documents that exist only in a different language in the corpus.
triggers: ["RAG doesn't work when asking in a different language", "translated query returns nothing relevant", "multilingual search fails to find the source document", "non-English query performs worse than English", "documents in another language never retrieved"]
permissions: ["READ"]
---

## Symptom
A user asks a question in one language (e.g., Spanish) about content that exists in the corpus only in another language (e.g., English source documents), and retrieval returns nothing relevant or scores everything low -- even though the same underlying fact, asked about in the document's original language, retrieves correctly. This can also show up in reverse within a single language pair: retrieval works acceptably for one query direction (native-language query against native-language docs) but fails specifically for the cross-lingual case.

## Likely causes
1. **The embedding model in use is not genuinely multilingual, or its cross-lingual alignment is weak** -- some embedding models are trained predominantly on one language and produce vectors for other languages that don't land in a shared, comparable semantic space with the dominant language, so same-meaning text in different languages doesn't embed nearby even though same-meaning text in the same language does.
2. **Chunking, tokenization, or a keyword/BM25 layer assumes a specific language's structure** (word-boundary tokenization tuned for space-separated languages, a stemmer/analyzer configured for one language) and performs poorly or breaks entirely on other languages, especially ones with different scripts or morphology.
3. **No query- or document-language detection and no translation/normalization step exists**, so the system has no mechanism to bridge the language gap at all -- it's relying entirely on the embedding model's inherent cross-lingual capability, which may not be sufficient for the specific language pair in question.
4. **The corpus itself has inconsistent language coverage** -- some documents exist in multiple language versions and some don't, so cross-lingual retrieval "works" for topics with parallel translations and silently fails for topics that only ever existed in the source language, which looks like an inconsistent, hard-to-reproduce bug rather than a systematic one.

## Diagnose
- Take a known fact from a source-language document and phrase the equivalent query in a second language, then check the raw cosine similarity between the query embedding and the known-relevant chunk's embedding directly -- a similarity score far below same-language equivalents confirms the embedding model's cross-lingual alignment as the proximate cause.
- Check the embedding model's documentation/model card for its trained/supported languages and any stated cross-lingual retrieval benchmarks -- a model with no stated multilingual training is unlikely to perform reliably regardless of tuning.
- If a keyword/BM25 layer is in the hybrid mix, test its analyzer directly against the non-dominant language's text via an `_analyze`-style call to confirm whether tokenization produces sensible tokens or degenerates (e.g., treating an entire non-space-separated-script sentence as one token).
- Audit corpus language coverage per topic/document to distinguish "the system can't do cross-lingual retrieval at all" from "this specific document only exists in one language and was never translated."

## Fix
Choose an embedding model with demonstrated strong cross-lingual retrieval performance for the specific language pairs the product needs (verified against a benchmark or a direct test, not assumed from a general "multilingual" label), since cross-lingual alignment quality varies significantly between models and language pairs. Where the embedding model's cross-lingual performance is insufficient, add an explicit query-translation step (translate the incoming query into the corpus's dominant language before embedding/retrieval) as a more controllable alternative to relying purely on shared embedding space, being explicit that this trades some nuance for reliability. For hybrid search, ensure the keyword/analyzer layer has language-appropriate tokenization configured per document language (detected or tagged at ingestion time) rather than one global analyzer config assumed to work for all languages in the corpus.

## Pitfalls
- Adding query translation but translating with a generic/low-quality translation step that mistranslates domain-specific terminology (product names, technical jargon), which can make retrieval worse than the untranslated cross-lingual embedding attempt for jargon-heavy queries -- validate translation quality specifically for domain terms, not just general fluency.
- Assuming a fix validated on one language pair generalizes to all supported languages -- cross-lingual embedding quality is pair-specific (a model strong on English-Spanish isn't necessarily strong on English-Japanese), so each supported pair needs its own validation.

## Verify
Build a small cross-lingual judged query set (queries in each supported non-dominant language paired with known-relevant source-language documents) and confirm retrieval precision/recall for these queries now approaches same-language performance; spot check that domain-specific terminology still retrieves correctly after any translation step is added, using terms known to be tricky for generic translation.
