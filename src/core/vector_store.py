"""VectorStore — ChromaDB wrapper that accepts externally-computed embeddings.

ChromaDB's built-in embedding function requires network access (ONNX model download).
We bypass it entirely by computing embeddings via our Embedder and passing raw vectors.
See ADR-001 for rationale.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import chromadb
import numpy as np
from numpy.typing import NDArray


@dataclass
class SearchResult:
    bug_id: str
    document: str
    pattern: str
    sector: str
    similarity_score: float  # 0.0 (identical) to 1.0 (opposite) — cosine distance
    metadata: dict


class VectorStore:
    """ChromaDB collection with manually supplied embeddings.

    Uses a cosine distance space. Lower distance == more similar.
    Similarity score returned as 1 - distance, clamped to [0, 1].
    """

    COLLECTION_NAME = "bug_reports"

    def __init__(
        self,
        persist_path: str | Path | None = None,
        collection_name: str = COLLECTION_NAME,
    ) -> None:
        if persist_path:
            self._client = chromadb.PersistentClient(path=str(persist_path))
        else:
            self._client = chromadb.Client()

        # embedding_function=None — we supply vectors ourselves
        self._col = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,  # type: ignore[arg-type]
        )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add(
        self,
        bug_id: str,
        document: str,
        embedding: NDArray[np.float32],
        pattern: str,
        sector: str,
        extra_metadata: dict | None = None,
    ) -> None:
        metadata: dict = {"pattern": pattern, "sector": sector}
        if extra_metadata:
            # ChromaDB only supports str/int/float/bool metadata values
            for k, v in extra_metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    metadata[k] = v
        self._col.upsert(
            ids=[bug_id],
            documents=[document],
            embeddings=[embedding.tolist()],
            metadatas=[metadata],
        )

    def add_batch(
        self,
        bug_ids: list[str],
        documents: list[str],
        embeddings: NDArray[np.float32],
        patterns: list[str],
        sectors: list[str],
    ) -> None:
        if not bug_ids:
            return
        metadatas = [
            {"pattern": p, "sector": s} for p, s in zip(patterns, sectors, strict=False)
        ]
        self._col.upsert(
            ids=bug_ids,
            documents=documents,
            embeddings=embeddings.tolist(),
            metadatas=metadatas,
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def search(
        self,
        query_embedding: NDArray[np.float32],
        n_results: int = 5,
        sector_filter: str | None = None,
    ) -> list[SearchResult]:
        count = self._col.count()
        if count == 0:
            return []

        n = min(n_results, count)
        where = {"sector": sector_filter} if sector_filter else None

        try:
            result = self._col.query(
                query_embeddings=[query_embedding.tolist()],
                n_results=n,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            # Fallback without sector filter if filter yields 0 results
            result = self._col.query(
                query_embeddings=[query_embedding.tolist()],
                n_results=n,
                include=["documents", "metadatas", "distances"],
            )

        out: list[SearchResult] = []
        ids = result.get("ids", [[]])[0]
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        for bug_id, doc, meta, dist in zip(ids, docs, metas, distances, strict=False):
            out.append(
                SearchResult(
                    bug_id=bug_id,
                    document=doc,
                    pattern=str(meta.get("pattern", "UNKNOWN")),
                    sector=str(meta.get("sector", "generic")),
                    similarity_score=max(0.0, round(1.0 - float(dist), 4)),
                    metadata=dict(meta),
                )
            )
        return out

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def count(self) -> int:
        return self._col.count()

    def reset(self) -> None:
        """Clear all stored embeddings — useful for test isolation."""
        self._client.delete_collection(self._col.name)
        self._col = self._client.get_or_create_collection(
            name=self._col.name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,  # type: ignore[arg-type]
        )
