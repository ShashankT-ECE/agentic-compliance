"""
Database models — V2 M4.

SQLAlchemy ORM models for the PostgreSQL persistence layer.
These mirror the existing Pydantic schemas and are the source of truth
for all relational data.  Chroma remains the authoritative store for
embedding vectors only.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CHAR,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    JSON,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# =============================================================================
# circular_records
# =============================================================================


class CircularRecordModel(Base):
    """Registered SEBI circular with identity and indexing metadata."""

    __tablename__ = "circular_records"

    circular_ref: Mapped[str] = mapped_column(
        String(512), primary_key=True, comment="SEBI circular reference number"
    )
    pdf_path: Mapped[str] = mapped_column(
        String(1024), nullable=False, comment="Filesystem path to the indexed PDF"
    )
    title: Mapped[str] = mapped_column(
        String(512), default="", nullable=False, comment="Human-readable title"
    )
    document_hash: Mapped[str] = mapped_column(
        CHAR(64), default="", nullable=False, comment="SHA-256 hash of the PDF"
    )
    index_version: Mapped[str] = mapped_column(
        String(32), default="v2-m2", nullable=False, comment="Chunking/embedding version tag"
    )
    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When the circular was indexed"
    )
    chunk_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="Number of chunks produced"
    )
    char_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="Total character count of all chunks"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False,
    )

    def __repr__(self) -> str:
        return f"<CircularRecord {self.circular_ref}>"


# =============================================================================
# pipeline_runs  (aggregate root)
# =============================================================================


class PipelineRunModel(Base):
    """Pipeline execution run — the primary aggregate root.

    The ``state_blob`` column stores the full ``CompliancePipelineState``
    as JSON, providing a complete audit trail.  Scalar fields are
    extracted into columns for queryability.
    """

    __tablename__ = "pipeline_runs"

    run_id: Mapped[str] = mapped_column(
        String(32), primary_key=True, comment="run-{uuid hex[:12]}"
    )
    circular_id: Mapped[str] = mapped_column(
        String(512), ForeignKey("circular_records.circular_ref"),
        nullable=False, comment="SEBI circular reference"
    )
    circular_path: Mapped[str | None] = mapped_column(
        String(1024), nullable=True, comment="Filesystem path to the circular PDF"
    )
    status: Mapped[str] = mapped_column(
        String(32), default="created", nullable=False, comment="PipelineStatus value"
    )
    approved_by: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="HITL reviewer identity"
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="HITL approval timestamp"
    )
    hitl_notes: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Reviewer notes"
    )
    hash_chain_root: Mapped[str | None] = mapped_column(
        CHAR(64), nullable=True, comment="SHA-256 root hash"
    )
    state_blob: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict,
        comment="Full CompliancePipelineState serialized as JSON",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When the run completed"
    )

    # Relationships
    circular: Mapped["CircularRecordModel"] = relationship(
        "CircularRecordModel", lazy="selectin",
    )
    verdicts: Mapped[list["VerdictModel"]] = relationship(
        "VerdictModel", back_populates="pipeline_run", lazy="selectin",
    )
    locked_fsms: Mapped[list["LockedFsmModel"]] = relationship(
        "LockedFsmModel", back_populates="pipeline_run", lazy="selectin",
    )
    evidence_refs: Mapped[list["EvidenceReferenceModel"]] = relationship(
        "EvidenceReferenceModel", back_populates="pipeline_run", lazy="selectin",
    )
    report: Mapped["ReportModel | None"] = relationship(
        "ReportModel", back_populates="pipeline_run", uselist=False, lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<PipelineRun {self.run_id} [{self.status}]>"


# =============================================================================
# verdicts
# =============================================================================


class VerdictModel(Base):
    """Compliance verdict — one per obligation per broker per run."""

    __tablename__ = "verdicts"

    verdict_id: Mapped[str] = mapped_column(
        String(32), primary_key=True, comment="VER-{uuid hex[:12]}"
    )
    pipeline_run_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("pipeline_runs.run_id", ondelete="CASCADE"),
        nullable=False, index=True, comment="Owning pipeline run"
    )
    obligation_ref: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="ObligationClause.clause_id"
    )
    broker_id: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True, comment="Broker identifier"
    )
    fsm_ref: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="LockedFSM reference"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="VerdictStatus: compliant/non_compliant/pending"
    )
    current_state: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="FSM state name at evaluation time"
    )
    evidence: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, comment="Evidence trail dict"
    )
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="Evaluation timestamp"
    )

    # Relationships
    pipeline_run: Mapped["PipelineRunModel"] = relationship(
        "PipelineRunModel", back_populates="verdicts",
    )

    def __repr__(self) -> str:
        return f"<Verdict {self.verdict_id} [{self.status}]>"


# =============================================================================
# locked_fsms
# =============================================================================


class LockedFsmModel(Base):
    """Human-reviewed LockedFSM — one per obligation per run."""

    __tablename__ = "locked_fsms"

    locked_fsm_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="LOCKED-{uuid}"
    )
    pipeline_run_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("pipeline_runs.run_id", ondelete="CASCADE"),
        nullable=False, index=True, comment="Owning pipeline run"
    )
    fsm_id: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="HybridFSM.fsm_id"
    )
    obligation_ref: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="ObligationClause.clause_id"
    )
    circular_ref: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="SEBI circular reference"
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="Amendment version"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending_review",
        comment="LockStatus: pending_review/approved/rejected/amended"
    )
    reviewer: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="Reviewer identity"
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    review_comments: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Reviewer comments or rationale"
    )
    integrity_hash: Mapped[str | None] = mapped_column(
        CHAR(64), nullable=True, comment="SHA-256 integrity hash"
    )
    original_fsm: Mapped[dict] = mapped_column(
        JSON, nullable=False, comment="Full HybridFSM serialized"
    )
    amendment_history: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=list, comment="list[AmendmentRecord]"
    )
    hash_link: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="HashLink for chain integrity"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False,
    )

    # Relationships
    pipeline_run: Mapped["PipelineRunModel"] = relationship(
        "PipelineRunModel", back_populates="locked_fsms",
    )

    def __repr__(self) -> str:
        return f"<LockedFSM {self.locked_fsm_id} [{self.status}]>"


# =============================================================================
# hitl_review_log  (append-only audit trail)
# =============================================================================


class HitlReviewLogModel(Base):
    """Immutable HITL review audit trail — INSERT only, never UPDATE or DELETE."""

    __tablename__ = "hitl_review_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    pipeline_run_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("pipeline_runs.run_id", ondelete="CASCADE"),
        nullable=False, index=True, comment="Owning pipeline run"
    )
    locked_fsm_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("locked_fsms.locked_fsm_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    fsm_id: Mapped[str] = mapped_column(
        String(32), nullable=False,
    )
    obligation_ref: Mapped[str] = mapped_column(
        String(128), nullable=False,
    )
    action: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="approved/rejected/amended"
    )
    reviewer: Mapped[str] = mapped_column(
        String(256), nullable=False,
    )
    comments: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False,
    )

    def __repr__(self) -> str:
        return f"<HitlReviewLog {self.id} [{self.action}]>"


# =============================================================================
# reports
# =============================================================================


class ReportModel(Base):
    """Generated compliance audit report."""

    __tablename__ = "reports"

    report_id: Mapped[str] = mapped_column(
        String(16), primary_key=True, comment="RPT-{uuid hex[:12]}"
    )
    pipeline_run_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("pipeline_runs.run_id", ondelete="CASCADE"),
        nullable=False, unique=True, comment="One report per completed run"
    )
    circular_id: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="SEBI circular reference"
    )
    summary: Mapped[dict] = mapped_column(
        JSON, nullable=False, comment="ReportSummary dict"
    )
    scoreboard: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Full Scoreboard serialized"
    )
    verdicts: Mapped[dict] = mapped_column(
        JSON, nullable=False, comment="list[serialized verdicts]"
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="Report generation timestamp"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False,
    )

    # Relationships
    pipeline_run: Mapped["PipelineRunModel"] = relationship(
        "PipelineRunModel", back_populates="report",
    )

    def __repr__(self) -> str:
        return f"<Report {self.report_id}>"


# =============================================================================
# evidence_references
# =============================================================================


class EvidenceReferenceModel(Base):
    """Evidence chain linking a verdict back to source regulatory text."""

    __tablename__ = "evidence_references"

    evidence_id: Mapped[str] = mapped_column(
        String(16), primary_key=True, comment="EV-{uuid hex[:12]}"
    )
    verdict_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("verdicts.verdict_id", ondelete="CASCADE"),
        nullable=False, unique=True, comment="One evidence per verdict"
    )
    pipeline_run_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("pipeline_runs.run_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    circular_ref: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="SEBI circular reference"
    )
    fsm_provenance: Mapped[dict] = mapped_column(
        JSON, nullable=False,
        comment="FSMProvenance -> ObligationSource -> [ChunkCitation] chain"
    )
    attribution_method: Mapped[str] = mapped_column(
        String(32), nullable=False, default="conservative",
    )
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False,
    )

    # Relationships
    pipeline_run: Mapped["PipelineRunModel"] = relationship(
        "PipelineRunModel", back_populates="evidence_refs",
    )

    def __repr__(self) -> str:
        return f"<EvidenceReference {self.evidence_id}>"


# =============================================================================
# rag_chunks  (Regulatory Knowledge Layer — independent)
# =============================================================================


class RagChunkModel(Base):
    """Chunk text and metadata — PostgreSQL home for chunk data.

    Chroma stores embedding vectors only.  This table is the authoritative
    store for chunk text and structured metadata.  It belongs to the
    Regulatory Knowledge Layer and is independent of pipeline runs.
    """

    __tablename__ = "rag_chunks"

    chunk_id: Mapped[str] = mapped_column(
        String(256), primary_key=True,
        comment="e.g. SEBI/HO/.../2025/57::chunk::t39::000"
    )
    circular_ref: Mapped[str] = mapped_column(
        String(512), ForeignKey("circular_records.circular_ref", ondelete="CASCADE"),
        nullable=False, index=True, comment="Owning circular"
    )
    text: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Chunk regulatory text"
    )
    chunk_metadata: Mapped[dict] = mapped_column(
        "chunk_metadata", JSON, nullable=False, default=dict,
        comment="All ChunkMetadata fields (section_path, topic_number, page_range, etc.)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False,
    )

    def __repr__(self) -> str:
        return f"<RagChunk {self.chunk_id}>"


# =============================================================================
# telemetry_events  (standalone — no FK to pipeline runs)
# =============================================================================


class TelemetryEventModel(Base):
    """Ingested broker telemetry events — independent of pipeline runs."""

    __tablename__ = "telemetry_events"

    event_id: Mapped[str] = mapped_column(
        String(64), primary_key=True,
    )
    broker_id: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    payload: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict,
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("event_id", name="uq_telemetry_event_id"),
    )

    def __repr__(self) -> str:
        return f"<TelemetryEvent {self.event_id}>"
