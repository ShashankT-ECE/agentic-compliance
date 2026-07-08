"""
Pydantic schemas for the RAG subsystem — V2 M1.

Defines the core data structures shared across chunking, embedding,
vector storage, and retrieval.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChunkMetadata(BaseModel):
    """Metadata attached to every chunk for citation and filtering."""

    circular_ref: str = Field(..., description="SEBI circular reference number")
    section_path: str = Field(
        default="",
        description="Hierarchical section path, e.g. 'III.39.1.2'",
    )
    roman_section: str | None = Field(default=None, description="Roman section label, e.g. 'III'")
    roman_title: str | None = Field(default=None, description="Roman section title")
    topic_number: int | None = Field(default=None, description="Numbered topic, e.g. 39")
    topic_title: str | None = Field(default=None, description="Topic title text")
    sub_section: str | None = Field(default=None, description="Sub-section, e.g. '39.1'")
    chunk_index: int = Field(default=0, description="0-based index within parent section")
    chunk_total: int = Field(default=1, description="Total chunks in parent section")
    char_count: int = Field(default=0, description="Character count of this chunk")


class Chunk(BaseModel):
    """A single chunk of regulatory text with metadata."""

    chunk_id: str = Field(..., description="Unique chunk identifier")
    text: str = Field(..., description="Chunk text content")
    metadata: ChunkMetadata = Field(default_factory=ChunkMetadata)


class RetrievalResult(BaseModel):
    """A single result from a retrieval query."""

    chunk_id: str
    text: str
    score: float
    metadata: dict[str, object]
