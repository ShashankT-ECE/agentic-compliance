/**
 * TelemetryTable — sortable, filterable broker telemetry event table.
 *
 * Renders ingested telemetry events with per-column sorting, broker/event-type
 * filters, pagination, and an expandable detail view for each row's payload.
 *
 * Also provides an inline ingest form to submit new telemetry events.
 *
 * States handled:
 *  - empty:     no events loaded
 *  - loading:   fetch or ingest in-flight
 *  - error:     fetch or ingest failed
 *  - populated: table rendered
 */

import { useState, useMemo, useCallback, type FormEvent } from 'react';
import useComplianceStore from '../../store/useComplianceStore';
import type { TelemetryEvent, TelemetryInput } from '../../api/client';

// ============================================================================
// Props
// ============================================================================

export interface TelemetryTableProps {
  /** Pre-fetched events to display. If omitted, pulls from the store. */
  events?: TelemetryEvent[] | null;
  /** Show the inline ingest form (default: true). */
  showIngestForm?: boolean;
  /** Callback after successful ingest. */
  onIngested?: (ingested: number) => void;
  /** Callback when a row is clicked (for navigation / drill-down). */
  onEventClick?: (event: TelemetryEvent) => void;
}

// ============================================================================
// Sort / filter types
// ============================================================================

type SortField = 'event_id' | 'event_type' | 'broker_id' | 'timestamp';
type SortDir = 'asc' | 'desc';

// ============================================================================
// Component
// ============================================================================

