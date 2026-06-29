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
- Deterministic fallback pattern established in P1 and P2 is non-negotiable
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

This mirrors the Claude API / rule-based fallback pattern used in Agents 1 and 2, and
demonstrates a consistent architectural principle across the entire TestScribe pipeline.

## Consequences

- **Positive:** CI always passes, zero network dependency, deterministic test corpus
- **Positive:** Production upgrade path is one config flag (`USE_NEURAL_EMBEDDINGS=true`)
- **Negative:** TF-IDF misses semantic similarity between synonyms ("crash" vs "freeze")
- **Mitigation:** Pattern library uses canonical QA vocabulary; keyword normalisation reduces synonym gaps
