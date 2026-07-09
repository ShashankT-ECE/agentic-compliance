"""
Evidence service — V2 M3.

Orchestrates the construction of ``EvidenceReference`` objects by
coordinating the attribution strategy, bounding-box extractor, and
registry lookups.

The API calls this service rather than wiring the components directly,
keeping the endpoint layer thin.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.models.evidence import (
    ChunkCitation,
    EvidenceReference,
    FSMProvenance,
    ObligationSource,
    PageRegion,
)
from app.models.obligation import ObligationClause
from app.models.verdict import ComplianceVerdict
from app.pipeline.attribution import get_attribution_strategy
from app.rag.schemas import Chunk
from app.utils.bbox_extractor import BoundingBoxExtractor

logger = logging.getLogger(__name__)


class EvidenceService:
    """Build evidence references from pipeline artifacts.

    Usage::

        service = EvidenceService()
        evidence = service.build_evidence(
            verdicts=verdicts,
            chunks=chunks,
            obligations=obligations,
            circular_ref="SEBI/HO/...",
            pdf_path="data/circulars/circ.pdf",
            run_id="run-abc123",
        )
    """

    def __init__(self, bbox_cache_dir: str | Path | None = None) -> None:
        self._bbox = BoundingBoxExtractor(cache_dir=bbox_cache_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_evidence(
        self,
        *,
        verdicts: list[ComplianceVerdict],
        chunks: list[Chunk],
        obligations: list[ObligationClause],
        circular_ref: str,
        pdf_path: str | Path,
        run_id: str | None = None,
        enrich_bbox: bool = False,
    ) -> dict[str, EvidenceReference]:
        """Build one ``EvidenceReference`` per verdict.

        Args:
            verdicts: The verdicts produced by the evaluator.
            chunks: The input chunks fed to the parser.
            obligations: The obligations produced by the parser.
            circular_ref: SEBI circular reference.
            pdf_path: Path to the source PDF (for bbox extraction).
            run_id: Optional pipeline run identifier.
            enrich_bbox: If True, populate ``page_regions`` on every
                ``ChunkCitation`` by calling the bounding-box extractor.
                This is expensive — only enable for completed runs.

        Returns:
            A dict mapping ``verdict_id`` → ``EvidenceReference``.
        """
        if not verdicts:
            return {}

        # 1. Attribution: chunks → obligations
        strategy = get_attribution_strategy()
        obl_sources = strategy.attribute(chunks, obligations)
        obl_map: dict[str, ObligationSource] = {
            src.obligation_ref: src for src in obl_sources
        }

        # 2. Build obligation → FSM map from verdicts
        #    Each verdict carries obligation_ref and fsm_ref.
        fsm_to_obl: dict[str, str] = {}  # fsm_ref → obligation_ref
        for v in verdicts:
            fsm_to_obl[v.fsm_ref] = v.obligation_ref

        # 3. Optionally enrich with bounding boxes
        if enrich_bbox:
            self._enrich_citations(list(obl_map.values()), pdf_path)

        # 4. Assemble one EvidenceReference per verdict
        result: dict[str, EvidenceReference] = {}
        for v in verdicts:
            obl_source = obl_map.get(
                v.obligation_ref,
                ObligationSource(obligation_ref=v.obligation_ref),
            )
            evidence = EvidenceReference(
                verdict_id=v.verdict_id,
                circular_ref=circular_ref,
                fsm_provenance=FSMProvenance(
                    fsm_id=v.fsm_ref,
                    obligation_source=obl_source,
                ),
                pipeline_run_id=run_id,
                attribution_method=strategy.method_name,
            )
            result[v.verdict_id] = evidence

        return result

    def build_evidence_for_verdict(
        self,
        verdict: ComplianceVerdict,
        chunks: list[Chunk],
        obligations: list[ObligationClause],
        circular_ref: str,
        pdf_path: str | Path,
        run_id: str | None = None,
        enrich_bbox: bool = False,
    ) -> EvidenceReference | None:
        """Build evidence for a single verdict.

        Returns None if the verdict's obligation cannot be matched.
        """
        result = self.build_evidence(
            verdicts=[verdict],
            chunks=chunks,
            obligations=obligations,
            circular_ref=circular_ref,
            pdf_path=pdf_path,
            run_id=run_id,
            enrich_bbox=enrich_bbox,
        )
        return result.get(verdict.verdict_id)

    def get_chunk_positions(
        self,
        chunk: Chunk,
        pdf_path: str | Path,
    ) -> list[PageRegion]:
        """Return cached (or freshly extracted) page regions for a chunk."""
        return self._bbox.load_or_extract(
            chunk_id=chunk.chunk_id,
            pdf_path=pdf_path,
            chunk_text=chunk.text,
            start_page=chunk.metadata.start_page,
            end_page=chunk.metadata.end_page,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _enrich_citations(
        self,
        obl_sources: list[ObligationSource],
        pdf_path: str | Path,
    ) -> None:
        """Populate ``page_regions`` on every chunk citation in-place.

        Extracts bounding boxes for all unique chunks referenced across
        all obligation sources.  Results are cached to disk, so repeated
        calls for the same chunks are cheap.
        """
        # Collect unique (chunk_id, chunk) pairs
        seen: set[str] = set()
        citations: list[ChunkCitation] = []
        for src in obl_sources:
            for cit in src.source_chunks:
                if cit.chunk_id not in seen:
                    seen.add(cit.chunk_id)
                    citations.append(cit)

        if not citations:
            return

        # Build batch input
        batch_input: list[tuple[str, int, int]] = []
        for cit in citations:
            sp, ep = cit.page_range
            batch_input.append((cit.citation_text, sp, ep))

        # Extract all in one batch (opens the PDF once)
        try:
            all_regions = self._bbox.extract_batch(pdf_path, batch_input)
            for cit, regions in zip(citations, all_regions):
                if regions:
                    cit.page_regions = regions
        except Exception:
            logger.exception(
                "Failed to enrich citations with bbox data for %s", pdf_path
            )
