"""PatternClassifier — semantic pattern classification using RAG.

Encodes bug reports as TF-IDF vectors, stores them in ChromaDB,
and classifies new reports by finding the nearest neighbours
in the vector space.

See ADR-001 (ChromaDB) and ADR-002 (embedding strategy) for rationale.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.embedder import Embedder
from core.vector_store import VectorStore, SearchResult

_DATA_DIR = Path(__file__).parent.parent / "data"
_PATTERN_LIBRARY_PATH = _DATA_DIR / "pattern_library.json"
_SEED_REPORTS_PATH = _DATA_DIR / "seed_reports.json"

# Pattern priority order for keyword fallback (more specific first)
_PRIORITY = [
    "SAFETY_CRITICAL",
    "SECURITY",
    "COMPLIANCE_REGULATORY",
    "AUTH_FLOW",
    "DATA_VALIDATION",
    "DATA_INTEGRITY",
    "INTEGRATION",
    "PERFORMANCE",
    "UI_REGRESSION",
]


@dataclass
class ClassificationResult:
    pattern: str
    similar_bugs: list[SearchResult] = field(default_factory=list)
    duplicate_probability: float = 0.0
    classified_by: str = "rule-based-fallback"
    confidence: float = 0.5


# ---------------------------------------------------------------------------
# Keyword-based fallback classifier
# ---------------------------------------------------------------------------

def _load_pattern_library() -> list[dict]:
    with _PATTERN_LIBRARY_PATH.open(encoding="utf-8") as f:
        return json.load(f)["patterns"]


def _kw_hits(kw: str, combined: str) -> bool:
    """Match a keyword against text — handles multi-word and plurals/conjugations."""
    if " " in kw:
        # Multi-word: anchor on first word (handles "30 min" -> "30 minutes")
        stem = re.escape(kw.split()[0])
        return bool(re.search(stem, combined))
    else:
        # Single word: prefix match for plurals/conjugations (freeze -> freezes)
        stem = re.escape(kw.rstrip("es"))
        return bool(re.search(r"\b" + stem, combined))


def _classify_keyword(text: str, patterns: list[dict]) -> str:
    """Keyword-based pattern classification — deterministic fallback."""
    combined = text.lower()
    scores: dict[str, int] = {}
    for p in patterns:
        hits = sum(1 for kw in p["keywords"] if _kw_hits(kw, combined))
        if hits:
            scores[p["name"]] = hits

    if not scores:
        return "UI_REGRESSION"  # Safe default

    # Prefer highest score; break ties with _PRIORITY order
    max_hits = max(scores.values())
    candidates = [k for k, v in scores.items() if v == max_hits]
    for p in _PRIORITY:
        if p in candidates:
            return p
    return candidates[0]


# ---------------------------------------------------------------------------
# RAG classifier
# ---------------------------------------------------------------------------

class PatternClassifier:
    """RAG-based pattern classifier backed by ChromaDB + TF-IDF embeddings.

    On first use, seeds the vector store with the 30 seed bug reports
    and their ground-truth patterns (derived via keyword classifier).
    Subsequent calls embed the query report and find similar patterns
    from the store.
    """

    _SIMILARITY_THRESHOLD = 0.15  # Below this: patterns are unreliable
    _DUPLICATE_THRESHOLD = 0.75   # Above this: likely duplicate

    def __init__(
        self,
        persist_path: Optional[str | Path] = None,
        force_fallback: bool = False,
    ) -> None:
        self._force_fallback = force_fallback
        self._patterns = _load_pattern_library()
        self._embedder = Embedder(force_tfidf=True)  # TF-IDF always (CI-safe)
        self._store = VectorStore(persist_path=persist_path)
        self._seeded = False

        if not force_fallback:
            self._seed_store()

    # ------------------------------------------------------------------
    # Seeding
    # ------------------------------------------------------------------

    def _seed_store(self) -> None:
        """Load seed bug reports into the vector store if empty."""
        if self._store.count() > 0:
            self._seeded = True
            return

        with _SEED_REPORTS_PATH.open(encoding="utf-8") as f:
            seed_data = json.load(f)

        documents = [f"{r.get('title', '')} {r['description']}" for r in seed_data]
        bug_ids = [r["id"] for r in seed_data]
        sectors = [r.get("sector", "generic") for r in seed_data]
        patterns = [_classify_keyword(doc, self._patterns) for doc in documents]

        # Fit TF-IDF on full seed corpus for better vocabulary coverage
        self._embedder.fit_tfidf(documents)

        embeddings = self._embedder.embed(documents)
        self._store.add_batch(bug_ids, documents, embeddings, patterns, sectors)
        self._seeded = True

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def classify(
        self,
        description: str,
        title: Optional[str] = None,
        sector: Optional[str] = None,
        n_similar: int = 3,
    ) -> ClassificationResult:
        if self._force_fallback or not self._seeded:
            return ClassificationResult(
                pattern=_classify_keyword(f"{title or ''} {description}", self._patterns),
                classified_by="rule-based-fallback",
                confidence=0.6,
            )

        full_text = f"{title or ''} {description}".strip()

        try:
            query_vec = self._embedder.embed([full_text])[0]
            results = self._store.search(
                query_vec,
                n_results=n_similar + 1,  # +1 in case the query itself is in store
                sector_filter=sector,
            )
        except Exception:
            return ClassificationResult(
                pattern=_classify_keyword(full_text, self._patterns),
                classified_by="rule-based-fallback",
                confidence=0.5,
            )

        if not results:
            return ClassificationResult(
                pattern=_classify_keyword(full_text, self._patterns),
                classified_by="rule-based-fallback",
                confidence=0.55,
            )

        # Majority-vote pattern from top neighbours above threshold
        above_threshold = [r for r in results if r.similarity_score >= self._SIMILARITY_THRESHOLD]

        if above_threshold:
            pattern_votes: dict[str, float] = {}
            for r in above_threshold:
                pattern_votes[r.pattern] = (
                    pattern_votes.get(r.pattern, 0.0) + r.similarity_score
                )
            rag_pattern = max(pattern_votes, key=lambda k: pattern_votes[k])

            # Blend with keyword signal for robustness
            keyword_pattern = _classify_keyword(full_text, self._patterns)
            final_pattern = rag_pattern if rag_pattern != "UI_REGRESSION" else keyword_pattern

            top_score = above_threshold[0].similarity_score
            confidence = min(0.95, 0.55 + top_score * 0.8)
        else:
            final_pattern = _classify_keyword(full_text, self._patterns)
            confidence = 0.55

        # Duplicate probability — based on highest similarity
        top_sim = results[0].similarity_score if results else 0.0
        dup_prob = min(1.0, top_sim / self._DUPLICATE_THRESHOLD) if top_sim > 0 else 0.0

        return ClassificationResult(
            pattern=final_pattern,
            similar_bugs=results[:n_similar],
            duplicate_probability=round(dup_prob, 3),
            classified_by="rag-tfidf",
            confidence=round(confidence, 3),
        )

    def add_report(
        self,
        bug_id: str,
        description: str,
        pattern: str,
        sector: str = "generic",
        title: Optional[str] = None,
    ) -> None:
        """Add a new bug report to the store (online learning)."""
        full_text = f"{title or ''} {description}".strip()
        vec = self._embedder.embed([full_text])[0]
        self._store.add(bug_id, full_text, vec, pattern, sector)