export default function TelemetryTable({
  events: eventsProp,
  showIngestForm = true,
  onIngested,
  onEventClick,
}: TelemetryTableProps) {
  // ------------------------------------------------------------------
  // Store
  // ------------------------------------------------------------------
  const storeEvents = useComplianceStore((s) => s.telemetryEvents);
  const storeTotal = useComplianceStore((s) => s.telemetryTotal);
  const ingestTelemetry = useComplianceStore((s) => s.ingestTelemetry);
  const queryTelemetry = useComplianceStore((s) => s.queryTelemetry);
  const loadingQuery = useComplianceStore((s) => s.loading.queryTelemetry);
  const loadingIngest = useComplianceStore((s) => s.loading.ingestTelemetry);
  const errorQuery = useComplianceStore((s) => s.errors.queryTelemetry);
  const errorIngest = useComplianceStore((s) => s.errors.ingestTelemetry);

  const events = eventsProp ?? storeEvents;
  const total = eventsProp ? eventsProp.length : storeTotal;

  // ------------------------------------------------------------------
  // Local state
  // ------------------------------------------------------------------
  const [sortField, setSortField] = useState<SortField>('timestamp');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [filterBroker, setFilterBroker] = useState('');
  const [filterType, setFilterType] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const pageSize = 25;

  // Ingest form
  const [ingestText, setIngestText] = useState('');
  const [ingestBrokerId, setIngestBrokerId] = useState('');
  const [ingestResult, setIngestResult] = useState<string | null>(null);

  // ------------------------------------------------------------------
  // Sorting & filtering
  // ------------------------------------------------------------------
  const toggleSort = useCallback(
    (field: SortField) => {
      if (sortField === field) {
        setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
      } else {
        setSortField(field);
        setSortDir('asc');
      }
    },
    [sortField],
  );

  const sorted = useMemo(() => {
    if (!events) return [];
    const list = [...events];

    // Filter
    const filtered = list.filter((e) => {
      if (filterBroker && !e.broker_id.toLowerCase().includes(filterBroker.toLowerCase())) return false;
      if (filterType && !e.event_type.toLowerCase().includes(filterType.toLowerCase())) return false;
      return true;
    });

    // Sort
    filtered.sort((a, b) => {
      let cmp = 0;
      if (sortField === 'timestamp') {
        cmp = new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
      } else {
        cmp = String(a[sortField]).localeCompare(String(b[sortField]));
      }
      return sortDir === 'desc' ? -cmp : cmp;
    });

    return filtered;
  }, [events, filterBroker, filterType, sortField, sortDir]);

  const paged = useMemo(
    () => sorted.slice(page * pageSize, (page + 1) * pageSize),
    [sorted, page],
  );

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));

  // ------------------------------------------------------------------
  // Ingest handler
  // ------------------------------------------------------------------
  async function handleIngest(e: FormEvent) {
    e.preventDefault();
    setIngestResult(null);

    let parsed: TelemetryInput[];
    try {
      parsed = JSON.parse(ingestText);
      if (!Array.isArray(parsed)) parsed = [parsed];
    } catch {
      setIngestResult('❌ Invalid JSON — expected an array of telemetry event objects.');
      return;
    }

    const res = await ingestTelemetry(parsed, ingestBrokerId || undefined);
    if (res) {
      setIngestResult(`✅ ${res.ingested} ingested, ${res.rejected} rejected`);
      setIngestText('');
      onIngested?.(res.ingested);
      // Refresh the table
      queryTelemetry({ limit: 100, offset: 0 });
    }
  }

  // ------------------------------------------------------------------
  // Loading
  // ------------------------------------------------------------------
  if (loadingQuery && !events?.length) {
    return (
      <section className="card">
        <div className="card__header">
          <h2 className="card__title">Telemetry Events</h2>
        </div>
        <div className="card__body">
          <div className="skeleton" style={{ height: '16rem' }} />
        </div>
      </section>
    );
  }

  // ------------------------------------------------------------------
  // Empty
  // ------------------------------------------------------------------
  if (!events?.length && !loadingQuery && !errorQuery) {
    return (
      <section className="card">
        <div className="card__header">
          <h2 className="card__title">Telemetry Events</h2>
        </div>
        <div className="card__body">
          <div className="placeholder-page" style={{ minHeight: '16vh' }}>
            <div className="placeholder-page__icon" aria-hidden="true">📡</div>
            <h3 className="placeholder-page__title">No Telemetry Data</h3>
            <p className="placeholder-page__subtitle">
              Ingest broker telemetry events via the form below, or trigger a pipeline
              with initial telemetry.
            </p>
          </div>

          {showIngestForm && (
            <div style={{ maxWidth: '36rem', margin: '0 auto' }}>
              <IngestForm
                text={ingestText}
                brokerId={ingestBrokerId}
                loading={loadingIngest}
                error={errorIngest ?? ingestResult ?? undefined}
                onTextChange={setIngestText}
                onBrokerIdChange={setIngestBrokerId}
                onSubmit={handleIngest}
              />
            </div>
          )}
        </div>
      </section>
    );
  }

  // ------------------------------------------------------------------
  // Populated
  // ------------------------------------------------------------------
  return (
    <section className="card">
      <div className="card__header">
        <h2 className="card__title">Telemetry Events</h2>
        <span className="badge badge--neutral">
          {total.toLocaleString()} total
        </span>
      </div>

      <div className="card__body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        {/* Filters */}
        <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap', alignItems: 'center' }}>
          <input
            type="text"
            className="field-input"
            placeholder="Filter broker…"
            value={filterBroker}
            onChange={(e) => { setFilterBroker(e.target.value); setPage(0); }}
            style={{ maxWidth: '12rem' }}
          />
          <input
            type="text"
            className="field-input"
            placeholder="Filter event type…"
            value={filterType}
            onChange={(e) => { setFilterType(e.target.value); setPage(0); }}
            style={{ maxWidth: '14rem' }}
          />
          {eventsProp ? null : (
            <button
              type="button"
              className="btn btn--secondary btn--sm"
              disabled={loadingQuery}
              onClick={() => queryTelemetry({ limit: 100, offset: 0 })}
            >
              {loadingQuery ? 'Refreshing…' : 'Refresh'}
            </button>
          )}
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-neutral-400)', marginLeft: 'auto' }}>
            {sorted.length} matching
          </span>
        </div>

        {/* Error */}
        {errorQuery && (
          <div className="inline-error" style={{ marginBottom: 0 }}>
            {errorQuery}
          </div>
        )}

        {/* Table */}
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <SortHeader
                  label="Event ID"
                  field="event_id"
                  current={sortField}
                  dir={sortDir}
                  onClick={toggleSort}
                />
                <SortHeader
                  label="Broker"
                  field="broker_id"
                  current={sortField}
                  dir={sortDir}
                  onClick={toggleSort}
                />
                <SortHeader
                  label="Event Type"
                  field="event_type"
                  current={sortField}
                  dir={sortDir}
                  onClick={toggleSort}
                  style={{ minWidth: '10rem' }}
                />
                <SortHeader
                  label="Timestamp"
                  field="timestamp"
                  current={sortField}
                  dir={sortDir}
                  onClick={toggleSort}
                  style={{ minWidth: '10rem' }}
                />
                <th style={{ width: '2rem' }} aria-label="Expand" />
              </tr>
            </thead>
            <tbody>
              {paged.map((ev) => {
                const isExpanded = expandedId === ev.event_id;
                return (
                  <tr
                    key={ev.event_id}
                    style={{ cursor: 'pointer' }}
                    onClick={() => {
                      setExpandedId(isExpanded ? null : ev.event_id);
                      onEventClick?.(ev);
                    }}
                  >
                    <td>
                      <code style={{ fontSize: 'var(--text-xs)' }}>{ev.event_id}</code>
                    </td>
                    <td style={{ fontWeight: 500 }}>{ev.broker_id}</td>
                    <td>
                      <code style={{ fontSize: 'var(--text-xs)' }}>{ev.event_type}</code>
                    </td>
                    <td style={{ whiteSpace: 'nowrap', fontSize: 'var(--text-sm)' }}>
                      {new Date(ev.timestamp).toLocaleString()}
                    </td>
                    <td>
                      <span
                        style={{
                          display: 'inline-block',
                          transition: 'transform 0.15s',
                          transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
                          color: 'var(--color-neutral-400)',
                        }}
                        aria-hidden="true"
                      >
                        ▶
                      </span>
                    </td>
                  </tr>
                );
              })}

              {/* Expanded detail row */}
              {paged
                .filter((ev) => expandedId === ev.event_id)
                .map((ev) => (
                  <tr key={`${ev.event_id}-detail`}>
                    <td colSpan={5} style={{ padding: 'var(--space-4)', background: 'var(--color-neutral-50)' }}>
                      <EventDetail event={ev} />
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontSize: 'var(--text-sm)',
            }}
          >
            <span style={{ color: 'var(--color-neutral-500)' }}>
              Page {page + 1} of {totalPages}
            </span>
            <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
              <button
                type="button"
                className="btn btn--secondary btn--sm"
                disabled={page <= 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
              >
                ← Prev
              </button>
              <button
                type="button"
                className="btn btn--secondary btn--sm"
                disabled={page >= totalPages - 1}
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              >
                Next →
              </button>
            </div>
          </div>
        )}

        {/* Ingest form */}
        {showIngestForm && (
          <details style={{ marginTop: 'var(--space-4)' }}>
            <summary
              style={{
                cursor: 'pointer',
                fontSize: 'var(--text-sm)',
                fontWeight: 500,
                color: 'var(--color-primary-700)',
              }}
            >
              + Ingest New Telemetry
            </summary>
            <div style={{ marginTop: 'var(--space-3)', maxWidth: '36rem' }}>
              <IngestForm
                text={ingestText}
                brokerId={ingestBrokerId}
                loading={loadingIngest}
                error={errorIngest ?? ingestResult ?? undefined}
                onTextChange={setIngestText}
                onBrokerIdChange={setIngestBrokerId}
                onSubmit={handleIngest}
              />
            </div>
          </details>
        )}
      </div>
    </section>
  );
}

