"""Local CPU semantic vector embedder using FastEmbed (BAAI/bge-small-en-v1.5 ONNX)."""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Protocol, Sequence

import numpy as np


class EmbedderProtocol(Protocol):
    """Protocol allowing real FastEmbed or deterministic test doubles."""

    def embed_texts(self, texts: Sequence[str]) -> np.ndarray:
        """Return an L2-normalized float32 matrix of shape (len(texts), dim)."""
        ...


class FastEmbedService:
    """Thread-safe lazy singleton wrapping FastEmbed ONNX Runtime."""

    def __init__(self, model_name: str, cache_dir: Path, dim: int = 384) -> None:
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.dim = dim
        self._model = None
        self._lock = Lock()

    def _get_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from fastembed import TextEmbedding

                    self.cache_dir.mkdir(parents=True, exist_ok=True)
                    self._model = TextEmbedding(
                        model_name=self.model_name,
                        cache_dir=str(self.cache_dir),
                    )
        return self._model

    def embed_texts(self, texts: Sequence[str]) -> np.ndarray:
        """Compute L2-normalized float32 embeddings for a sequence of strings."""
        cleaned = [t.strip() for t in texts]
        if not cleaned:
            return np.zeros((0, self.dim), dtype=np.float32)

        model = self._get_model()
        vectors = np.asarray(list(model.embed(cleaned)), dtype=np.float32)
        return l2_normalize_matrix(vectors)


def l2_normalize_matrix(matrix: np.ndarray) -> np.ndarray:
    """Normalize rows of a 2D float32 matrix to unit length."""
    if matrix.size == 0:
        return matrix.astype(np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    safe_norms = np.where(norms == 0.0, 1.0, norms)
    return (matrix / safe_norms).astype(np.float32)


def vector_to_blob(vector: np.ndarray) -> bytes:
    """Serialize a 1D float32 vector to raw SQLite BLOB bytes."""
    return np.asarray(vector, dtype=np.float32).tobytes()


def blob_to_vector(blob: bytes) -> np.ndarray:
    """Deserialize raw SQLite BLOB bytes back into a 1D float32 vector."""
    return np.frombuffer(blob, dtype=np.float32)


def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """Compute cosine similarity between two 1D float32 vectors."""
    norm_a = float(np.linalg.norm(vec_a))
    norm_b = float(np.linalg.norm(vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))

