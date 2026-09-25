"""Optional LanceDB-backed semantic ranking store.

Install it with ``brainstem[vector]`` when embeddings improve retrieval for a
repository. Deterministic graph retrieval remains fully functional without
this extra. Embeddings use fastembed's ONNX runtime rather than requiring
PyTorch, and callers may select a compatible model with ``model_name``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import VectorStore

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


class LanceDBVectorStore(VectorStore):
    def __init__(self, db_path: Path, table_name: str = "context", model_name: str = DEFAULT_MODEL) -> None:
        import lancedb
        from fastembed import TextEmbedding

        self._embedder = TextEmbedding(model_name=model_name)
        self._db = lancedb.connect(str(db_path))
        self._table_name = table_name
        self._table = None
        if table_name in self._db.table_names():
            self._table = self._db.open_table(table_name)

    def _embed_one(self, text: str) -> list[float]:
        return next(iter(self._embedder.embed([text]))).tolist()

    def upsert(self, doc_id: str, text: str, metadata: dict[str, Any]) -> None:
        vector = self._embed_one(text)
        row = {"id": doc_id, "vector": vector, "text": text, **metadata}
        if self._table is None:
            self._table = self._db.create_table(self._table_name, data=[row], mode="overwrite")
            return
        self._table.delete(f"id = '{doc_id}'")
        self._table.add([row])

    def search(self, query: str, limit: int = 10) -> list[tuple[str, float, dict[str, Any]]]:
        if self._table is None:
            return []
        vector = self._embed_one(query)
        results = self._table.search(vector).limit(limit).to_list()
        out: list[tuple[str, float, dict[str, Any]]] = []
        for row in results:
            distance = row.pop("_distance", 1.0)
            doc_id = row.pop("id")
            row.pop("vector", None)
            row.pop("text", None)
            score = 1.0 / (1.0 + distance)  # smaller distance -> higher score, bounded (0, 1]
            out.append((doc_id, score, row))
        return out
