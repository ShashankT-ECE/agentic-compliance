"""Initial schema — V2 M4.

Create all 9 tables for the PostgreSQL persistence layer.

Revision ID: 001
Revises: None
Create Date: 2026-07-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # circular_records
    # ------------------------------------------------------------------
    op.create_table(
        "circular_records",
        sa.Column("circular_ref", sa.String(512), nullable=False),
        sa.Column("pdf_path", sa.String(1024), nullable=False),
        sa.Column("title", sa.String(512), nullable=False, server_default=""),
        sa.Column("document_hash", sa.CHAR(64), nullable=False, server_default=""),
        sa.Column("index_version", sa.String(32), nullable=False, server_default="v2-m2"),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("circular_ref"),
    )

    # ------------------------------------------------------------------
    # pipeline_runs (aggregate root)
    # ------------------------------------------------------------------
    op.create_table(
        "pipeline_runs",
        sa.Column("run_id", sa.String(32), nullable=False),
        sa.Column("circular_id", sa.String(512), nullable=False),
        sa.Column("circular_path", sa.String(1024), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="created"),
        sa.Column("approved_by", sa.String(256), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hitl_notes", sa.Text(), nullable=True),
        sa.Column("hash_chain_root", sa.CHAR(64), nullable=True),
        sa.Column("state_blob", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("run_id"),
        sa.ForeignKeyConstraint(["circular_id"], ["circular_records.circular_ref"]),
    )

    # ------------------------------------------------------------------
    # verdicts
    # ------------------------------------------------------------------
    op.create_table(
        "verdicts",
        sa.Column("verdict_id", sa.String(32), nullable=False),
        sa.Column("pipeline_run_id", sa.String(32), nullable=False),
        sa.Column("obligation_ref", sa.String(128), nullable=False),
        sa.Column("broker_id", sa.String(128), nullable=False),
        sa.Column("fsm_ref", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("current_state", sa.String(32), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("verdict_id"),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"], ["pipeline_runs.run_id"], ondelete="CASCADE",
        ),
    )
    op.create_index("ix_verdicts_pipeline_run_id", "verdicts", ["pipeline_run_id"])
    op.create_index("ix_verdicts_broker_id", "verdicts", ["broker_id"])

    # ------------------------------------------------------------------
    # locked_fsms
    # ------------------------------------------------------------------
    op.create_table(
        "locked_fsms",
        sa.Column("locked_fsm_id", sa.String(64), nullable=False),
        sa.Column("pipeline_run_id", sa.String(32), nullable=False),
        sa.Column("fsm_id", sa.String(32), nullable=False),
        sa.Column("obligation_ref", sa.String(128), nullable=False),
        sa.Column("circular_ref", sa.String(512), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending_review"),
        sa.Column("reviewer", sa.String(256), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_comments", sa.Text(), nullable=True),
        sa.Column("integrity_hash", sa.CHAR(64), nullable=True),
        sa.Column("original_fsm", postgresql.JSONB(), nullable=False),
        sa.Column("amendment_history", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("hash_link", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("locked_fsm_id"),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"], ["pipeline_runs.run_id"], ondelete="CASCADE",
        ),
    )
    op.create_index("ix_locked_fsms_pipeline_run_id", "locked_fsms", ["pipeline_run_id"])

    # ------------------------------------------------------------------
    # hitl_review_log (append-only)
    # ------------------------------------------------------------------
    op.create_table(
        "hitl_review_log",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("pipeline_run_id", sa.String(32), nullable=False),
        sa.Column("locked_fsm_id", sa.String(64), nullable=False),
        sa.Column("fsm_id", sa.String(32), nullable=False),
        sa.Column("obligation_ref", sa.String(128), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("reviewer", sa.String(256), nullable=False),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"], ["pipeline_runs.run_id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["locked_fsm_id"], ["locked_fsms.locked_fsm_id"], ondelete="CASCADE",
        ),
    )
    op.create_index("ix_hitl_review_log_pipeline_run_id", "hitl_review_log", ["pipeline_run_id"])
    op.create_index("ix_hitl_review_log_locked_fsm_id", "hitl_review_log", ["locked_fsm_id"])

    # ------------------------------------------------------------------
    # reports
    # ------------------------------------------------------------------
    op.create_table(
        "reports",
        sa.Column("report_id", sa.String(16), nullable=False),
        sa.Column("pipeline_run_id", sa.String(32), nullable=False),
        sa.Column("circular_id", sa.String(512), nullable=False),
        sa.Column("summary", postgresql.JSONB(), nullable=False),
        sa.Column("scoreboard", postgresql.JSONB(), nullable=True),
        sa.Column("verdicts", postgresql.JSONB(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("report_id"),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"], ["pipeline_runs.run_id"], ondelete="CASCADE",
        ),
        sa.UniqueConstraint("pipeline_run_id"),
    )

    # ------------------------------------------------------------------
    # evidence_references
    # ------------------------------------------------------------------
    op.create_table(
        "evidence_references",
        sa.Column("evidence_id", sa.String(16), nullable=False),
        sa.Column("verdict_id", sa.String(32), nullable=False),
        sa.Column("pipeline_run_id", sa.String(32), nullable=False),
        sa.Column("circular_ref", sa.String(512), nullable=False),
        sa.Column("fsm_provenance", postgresql.JSONB(), nullable=False),
        sa.Column("attribution_method", sa.String(32), nullable=False, server_default="conservative"),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("evidence_id"),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"], ["pipeline_runs.run_id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["verdict_id"], ["verdicts.verdict_id"], ondelete="CASCADE",
        ),
        sa.UniqueConstraint("verdict_id"),
    )
    op.create_index("ix_evidence_references_pipeline_run_id", "evidence_references", ["pipeline_run_id"])

    # ------------------------------------------------------------------
    # rag_chunks (Regulatory Knowledge Layer — independent)
    # ------------------------------------------------------------------
    op.create_table(
        "rag_chunks",
        sa.Column("chunk_id", sa.String(256), nullable=False),
        sa.Column("circular_ref", sa.String(512), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("chunk_metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("chunk_id"),
        sa.ForeignKeyConstraint(
            ["circular_ref"], ["circular_records.circular_ref"], ondelete="CASCADE",
        ),
    )
    op.create_index("ix_rag_chunks_circular_ref", "rag_chunks", ["circular_ref"])

    # ------------------------------------------------------------------
    # telemetry_events (standalone)
    # ------------------------------------------------------------------
    op.create_table(
        "telemetry_events",
        sa.Column("event_id", sa.String(64), nullable=False),
        sa.Column("broker_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("event_id", name="uq_telemetry_event_id"),
    )
    op.create_index("ix_telemetry_events_broker_id", "telemetry_events", ["broker_id"])
    op.create_index("ix_telemetry_events_event_type", "telemetry_events", ["event_type"])


def downgrade() -> None:
    op.drop_table("telemetry_events")
    op.drop_table("rag_chunks")
    op.drop_table("evidence_references")
    op.drop_table("reports")
    op.drop_table("hitl_review_log")
    op.drop_table("locked_fsms")
    op.drop_table("verdicts")
    op.drop_table("pipeline_runs")
    op.drop_table("circular_records")