// ============================================================================
// Internal sub-components
// ============================================================================

function SortHeader({
  label,
  field,
  current,
  dir,
  onClick,
  style,
}: {
  label: string;
  field: SortField;
  current: SortField;
  dir: SortDir;
  onClick: (field: SortField) => void;
  style?: React.CSSProperties;
}) {
  const active = field === current;
  return (
    <th
      onClick={() => onClick(field)}
      style={{ cursor: 'pointer', userSelect: 'none', ...style }}
      aria-sort={active ? (dir === 'asc' ? 'ascending' : 'descending') : 'none'}
    >
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--space-1)' }}>
        {label}
        {active && (
          <span aria-hidden="true" style={{ fontSize: '0.7em' }}>
            {dir === 'asc' ? '▲' : '▼'}
          </span>
        )}
      </span>
    </th>
  );
}

function EventDetail({ event }: { event: TelemetryEvent }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'auto 1fr',
          gap: 'var(--space-2) var(--space-4)',
          fontSize: 'var(--text-sm)',
        }}
      >
        <span style={{ color: 'var(--color-neutral-500)' }}>Event ID</span>
        <code style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>{event.event_id}</code>

        <span style={{ color: 'var(--color-neutral-500)' }}>Broker</span>
        <span style={{ fontWeight: 500 }}>{event.broker_id}</span>

        <span style={{ color: 'var(--color-neutral-500)' }}>Type</span>
        <span>{event.event_type}</span>

        <span style={{ color: 'var(--color-neutral-500)' }}>Timestamp</span>
        <span>{new Date(event.timestamp).toLocaleString()}</span>
      </div>

      {/* Payload */}
      <div>
        <div
          style={{
            fontSize: 'var(--text-xs)',
            fontWeight: 600,
            color: 'var(--color-neutral-500)',
            textTransform: 'uppercase',
            letterSpacing: '0.04em',
            marginBottom: 'var(--space-2)',
          }}
        >
          Payload
        </div>
        <pre
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 'var(--text-xs)',
            background: 'var(--color-neutral-100)',
            border: '1px solid var(--color-neutral-300)',
            borderRadius: 'var(--radius-sm)',
            padding: 'var(--space-3)',
            overflowX: 'auto',
            maxHeight: '16rem',
            lineHeight: 1.5,
            margin: 0,
          }}
        >
          {JSON.stringify(event.payload, null, 2)}
        </pre>
      </div>
    </div>
  );
}

