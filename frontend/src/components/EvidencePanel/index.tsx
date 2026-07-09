/**
 * EvidencePanel — provenance chain viewer for a compliance verdict.
 *
 * V2 M3 — Evidence Traceability.
 *
 * Displays the full evidence chain: verdict → FSM → obligation → source chunks.
 * Each chunk citation links to its position in the PDF via callbacks.
 */

import { useEffect, useState } from 'react';
import type { EvidenceResponse, PageRegion } from '../../api/client';
import { getEvidenceForFsm, getChunkPositions } from '../../api/client';

// ============================================================================
// Props
// ============================================================================

export interface EvidencePanelProps {
  /** Verdict ID to fetch evidence for. */
  verdictId: string | null;
  /** SEBI circular reference (for resolving positions). */
  circularRef?: string;
  /** Called when the user wants to navigate to a PDF page. */
  onNavigateToPage?: (pageNumber: number) => void;
  /** Called when the user wants to highlight regions in the PDF. */
  onHighlightRegions?: (regions: PageRegion[]) => void;
  /** Called when evidence is loaded (for external state). */
  onEvidenceLoaded?: (evidence: EvidenceResponse | null) => void;
}

// ============================================================================
// Component
// ============================================================================

export default function EvidencePanel({
  verdictId,
  circularRef,
  onNavigateToPage,
  onHighlightRegions,
  onEvidenceLoaded,
}: EvidencePanelProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<EvidenceResponse | null>(null);

  // Fetch evidence when verdictId changes
  useEffect(() => {
    if (!verdictId) {
      setEvidence(null);
      onEvidenceLoaded?.(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    async function fetchEvidence() {
      const resolvedId = verdictId; // captured by closure, non-null here
      if (!resolvedId) return;

      try {
        // Fetch from the FSM evidence endpoint (primary source)
        const data = await getEvidenceForFsm(resolvedId);
        if (!cancelled) {
          // Convert FsmEvidenceResponse shape to Evidence-compatible
          setEvidence({
            evidence_id: `EV-FSM-${resolvedId.slice(0, 12)}`,
            verdict_id: resolvedId,
            circular_ref: data.circular_ref,
            fsm_provenance: {
              fsm_id: data.fsm_id,
              locked_fsm_id: data.locked_fsm_id,
              obligation_source: {
                obligation_ref: data.obligation_ref,
                source_chunks: data.source_chunks.map((c) => ({
                  chunk_id: c.chunk_id,
                  citation_text: c.text,
                  page_range: c.page_range,
                  page_regions: [],
                })),
                attribution_method: 'conservative',
              },
            },
            evaluated_at: new Date().toISOString(),
            pipeline_run_id: null,
            attribution_method: 'conservative',
          });
          setError(null);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load evidence');
          setEvidence(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchEvidence();
    return () => { cancelled = true; };
  }, [verdictId, onEvidenceLoaded]);

  // When evidence loads, notify parent
  useEffect(() => {
    if (evidence) onEvidenceLoaded?.(evidence);
  }, [evidence, onEvidenceLoaded]);

  // Click a chunk → load its positions and highlight
  const handleChunkClick = async (
    chunkId: string,
    pageRange: [number, number],
  ) => {
    onNavigateToPage?.(pageRange[0]);

    if (circularRef) {
      try {
        const pos = await getChunkPositions(chunkId, circularRef);
        if (pos.regions.length > 0) {
          onHighlightRegions?.(pos.regions);
        }
      } catch {
        // Bbox not available — still navigated to page
      }
    }
  };

  // ------------------------------------------------------------------
  // Empty state
  // ------------------------------------------------------------------

  if (!verdictId) {
    return (
      <div className="evidence-panel evidence-panel--empty">
        <p className="evidence-panel__placeholder">
          Select a verdict to view its evidence chain.
        </p>
      </div>
    );
  }

  // ------------------------------------------------------------------
  // Loading
  // ------------------------------------------------------------------

  if (loading) {
    return (
      <div className="evidence-panel evidence-panel--loading">
        <p className="evidence-panel__placeholder">Loading evidence...</p>
      </div>
    );
  }

  // ------------------------------------------------------------------
  // Error
  // ------------------------------------------------------------------

  if (error) {
    return (
      <div className="evidence-panel evidence-panel--error">
        <p className="evidence-panel__placeholder" style={{ color: 'var(--color-danger-500)' }}>
          {error}
        </p>
      </div>
    );
  }

  // ------------------------------------------------------------------
  // No evidence
  // ------------------------------------------------------------------

  if (!evidence) {
    return (
      <div className="evidence-panel evidence-panel--empty">
        <p className="evidence-panel__placeholder">
          No evidence available for this verdict.
        </p>
      </div>
    );
  }

  // ------------------------------------------------------------------
  // Populated
  // ------------------------------------------------------------------

  const obl = evidence.fsm_provenance.obligation_source;
  const chunks = obl.source_chunks;

  return (
    <div className="evidence-panel">
      <h3 className="evidence-panel__title">Evidence Chain</h3>

      {/* Verdict */}
      <div className="evidence-panel__section">
        <h4 className="evidence-panel__section-title">Verdict</h4>
        <code className="evidence-panel__code">{evidence.verdict_id}</code>
        <div className="evidence-panel__meta">
          Circular: {evidence.circular_ref}
        </div>
      </div>

      {/* FSM */}
      <div className="evidence-panel__section">
        <h4 className="evidence-panel__section-title">FSM</h4>
        <code className="evidence-panel__code">
          {evidence.fsm_provenance.fsm_id}
        </code>
        {evidence.fsm_provenance.locked_fsm_id && (
          <div className="evidence-panel__meta">
            Reviewed as:{' '}
            <code>{evidence.fsm_provenance.locked_fsm_id}</code>
          </div>
        )}
      </div>

      {/* Obligation */}
      <div className="evidence-panel__section">
        <h4 className="evidence-panel__section-title">Obligation</h4>
        <code className="evidence-panel__code">{obl.obligation_ref}</code>
        <div className="evidence-panel__meta">
          Attribution: {obl.attribution_method}
        </div>
      </div>

      {/* Source chunks */}
      <div className="evidence-panel__section">
        <h4 className="evidence-panel__section-title">
          Source Chunks ({chunks.length})
        </h4>
        <div className="evidence-panel__chunks">
          {chunks.map((chunk) => (
            <button
              key={chunk.chunk_id}
              className="evidence-panel__chunk-btn"
              type="button"
              onClick={() =>
                handleChunkClick(chunk.chunk_id, chunk.page_range)
              }
              title={`Navigate to page ${chunk.page_range[0]}${chunk.page_range[0] !== chunk.page_range[1] ? `–${chunk.page_range[1]}` : ''}`}
            >
              <div className="evidence-panel__chunk-id">
                {chunk.chunk_id.split('::').pop()}
              </div>
              <div className="evidence-panel__chunk-page">
                Page{chunk.page_range[0] !== chunk.page_range[1] ? 's' : ''}{' '}
                {chunk.page_range[0]}
                {chunk.page_range[0] !== chunk.page_range[1]
                  ? `–${chunk.page_range[1]}`
                  : ''}
              </div>
              <div className="evidence-panel__chunk-text">
                {chunk.citation_text.slice(0, 120)}
                {chunk.citation_text.length > 120 ? '...' : ''}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Attribution */}
      <div className="evidence-panel__section evidence-panel__section--footer">
        <div className="evidence-panel__meta">
          Attribution method: {evidence.attribution_method}
        </div>
        <div className="evidence-panel__meta">
          Evidence ID: {evidence.evidence_id}
        </div>
      </div>
    </div>
  );
}
