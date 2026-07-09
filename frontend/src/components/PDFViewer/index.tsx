/**
 * PDFViewer — PDF.js-based regulatory circular viewer with highlight overlays.
 *
 * V2 M3 — Evidence Traceability.
 *
 * Renders a SEBI circular PDF and overlays highlighted regions from
 * ``PageRegion`` data.  Highlights are rendered as semi-transparent
 * coloured rectangles positioned over the PDF canvas.
 *
 * Coordinates are in pdfplumber's native system (top-left origin, y
 * increases downward) which matches PDF.js's canvas coordinate space.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import type { PageRegion } from '../../api/client';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import './PDFViewer.css';

// Use the bundled worker from pdfjs-dist
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

// ============================================================================
// Types
// ============================================================================

export interface PDFViewerProps {
  /** URL to the circular PDF file (e.g. /api/circulars/SEBI/.../pdf). */
  pdfUrl: string;
  /** Page regions to highlight. Keyed by page number for fast lookup. */
  highlights: PageRegion[];
  /** Page to navigate to on mount (1-based). */
  initialPage?: number;
  /** Called when the user navigates to a different page. */
  onPageChange?: (page: number) => void;
  /** Called when the PDF document loads successfully. */
  onLoadSuccess?: (totalPages: number) => void;
  /** Called when the PDF fails to load. */
  onLoadError?: (error: Error) => void;
}

// ============================================================================
// Component
// ============================================================================

export default function PDFViewer({
  pdfUrl,
  highlights,
  initialPage = 1,
  onPageChange,
  onLoadSuccess,
  onLoadError,
}: PDFViewerProps) {
  const [numPages, setNumPages] = useState<number>(0);
  const [currentPage, setCurrentPage] = useState<number>(initialPage);
  const [pageScale, setPageScale] = useState<number>(1);
  const [containerWidth, setContainerWidth] = useState<number>(700);
  const containerRef = useRef<HTMLDivElement>(null);

  // ------------------------------------------------------------------
  // Scale management
  // ------------------------------------------------------------------

  useEffect(() => {
    function handleResize() {
      if (containerRef.current) {
        const w = containerRef.current.clientWidth;
        setContainerWidth(w);
        // Scale page to fit container, with a max for readability
        setPageScale(Math.min(w / 620, 1.15));
      }
    }
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Sync initialPage changes
  useEffect(() => {
    if (initialPage >= 1 && initialPage <= numPages) {
      setCurrentPage(initialPage);
    }
  }, [initialPage, numPages]);

  // ------------------------------------------------------------------
  // PDF load callbacks
  // ------------------------------------------------------------------

  const handleLoadSuccess = useCallback(
    ({ numPages: total }: { numPages: number }) => {
      setNumPages(total);
      onLoadSuccess?.(total);
      if (initialPage > total) setCurrentPage(total);
    },
    [onLoadSuccess, initialPage],
  );

  // ------------------------------------------------------------------
  // Page navigation
  // ------------------------------------------------------------------

  const goToPage = useCallback(
    (page: number) => {
      if (page >= 1 && page <= numPages) {
        setCurrentPage(page);
        onPageChange?.(page);
      }
    },
    [numPages, onPageChange],
  );

  // ------------------------------------------------------------------
  // Highlight lookup (pre-indexed by page)
  // ------------------------------------------------------------------

  const highlightsByPage = useRef<Map<number, PageRegion>>(new Map());
  useEffect(() => {
    const map = new Map<number, PageRegion>();
    for (const h of highlights) {
      map.set(h.page_number, h);
    }
    highlightsByPage.current = map;
  }, [highlights]);

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  return (
    <div className="pdf-viewer" ref={containerRef}>
      {/* Toolbar */}
      <div className="pdf-viewer__toolbar">
        <button
          className="pdf-viewer__nav-btn"
          disabled={currentPage <= 1}
          onClick={() => goToPage(currentPage - 1)}
          title="Previous page"
        >
          ◀
        </button>
        <span className="pdf-viewer__page-info">
          Page {currentPage} of {numPages || '?'}
        </span>
        <button
          className="pdf-viewer__nav-btn"
          disabled={currentPage >= numPages}
          onClick={() => goToPage(currentPage + 1)}
          title="Next page"
        >
          ▶
        </button>

        {numPages > 0 && (
          <input
            className="pdf-viewer__page-input"
            type="number"
            min={1}
            max={numPages}
            value={currentPage}
            onChange={(e) => {
              const p = parseInt(e.target.value, 10);
              if (p >= 1 && p <= numPages) goToPage(p);
            }}
          />
        )}
      </div>

      {/* Document */}
      <div className="pdf-viewer__document">
        <Document
          file={pdfUrl}
          onLoadSuccess={handleLoadSuccess}
          onLoadError={onLoadError}
          loading={
            <div className="pdf-viewer__loading">
              Loading circular PDF...
            </div>
          }
          error={
            <div className="pdf-viewer__error">
              Failed to load PDF. The circular may not be indexed yet.
            </div>
          }
        >
          <div className="pdf-viewer__page-container">
            <Page
              key={`page_${currentPage}`}
              pageNumber={currentPage}
              width={containerWidth * pageScale}
              renderTextLayer={true}
              renderAnnotationLayer={false}
              onRenderSuccess={(page) => {
                // Draw highlights on the canvas after page render
                drawHighlights(page, highlightsByPage.current.get(currentPage));
              }}
            />
          </div>
        </Document>
      </div>
    </div>
  );
}

// ============================================================================
// Highlight rendering
// ============================================================================

/**
 * Draw highlight rectangles on a PDF page's canvas overlay.
 *
 * Coordinates from pdfplumber are in top-left-origin, which matches the
 * PDF.js canvas coordinate space directly.
 */
function drawHighlights(
  _page: unknown,
  region: PageRegion | undefined,
): void {
  if (!region || !region.rectangles || region.rectangles.length === 0) return;

  // Find the canvas element for the current page
  const canvases = document.querySelectorAll(
    '.react-pdf__Page__canvas',
  ) as NodeListOf<HTMLCanvasElement>;

  // The most recently rendered canvas is the current page
  const canvas = canvases[canvases.length - 1];
  if (!canvas) return;

  // Remove previous highlight overlay for this page
  const parent = canvas.parentElement;
  if (!parent) return;
  const existing = parent.querySelector('.pdf-highlight-overlay');
  if (existing) existing.remove();

  // Create overlay canvas
  const overlay = document.createElement('canvas');
  overlay.className = 'pdf-highlight-overlay';
  overlay.width = canvas.width;
  overlay.height = canvas.height;
  overlay.style.position = 'absolute';
  overlay.style.top = '0';
  overlay.style.left = '0';
  overlay.style.pointerEvents = 'none';
  overlay.style.zIndex = '2';

  const ctx = overlay.getContext('2d');
  if (!ctx) return;

  // Compute scale factor: pdfplumber points → canvas pixels
  const scaleX = canvas.width / canvas.clientWidth;
  const scaleY = canvas.height / canvas.clientHeight;

  for (const rect of region.rectangles) {
    const x = rect.x0 * scaleX;
    const y = rect.y0 * scaleY;
    const w = (rect.x1 - rect.x0) * scaleX;
    const h = (rect.y1 - rect.y0) * scaleY;

    ctx.fillStyle = 'rgba(255, 230, 0, 0.35)';
    ctx.fillRect(x, y, w, h);

    ctx.strokeStyle = 'rgba(200, 160, 0, 0.7)';
    ctx.lineWidth = 1;
    ctx.strokeRect(x, y, w, h);
  }

  parent.style.position = 'relative';
  parent.appendChild(overlay);
}
