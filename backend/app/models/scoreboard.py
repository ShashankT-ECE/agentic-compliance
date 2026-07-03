"""
Scoreboard data models.

Defines the output of Node 4 (Scoreboard Generator) — aggregated compliance
results with hash-chain integrity for auditability.

The scoreboard aggregates ComplianceVerdicts per broker and chains each
broker's results into a verifiable hash chain.
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from app.models.verdict import VerdictStatus


# ---------------------------------------------------------------------------
# Hash chain data structures (used by hash_chain utility and scoreboard)
# ---------------------------------------------------------------------------


class HashLink(BaseModel):
    """A single link in the hash chain.

    Each link records a hash of some data, links to the previous link,
    and is itself hashed to form the next link's previous_hash.

    Immutable by design — once created, a HashLink must not be modified.
    """

    index: int = Field(..., ge=0, description="Zero-based position in the chain")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when this link was created",
    )
    data_hash: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="SHA-256 hash of the serialized data payload",
    )
    previous_hash: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="SHA-256 hash of the previous link (all-zeros for genesis)",
    )
    link_hash: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="SHA-256 hash of this link (hash(index + timestamp + data_hash + previous_hash))",
    )


class HashChain(BaseModel):
    """A verifiable hash chain of HashLinks.

    The chain anchors on a root hash and can be verified end-to-end.
    """

    root_hash: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="SHA-256 hash of the genesis link",
    )
    chain: list[HashLink] = Field(
        default_factory=list,
        description="Ordered list of hash links (genesis at index 0)",
    )
    verified_at: datetime | None = Field(
        default=None,
        description="UTC timestamp of the last successful chain verification",
    )

    @property
    def length(self) -> int:
        """Return the number of links in the chain."""
        return len(self.chain)

    @property
    def last_link(self) -> HashLink | None:
        """Return the most recent link, or None if the chain is empty."""
        return self.chain[-1] if self.chain else None


# ---------------------------------------------------------------------------
# Scoreboard models
# ---------------------------------------------------------------------------


class ObligationResult(BaseModel):
    """Result for a single obligation evaluated against a single broker."""

    obligation_ref: str = Field(..., description="Source ObligationClause.clause_id")
    fsm_ref: str = Field(..., description="HybridFSM.fsm_id used for evaluation")
    status: VerdictStatus = Field(..., description="Compliance verdict status")
    current_state: str = Field(..., description="Terminal FSM state after evaluation")
    evidence_summary: str = Field(
        default="",
        description="Human-readable summary of key evidence",
    )
    evaluated_at: datetime = Field(
        ...,
        description="When the verdict was produced",
    )


class BrokerScore(BaseModel):
    """Aggregated compliance score for a single broker.

    Summarises all obligation results for one broker with a composite
    compliance rate and a hash link for chain integrity.
    """

    broker_id: str = Field(..., description="Broker identifier")
    total_obligations: int = Field(..., ge=0, description="Total obligations evaluated")
    compliant: int = Field(..., ge=0, description="Number of compliant verdicts")
    non_compliant: int = Field(..., ge=0, description="Number of non-compliant verdicts")
    pending: int = Field(..., ge=0, description="Number of pending verdicts (evaluation incomplete)")
    compliance_rate: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="compliance_rate = compliant / (total - pending), or 1.0 if all are pending",
    )
    obligation_details: list[ObligationResult] = Field(
        default_factory=list,
        description="Per-obligation breakdown",
    )
    hash_link: HashLink | None = Field(
        default=None,
        description="Hash chain link anchoring this broker's results",
    )

    @model_validator(mode="after")
    def validate_counts_consistent(self) -> "BrokerScore":
        """Ensure compliant + non_compliant + pending == total_obligations."""
        computed = self.compliant + self.non_compliant + self.pending
        if computed != self.total_obligations:
            raise ValueError(
                f"Count mismatch: compliant({self.compliant}) + non_compliant({self.non_compliant}) "
                f"+ pending({self.pending}) = {computed} ≠ total_obligations({self.total_obligations})"
            )
        return self

    @model_validator(mode="after")
    def validate_obligation_details_count(self) -> "BrokerScore":
        """Ensure obligation_details length matches total_obligations."""
        if len(self.obligation_details) != self.total_obligations:
            raise ValueError(
                f"obligation_details count ({len(self.obligation_details)}) "
                f"≠ total_obligations ({self.total_obligations})"
            )
        return self

    @model_validator(mode="after")
    def validate_compliance_rate(self) -> "BrokerScore":
        """Ensure compliance_rate is consistent with the counts."""
        evaluated = self.total_obligations - self.pending
        if evaluated > 0:
            expected = self.compliant / evaluated
            if abs(self.compliance_rate - expected) > 0.001:
                raise ValueError(
                    f"compliance_rate {self.compliance_rate:.4f} does not match "
                    f"compliant({self.compliant}) / (total({self.total_obligations}) - pending({self.pending})) = {expected:.4f}"
                )
        else:
            if self.compliance_rate != 1.0:
                raise ValueError(
                    "compliance_rate must be 1.0 when all obligations are pending"
                )
        return self


class Scoreboard(BaseModel):
    """The final compliance scoreboard — aggregate output of the pipeline.

    Produced by Node 4 (Scoreboard Generator). Contains per-broker summaries
    and an optional hash chain for integrity verification.
    """

    scoreboard_id: str = Field(
        default_factory=lambda: f"SB-{uuid4().hex[:12].upper()}",
        description="Unique scoreboard identifier",
    )
    circular_id: str = Field(
        ...,
        description="SEBI circular reference this scoreboard covers",
    )
    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp of scoreboard generation",
    )
    broker_summaries: list[BrokerScore] = Field(
        default_factory=list,
        description="Per-broker compliance summaries",
    )
    hash_chain: HashChain | None = Field(
        default=None,
        description="Verifiable hash chain for scoreboard integrity (optional until M3)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Pipeline run metadata (run_id, pipeline_version, etc.)",
    )
