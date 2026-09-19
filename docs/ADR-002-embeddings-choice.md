# ADR-002 — Embedding Strategy: TF-IDF Fallback vs Sentence-Transformers

**Date:** 2026-06  
**Status:** Accepted  
**Deciders:** Jérémy Bazan (Solo)

---

## Context

The PatternClassifier requires a vector representation of bug reports to perform semantic
similarity search. Two embedding strategies were evaluated: a lightweight TF-IDF approach
(scikit-learn) and a neural approach (sentence-transformers `all-MiniLM-L6-v2`).

## Decision Drivers

- CI pipeline must pass with zero network access (no HuggingFace downloads)
- Deterministic fallback pattern established in Anomaly Sentinel and SkyGuard is non-negotiable
- Embedding quality must be sufficient for technical QA vocabulary
- Model size must not add unreasonable cold-start overhead in tests

## Options Considered

### Option A — sentence-transformers `all-MiniLM-L6-v2` (production target)
- 384-dimensional dense vectors, strong semantic generalisation
- Requires downloading ~80MB model weights from HuggingFace at first use
- Blocked in sandboxed environments (403 Forbidden from restricted networks)
- Best-in-class for short-text similarity

### Option B — TF-IDF + cosine similarity via scikit-learn (selected as primary fallback)
- No download, no network, deterministic
- Sparse vectors (vocabulary-dimension), suited to domain-specific jargon
- Performs well when corpus vocabulary is consistent (QA terms, component names, error types)
- Vectors are l2-normalised before storage so cosine distance is equivalent to dot product

## Decision

**Dual-mode embedder:** TF-IDF is the default and CI path. Sentence-transformers is loaded
when available and used transparently via the same interface. The `Embedder` class exposes a
single `embed(texts)` method; callers never interact with the underlying strategy.

The pipeline's only caller opts out of that choice: `PatternClassifier` builds
`Embedder(force_tfidf=True)`, so duplicate detection runs on TF-IDF whatever the
environment says. See the amendment below.

This mirrors the Claude API / rule-based fallback pattern used in Agents 1 and 2, and
demonstrates a consistent architectural principle across the entire TestScribe pipeline.

## Consequences

- **Positive:** CI always passes, zero network dependency, deterministic test corpus
- **Positive:** `Embedder` isolates the strategy, so a caller that wants the neural path
  only has to stop forcing TF-IDF
- **Negative:** TF-IDF misses semantic similarity between synonyms ("crash" vs "freeze")
- **Mitigation:** Pattern library uses canonical QA vocabulary; keyword normalisation reduces synonym gaps

---

## Amendment — 2026-09-19

Re-reading the code while fact-checking a published article showed that this ADR promised
more than the code delivers. `PatternClassifier.__init__` pins `Embedder(force_tfidf=True)`
(comment: `TF-IDF always (CI-safe)`), and it is the only place in the pipeline that builds an
`Embedder`. Setting `USE_NEURAL_EMBEDDINGS=true` therefore changes nothing: duplicate
detection always runs on TF-IDF, that is, on lexical similarity.

The decision itself stands — TF-IDF by default, for reproducibility and a network-free CI.
What was wrong was the consequence claiming the neural path was one environment variable
away. That line is corrected above, and the READMEs no longer describe duplicate detection
as semantic.

Reaching the neural path would take a code change, plus a check that ChromaDB handles the
dimension switch (TF-IDF is 512, MiniLM is 384). Neither has been done nor measured.
