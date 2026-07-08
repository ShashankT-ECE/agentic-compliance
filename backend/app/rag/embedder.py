"""
Local embedding model wrapper — V2 M1.

Wraps sentence-transformers for generating dense vector embeddings
from regulatory text chunks. Model is loaded lazily on first use.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.rag.config import EmbeddingConfig, RagConfig

logger = logging.getLogger(__name__)

# Default model — small, fast, good retrieval performance on legal text.
_DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


class LocalEmbedder:
    """Generate embeddings using a local sentence-transformers model.

    The model is loaded lazily on the first call to ``encode()`` or
    ``encode_batch()`` to avoid startup cost when embeddings are not
    needed (e.g., during test runs or for V1-only deployments).

    Usage::

        embedder = LocalEmbedder()
        vectors = await embedder.encode(["text chunk 1", "text chunk 2"])
        # vectors is a list[list[float]] with shape (2, 384)

    Dimensions:
        bge-small-en-v1.5  → 384
        bge-base-en-v1.5   → 768
        bge-large-en-v1.5  → 1024
    """

    def __init__(
        self,
        config: RagConfig | EmbeddingConfig | None = None,
    ) -> None:
        if isinstance(config, RagConfig):
            cfg = config.embedding
        elif isinstance(config, EmbeddingConfig):
            cfg = config
        else:
            cfg = EmbeddingConfig()

        self._model_name: str = cfg.model_name or _DEFAULT_MODEL
        self._device: str = cfg.device if cfg.device else "cpu"
        self._batch_size: int = cfg.batch_size if cfg.batch_size else 32
        self._model: Any = None  # Loaded lazily

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def dimension(self) -> int:
        """Return the embedding dimension for the configured model."""
        # Known dimensions for supported models.
        if "large" in self._model_name:
            return 1024
        if "base" in self._model_name:
            return 768
        return 384  # small variant

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    async def encode(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of text strings.

        Args:
            texts: List of text strings to embed.  Must be non-empty.

        Returns:
            List of embedding vectors, each a list of floats with
            length equal to ``self.dimension``.

        Raises:
            ValueError: If ``texts`` is empty.
        """
        if not texts:
            raise ValueError("Cannot encode empty text list")

        self._ensure_loaded()

        # sentence-transformers is synchronous; run in thread to avoid
        # blocking the event loop.
        return await asyncio.to_thread(self._encode_sync, texts)

    async def encode_single(self, text: str) -> list[float]:
        """Convenience wrapper for encoding a single text string."""
        results = await self.encode([text])
        return results[0]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        """Load the model if not already loaded."""
        if self._model is not None:
            return

        logger.info(
            "Loading embedding model '%s' on device '%s' (first use — "
            "this may download ~130 MB on initial run)",
            self._model_name,
            self._device,
        )
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(
                self._model_name,
                device=self._device,
                trust_remote_code=False,
            )
            logger.info(
                "Embedding model loaded: %s (dim=%d)",
                self._model_name,
                self.dimension,
            )
        except Exception:
            logger.exception(
                "Failed to load embedding model '%s'", self._model_name
            )
            raise

    def _encode_sync(self, texts: list[str]) -> list[list[float]]:
        """Synchronous encode (called via asyncio.to_thread)."""
        assert self._model is not None, "Model not loaded"
        # sentence-transformers encode returns a numpy array
        embeddings = self._model.encode(
            texts,
            batch_size=self._batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,  # cosine similarity requires normalized vectors
        )
        # Convert numpy array to list[list[float]]
        return embeddings.tolist()
