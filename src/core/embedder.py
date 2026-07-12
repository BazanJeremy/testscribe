"""Embedder — dual-mode text embedding layer.

Primary (CI-safe): TF-IDF via scikit-learn, no network required.
Production: sentence-transformers all-MiniLM-L6-v2 when available.

Interface is identical regardless of backend — callers see only embed().
See ADR-002 for rationale.
"""

from __future__ import annotations

import os

import numpy as np
from numpy.typing import NDArray
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

# ---------------------------------------------------------------------------
# TF-IDF backend (always available)
# ---------------------------------------------------------------------------

class TfidfEmbedder:
    """Sparse TF-IDF embedder. Fit on first call, then reusable."""

    _DIM = 512  # Fixed output dimension via truncated/padded TF-IDF vocabulary

    def __init__(self) -> None:
        self._vectorizer: TfidfVectorizer | None = None
        self._fitted = False

    def fit(self, corpus: list[str]) -> None:
        self._vectorizer = TfidfVectorizer(
            max_features=self._DIM,
            sublinear_tf=True,
            ngram_range=(1, 2),
            min_df=1,
            strip_accents="unicode",
            token_pattern=r"(?u)\b\w+\b",
        )
        self._vectorizer.fit(corpus)
        self._fitted = True

    def embed(self, texts: list[str]) -> NDArray[np.float32]:
        if not self._fitted or self._vectorizer is None:
            # Fit on the texts themselves (cold-start: only for single queries)
            self.fit(texts)
        matrix = self._vectorizer.transform(texts).toarray().astype(np.float32)
        # Pad or truncate to fixed DIM
        if matrix.shape[1] < self._DIM:
            pad = np.zeros((matrix.shape[0], self._DIM - matrix.shape[1]), dtype=np.float32)
            matrix = np.hstack([matrix, pad])
        elif matrix.shape[1] > self._DIM:
            matrix = matrix[:, : self._DIM]
        # L2-normalise so cosine similarity == dot product
        return normalize(matrix, norm="l2")

    @property
    def dim(self) -> int:
        return self._DIM


# ---------------------------------------------------------------------------
# Neural backend (optional — sentence-transformers)
# ---------------------------------------------------------------------------

class NeuralEmbedder:
    """sentence-transformers MiniLM embedder. Requires network on first use."""

    _MODEL_NAME = "all-MiniLM-L6-v2"

    def __init__(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._model = SentenceTransformer(self._MODEL_NAME)
            self._available = True
        except Exception:
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def embed(self, texts: list[str]) -> NDArray[np.float32]:
        if not self._available:
            raise RuntimeError("sentence-transformers model not available")
        vecs = self._model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return vecs.astype(np.float32)

    @property
    def dim(self) -> int:
        return 384


# ---------------------------------------------------------------------------
# Public facade
# ---------------------------------------------------------------------------

class Embedder:
    """Auto-selects neural or TF-IDF backend.

    Set USE_NEURAL_EMBEDDINGS=true in environment to prefer neural.
    Falls back to TF-IDF if neural is unavailable or if force_tfidf=True.
    """

    def __init__(
        self,
        force_tfidf: bool = False,
        seed_corpus: list[str] | None = None,
    ) -> None:
        use_neural = (
            not force_tfidf
            and os.environ.get("USE_NEURAL_EMBEDDINGS", "").lower() == "true"
        )
        self._neural: NeuralEmbedder | None = None
        self._tfidf = TfidfEmbedder()

        if use_neural:
            neural = NeuralEmbedder()
            if neural.available:
                self._neural = neural

        if seed_corpus:
            self._tfidf.fit(seed_corpus)

    def embed(self, texts: list[str]) -> NDArray[np.float32]:
        if self._neural is not None:
            return self._neural.embed(texts)
        return self._tfidf.embed(texts)

    def fit_tfidf(self, corpus: list[str]) -> None:
        """Pre-fit TF-IDF on a known corpus for better vocabulary coverage."""
        self._tfidf.fit(corpus)

    @property
    def backend(self) -> str:
        return "neural" if self._neural else "tfidf"

    @property
    def dim(self) -> int:
        if self._neural:
            return self._neural.dim
        return self._tfidf.dim
