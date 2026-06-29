# ADR-001 — Vector Store: ChromaDB vs FAISS

**Date:** 2026-06  
**Status:** Accepted  
**Deciders:** Jérémy Bazan (Solo)

---

## Context

TestScribe's PatternClassifier needs a vector store to persist bug report embeddings and perform
semantic similarity search at query time. Two candidates were evaluated: ChromaDB and FAISS.

## Decision Drivers

- Must run fully offline with no external API calls
- Must support persistent storage across process restarts
- Must integrate cleanly with Python 3.12 and our embedding pipeline
- Must be achievable solo with free/open-source tooling only
- CI pipeline must pass without network access

## Options Considered

### Option A — ChromaDB (selected)
- Embedded Python client, no server process required
- Supports custom embedding vectors (we supply TF-IDF/sentence-transformer vectors directly)
- Persistent storage via `PersistentClient` with a local directory
- Rich metadata filtering (sector, component, severity)
- Active community, well-documented Python API

### Option B — FAISS
- Extremely fast for large-scale nearest-neighbour search
- No built-in persistence layer (requires manual serialisation)
- No metadata support — requires parallel metadata store
- Lower-level API, more boilerplate for our use case

## Decision

**ChromaDB with manually supplied embeddings.**

ChromaDB's default embedding function requires downloading the ONNX MiniLM model from a CDN,
which is unavailable in sandboxed CI environments. We bypass this entirely by computing embeddings
externally (TF-IDF via scikit-learn, or sentence-transformers when available) and passing raw
vectors to ChromaDB. This gives us full control over the embedding strategy and keeps CI green
without network access.

## Consequences

- **Positive:** Portable, self-contained, no server process, metadata-rich queries
- **Positive:** Embedding strategy is swappable (TF-IDF → sentence-transformers) without changing the store interface
- **Negative:** TF-IDF vectors are sparser than neural embeddings; semantic recall is lower on short inputs
- **Mitigation:** TF-IDF performs well on technical QA vocabulary (component names, error codes, action verbs) and serves as a robust deterministic fallback
