"""
RAG configuration — V2 M1.

Pydantic model for RAG parameters, loaded from YAML with sensible defaults.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Default config path, relative to the backend directory.
_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "rag.yaml"


class ChunkingConfig(BaseModel):
    """Chunking parameters."""

    target_chunk_size: int = Field(default=1500, description="Target characters per chunk")
    min_chunk_size: int = Field(default=500, description="Merge chunks smaller than this")
    max_chunk_size: int = Field(default=3000, description="Split chunks larger than this")
    never_split_mid_paragraph: bool = Field(default=True)


class EmbeddingConfig(BaseModel):
    """Embedding model parameters."""

    provider: str = Field(default="local", description="Embedding provider: local | openai")
    model_name: str = Field(default="BAAI/bge-small-en-v1.5")
    device: str = Field(default="cpu")
    batch_size: int = Field(default=32, ge=1)


class ChromaConfig(BaseModel):
    """Chroma vector store parameters."""

    persist_directory: str = Field(default="data/chroma_db")
    collection_name: str = Field(default="sebi_circulars")


class VectorStoreConfig(BaseModel):
    """Vector store configuration."""

    provider: str = Field(default="chroma")
    chroma: ChromaConfig = Field(default_factory=ChromaConfig)


class RetrievalConfig(BaseModel):
    """Retrieval parameters."""

    default_top_k: int = Field(default=10, ge=1, le=100)
    max_top_k: int = Field(default=50, ge=1, le=200)
    similarity_threshold: float = Field(default=0.3, ge=0.0, le=1.0)


class RagConfig(BaseModel):
    """Top-level RAG configuration."""

    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)


def load_rag_config(config_path: str | Path | None = None) -> RagConfig:
    """Load RAG configuration from a YAML file, falling back to defaults.

    Args:
        config_path: Optional path to a rag.yaml file.  If None, the default
                     ``backend/config/rag.yaml`` is used.  If that file does
                     not exist, pure defaults are returned.

    Returns:
        A validated RagConfig instance.
    """
    path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH

    if not path.exists():
        logger.info("RAG config not found at %s — using defaults", path)
        return RagConfig()

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        logger.exception("Failed to load RAG config from %s — using defaults", path)
        return RagConfig()

    # Pydantic handles nested validation and default-filling.
    return RagConfig(**raw)
