/**
 * Evidence Page — interactive regulatory text viewer.
 *
 * V2 M3 — Evidence Traceability.
 *
 * Layout: PDF viewer (left) + Evidence panel (right).
 * Click a verdict in the report → navigates here with the verdict pre-selected.
 */

import { useCallback, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import PDFViewer from '../components/PDFViewer';
import EvidencePanel from '../components/EvidencePanel';
import type { PageRegion } from '../api/client';
import { getCircularPdfUrl } from '../api/client';

export default function EvidencePage() {
  const [searchParams] = useSearchParams();
  const verdictId = searchParams.get('verdictId');
  const circularRef = searchParams.get('circularRef') || '';
  const runId = searchParams.get('runId') || '';

  const [currentPage, setCurrentPage] = useState(1);
  const [highlights, setHighlights] = useState<PageRegion[]>([]);
  const [pdfUrl] = useState(() =>
    circularRef ? getCircularPdfUrl(circularRef) : '',
  );

  const handleNavigateToPage = useCallback((page: number) => {
    setCurrentPage(page);
  }, []);

  const handleHighlightRegions = useCallback((regions: PageRegion[]) => {
    setHighlights(regions);
  }, []);

  // If no circular is specified, show a prompt
  if (!circularRef) {
    return (
      <section className="card">
        <div className="card__header">
          <h2 className="card__title">Evidence Viewer</h2>
        </div>
        <div className="card__body">
          <div className="placeholder-page" style={{ minHeight: '20vh' }}>
            <div className="placeholder-page__icon" aria-hidden="true">🔍</div>
            <p className="placeholder-page__subtitle">
              Run a compliance pipeline and view the report to access evidence traceability.
            </p>
            <p className="placeholder-page__subtitle" style={{ fontSize: 'var(--text-sm)', color: 'var(--color-neutral-500)' }}>
              Navigate from an audit report verdict to see the exact regulatory text that produced each finding.
            </p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="card" style={{ padding: 0 }}>
      <div className="card__header">
        <h2 className="card__title">Evidence Viewer</h2>
        {verdictId && (
          <span className="badge badge--neutral">{verdictId}</span>
        )}
        {runId && (
          <span className="badge badge--neutral" style={{ marginLeft: 'var(--space-2)' }}>
            {runId}
          </span>
        )}
      </div>

      <div className="evidence-page" style={{ padding: 'var(--space-4)' }}>
        {/* Left: PDF Viewer */}
        <div className="evidence-page__viewer">
          {pdfUrl ? (
            <PDFViewer
              pdfUrl={pdfUrl}
              highlights={highlights}
              initialPage={currentPage}
              onPageChange={setCurrentPage}
            />
          ) : (
            <div className="placeholder-page" style={{ minHeight: '20vh' }}>
              <div className="placeholder-page__icon" aria-hidden="true">📄</div>
              <p className="placeholder-page__subtitle">
                Circular PDF not found. Index the circular first.
              </p>
            </div>
          )}
        </div>

        {/* Right: Evidence Panel */}
        <div className="evidence-page__panel">
          <EvidencePanel
            verdictId={verdictId}
            circularRef={circularRef}
            onNavigateToPage={handleNavigateToPage}
            onHighlightRegions={handleHighlightRegions}
          />
        </div>
      </div>
    </section>
  );
}