function IngestForm({
  text,
  brokerId,
  loading,
  error,
  onTextChange,
  onBrokerIdChange,
  onSubmit,
}: {
  text: string;
  brokerId: string;
  loading: boolean;
  error?: string;
  onTextChange: (v: string) => void;
  onBrokerIdChange: (v: string) => void;
  onSubmit: (e: FormEvent) => void;
}) {
  return (
    <form
      onSubmit={onSubmit}
      style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}
    >
      <label style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
        <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>
          Default Broker ID
        </span>
        <input
          type="text"
          className="field-input"
          value={brokerId}
          onChange={(e) => onBrokerIdChange(e.target.value)}
          placeholder="B-12345"
        />
      </label>

      <label style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
        <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>
          Events (JSON array)
        </span>
        <textarea
          className="field-input"
          rows={6}
          value={text}
          onChange={(e) => onTextChange(e.target.value)}
          placeholder={
            '[{"broker_id":"B-001","event_type":"margin_report_filed","timestamp":"2025-04-29T10:30:00Z","payload":{}}]'
          }
          style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', resize: 'vertical' }}
        />
      </label>

      {error && (
        <div className="inline-error">{error}</div>
      )}

      <button
        type="submit"
        className="btn btn--primary btn--sm"
        disabled={loading || !text.trim()}
        style={{ alignSelf: 'flex-start' }}
      >
        {loading ? 'Ingesting…' : 'Ingest Events'}
      </button>
    </form>
  );
}
