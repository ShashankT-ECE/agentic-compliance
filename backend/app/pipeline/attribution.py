"""
Attribution strategies — V2 M3.

Defines how chunks are attributed to obligations during pipeline execution.
The initial implementation is *conservative* (all input chunks → all output
obligations).  Future strategies can provide finer-grained attribution
without changing downstream pipeline code.

Each strategy implements the :class:`AttributionStrategy` protocol.
"""

from __future__ import annotations

from typing import Protocol

from app.models.evidence import ChunkCitation, ObligationSource
from app.models.obligation import ObligationClause
from app.rag.schemas import Chunk


# =============================================================================
# Protocol
# =============================================================================


class AttributionStrategy(Protocol):
    """Protocol for chunk-to-obligation attribution strategies.

    An attribution strategy takes the chunks that were fed to the parser and
    the obligations the parser produced, and returns a mapping from each
    obligation to the chunks that contributed to it.

    The protocol is deliberately minimal — one method — so new strategies
    are trivial to add.
    """

    @property
    def method_name(self) -> str:
        """Human-readable name for this strategy (e.g. 'conservative')."""
        ...

    def attribute(
        self,
        chunks: list[Chunk],
        obligations: list[ObligationClause],
    ) -> list[ObligationSource]:
        """Attribute input chunks to output obligations.

        Args:
            chunks: The chunks that were fed to the parser.
            obligations: The obligations the parser produced.

        Returns:
            One ``ObligationSource`` per obligation, each carrying its
            attributed source chunks.
        """
        ...


# =============================================================================
# Conservative attribution (initial implementation)
# =============================================================================


class ConservativeAttribution:
    """Attribute ALL input chunks to ALL output obligations.

    This is the safest, most defensible strategy for audit: it says "the
    parser had access to these source texts when it produced each
    obligation."  A regulator can verify that the parser *could* have
    produced the obligation from the provided text — which is sufficient
    for audit traceability.

    Future strategies may provide finer-grained attribution (e.g., by
    having the parser annotate which chunks each clause came from, or by
    post-hoc semantic similarity matching).
    """

    @property
    def method_name(self) -> str:
        return "conservative"

    def attribute(
        self,
        chunks: list[Chunk],
        obligations: list[ObligationClause],
    ) -> list[ObligationSource]:
        """Map every input chunk to every output obligation."""
        if not chunks or not obligations:
            return []

        citations = [
            ChunkCitation(
                chunk_id=c.chunk_id,
                citation_text=c.text,
                page_range=(c.metadata.start_page, c.metadata.end_page),
                page_regions=[],  # populated lazily by bbox extractor
            )
            for c in chunks
        ]

        return [
            ObligationSource(
                obligation_ref=obl.clause_id,
                source_chunks=list(citations),
                attribution_method=self.method_name,
            )
            for obl in obligations
        ]


# =============================================================================
# Module-level default
# =============================================================================

#: The attribution strategy used by the pipeline.  Swap this for a different
#: implementation to change how chunks are attributed to obligations without
#: modifying pipeline code.
_default_strategy: AttributionStrategy = ConservativeAttribution()


def get_attribution_strategy() -> AttributionStrategy:
    """Return the current global attribution strategy."""
    return _default_strategy


def set_attribution_strategy(strategy: AttributionStrategy) -> None:
    """Replace the global attribution strategy (primarily for testing)."""
    global _default_strategy
    _default_strategy = strategy
