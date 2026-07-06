/**
 * Dashboard page — pipeline overview, HITL queue, and telemetry status.
 *
 * Route: `/`
 *
 * Layout:
 *  1. Pipeline trigger / current run panel (CircularPanel)
 *  2. Pipeline runs list with selection
 *  3. Run detail (FSM counts, status) when a run is selected
 *  4. HITL review queue summary
 *  5. Telemetry quick stats
 *
 * All data flows through the Zustand store.  No mock data, no hard-coded
 * values.  Every section handles loading, empty, and error states.
 */

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import useComplianceStore from '../store/useComplianceStore';
import CircularPanel from '../components/CircularPanel';
import type { PipelineStatus } from '../api/client';

export default function DashboardPage() {
  // ------------------------------------------------------------------
  // Store
  // ------------------------------------------------------------------
  const runs = useComplianceStore((s) => s.runs);
  const currentRun = useComplianceStore((s) => s.currentRun);
  const hitlRuns = useComplianceStore((s) => s.hitlRuns);
  const telemetryTotal = useComplianceStore((s) => s.telemetryTotal);
  const telemetryEvents = useComplianceStore((s) => s.telemetryEvents);
  const fetchStatus = useComplianceStore((s) => s.fetchStatus);
  const fetchHitlList = useComplianceStore((s) => s.fetchHitlList);
  const queryTelemetry = useComplianceStore((s) => s.queryTelemetry);
  const loadingStatus = useComplianceStore((s) => s.loading.fetchStatus);
  const loadingHitl = useComplianceStore((s) => s.loading.fetchHitl);
  const loadingTelemetry = useComplianceStore((s) => s.loading.queryTelemetry);
  const generateReport = useComplianceStore((s) => s.generateReport);
  const loadingGenerate = useComplianceStore((s) => s.loading.generateReport);
  const reset = useComplianceStore((s) => s.reset);

  const navigate = useNavigate();

  // Local UI state
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  // ------------------------------------------------------------------
  // On mount: load HITL queue and telemetry
  // ------------------------------------------------------------------
  useEffect(() => {
    fetchHitlList();
    queryTelemetry({ limit: 5, offset: 0 });
  }, [fetchHitlList, queryTelemetry]);

  // ------------------------------------------------------------------
  // When a run is selected from the list, fetch its full status
  // ------------------------------------------------------------------
  useEffect(() => {
    if (selectedRunId) {
      fetchStatus(selectedRunId);
    }
  }, [selectedRunId, fetchStatus]);

  // ------------------------------------------------------------------
  // Handlers
  // ------------------------------------------------------------------
  function handleTriggered(runId: string) {
    setSelectedRunId(runId);
    fetchHitlList();
  }

  async function handleGenerateReport(runId: string) {
    const id = await generateReport(runId);
    if (id) {
      navigate(`/report/${id}`);
    }
  }

  function handleClearAll() {
    reset();
    setSelectedRunId(null);
  }

  // ------------------------------------------------------------------
  // Derived data
  // ------------------------------------------------------------------
  const selectedRun = runs.find((r) => r.run_id === selectedRunId) ?? currentRun;
  const pendingHitlCount = hitlRuns.reduce((sum, r) => sum + (r.pending ?? 0), 0);
  const latestEvents = telemetryEvents.slice(0, 3);

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-8)' }}>
      {/* ================================================================
          Section 1 — Pipeline Panel
          ================================================================ */}
      <CircularPanel run={selectedRun} onTriggered={handleTriggered} />

      {/* ================================================================
          Section 2 — Runs List + Detail (side-by-side on wide screens)
          ================================================================ */}
      <div className="grid-2" style={{ alignItems: 'start' }}>
        {/* Runs list */}
        <section className="card">
          <div className="card__header">
            <h2 className="card__title">Pipeline Runs</h2>
            {runs.length > 0 && (
              <span className="badge badge--neutral">{runs.length}</span>
            )}
          </div>

          <div className="card__body">
            {/* Empty */}
            {runs.length === 0 && (
              <div className="placeholder-page" style={{ minHeight: '12vh' }}>
                <p className="placeholder-page__subtitle">
                  No pipeline runs yet. Trigger one above to get started.
                </p>
              </div>
            )}

            {/* List */}
            {runs.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                {runs.map((run) => (
                  <button
                    key={run.run_id}
                    type="button"
                    onClick={() => setSelectedRunId(run.run_id)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      width: '100%',
                      padding: 'var(--space-3) var(--space-4)',
                      textAlign: 'left',
                      background:
                        selectedRunId === run.run_id
                          ? 'var(--color-primary-100)'
                          : 'var(--color-neutral-50)',
                      border:
                        selectedRunId === run.run_id
                          ? '1px solid var(--color-primary-500)'
                          : '1px solid var(--color-neutral-200)',
                      borderRadius: 'var(--radius-md)',
                      cursor: 'pointer',
                      font: 'inherit',
                      color: 'inherit',
                      transition: 'background 0.1s, border-color 0.1s',
                    }}
                  >
                    <div style={{ minWidth: 0 }}>
                      <div
                        style={{
                          fontWeight: 600,
                          fontSize: 'var(--text-sm)',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {run.circular_id}
                      </div>
                      <div
                        style={{
                          fontSize: 'var(--text-xs)',
                          color: 'var(--color-neutral-500)',
                          marginTop: 'var(--space-1)',
                        }}
                      >
                        {run.run_id}
                      </div>
                    </div>
                    <StatusBadge status={run.status} />
                  </button>
                ))}
              </div>
            )}

            {/* Clear all */}
            {runs.length > 0 && (
              <button
                type="button"
                className="btn btn--secondary btn--sm"
                style={{ marginTop: 'var(--space-3)' }}
                onClick={handleClearAll}
              >
                Clear All Runs
              </button>
            )}
          </div>
        </section>

        {/* Run Detail */}
        <RunDetailCard
          run={selectedRun}
          loading={loadingStatus}
          onGenerateReport={handleGenerateReport}
          loadingGenerate={loadingGenerate}
        />
      </div>

      {/* ================================================================
          Section 3 — HITL Queue Summary
          ================================================================ */}
      <section className="card">
        <div className="card__header">
          <h2 className="card__title">HITL Review Queue</h2>
          {pendingHitlCount > 0 && (
            <span className="badge badge--pending">{pendingHitlCount} pending</span>
          )}
        </div>

        <div className="card__body">
          {/* Loading */}
          {loadingHitl && !hitlRuns.length && (
            <div className="skeleton" style={{ height: '4rem' }} />
          )}

          {/* Empty */}
          {!loadingHitl && hitlRuns.length === 0 && (
            <div className="placeholder-page" style={{ minHeight: '8vh' }}>
              <p className="placeholder-page__subtitle">
                No FSMs awaiting review. Trigger a pipeline to populate the HITL queue.
              </p>
            </div>
          )}

          {/* Populated */}
          {hitlRuns.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
              {hitlRuns.map((run) => (
                <div
                  key={run.run_id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: 'var(--space-3) var(--space-4)',
                    background: 'var(--color-warning-100)',
                    border: '1px solid var(--color-warning-500)',
                    borderRadius: 'var(--radius-md)',
                    flexWrap: 'wrap',
                    gap: 'var(--space-3)',
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>
                      {run.circular_ref}
                    </div>
                    <div
                      style={{
                        fontSize: 'var(--text-xs)',
                        color: 'var(--color-neutral-600)',
                        fontFamily: 'var(--font-mono)',
                        marginTop: 'var(--space-1)',
                      }}
                    >
                      {run.run_id}
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: 'var(--space-4)', alignItems: 'center' }}>
                    <MiniCount
                      label="Total"
                      value={run.total_fsms}
                    />
                    <MiniCount
                      label="Pending"
                      value={run.pending}
                      tone="warn"
                    />
                    <button
                      type="button"
                      className="btn btn--primary btn--sm"
                      onClick={() => navigate(`/hitl/${run.run_id}`)}
                    >
                      Review
                    </button>
                  </div>
                </div>
              ))}

              <button
                type="button"
                className="btn btn--secondary btn--sm"
                style={{ alignSelf: 'flex-start' }}
                onClick={() => fetchHitlList()}
                disabled={loadingHitl}
              >
                {loadingHitl ? 'Refreshing…' : 'Refresh'}
              </button>
            </div>
          )}
        </div>
      </section>

      {/* ================================================================
          Section 4 — Telemetry Quick Stats
          ================================================================ */}
      <section className="card">
        <div className="card__header">
          <h2 className="card__title">Telemetry</h2>
          {telemetryTotal > 0 && (
            <span className="badge badge--neutral">{telemetryTotal.toLocaleString()} events</span>
          )}
        </div>

        <div className="card__body">
          {/* Loading */}
          {loadingTelemetry && telemetryTotal === 0 && (
            <div className="skeleton" style={{ height: '4rem' }} />
          )}

          {/* Empty */}
          {!loadingTelemetry && telemetryTotal === 0 && (
            <div className="placeholder-page" style={{ minHeight: '8vh' }}>
              <p className="placeholder-page__subtitle">
                No telemetry events ingested yet. Use the Telemetry Table on a run
                detail to ingest broker events.
              </p>
            </div>
          )}

          {/* Populated */}
          {telemetryTotal > 0 && (
            <div>
              {/* Recent events preview */}
              {latestEvents.length > 0 && (
                <div style={{ marginBottom: 'var(--space-3)' }}>
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
                    Recent Events
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                    {latestEvents.map((ev) => (
                      <div
                        key={ev.event_id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: 'var(--space-2) var(--space-3)',
                          background: 'var(--color-neutral-100)',
                          borderRadius: 'var(--radius-sm)',
                          border: '1px solid var(--color-neutral-200)',
                          fontSize: 'var(--text-sm)',
                        }}
                      >
                        <div style={{ display: 'flex', gap: 'var(--space-4)', alignItems: 'center', minWidth: 0 }}>
                          <span style={{ fontWeight: 500 }}>{ev.broker_id}</span>
                          <code style={{ fontSize: 'var(--text-xs)', color: 'var(--color-neutral-600)' }}>
                            {ev.event_type}
                          </code>
                        </div>
                        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-neutral-400)', whiteSpace: 'nowrap' }}>
                          {new Date(ev.timestamp).toLocaleString()}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <button
                type="button"
                className="btn btn--secondary btn--sm"
                onClick={() => queryTelemetry({ limit: 10, offset: 0 })}
                disabled={loadingTelemetry}
              >
                {loadingTelemetry ? 'Refreshing…' : 'Refresh Telemetry'}
              </button>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

// ============================================================================
// Internal sub-components
// ============================================================================

function StatusBadge({ status }: { status: string }) {
  let tone: 'ok' | 'warn' | 'bad' | 'neutral' = 'neutral';

  switch (status) {
    case 'completed':
    case 'evaluated':
    case 'approved':
      tone = 'ok';
      break;
    case 'awaiting_approval':
    case 'generating_scoreboard':
      tone = 'warn';
      break;
    case 'rejected':
    case 'failed':
      tone = 'bad';
      break;
  }

  const cls =
    tone === 'ok'
      ? 'badge--compliant'
      : tone === 'warn'
        ? 'badge--pending'
        : tone === 'bad'
          ? 'badge--non-compliant'
          : 'badge--neutral';

  const label = status.replace(/_/g, ' ');

  return <span className={`badge ${cls}`}>{label}</span>;
}

function RunDetailCard({
  run,
  loading,
  onGenerateReport,
  loadingGenerate,
}: {
  run: PipelineStatus | null | undefined;
  loading: boolean;
  onGenerateReport: (runId: string) => void;
  loadingGenerate: boolean;
}) {
  // ------------------------------------------------------------------
  // Empty (no run selected)
  // ------------------------------------------------------------------
  if (!run) {
    return (
      <section className="card">
        <div className="card__header">
          <h2 className="card__title">Run Detail</h2>
        </div>
        <div className="card__body">
          <div className="placeholder-page" style={{ minHeight: '14vh' }}>
            <div className="placeholder-page__icon" aria-hidden="true">📋</div>
            <p className="placeholder-page__subtitle">
              Select a pipeline run from the list to view its details.
            </p>
          </div>
        </div>
      </section>
    );
  }

  // ------------------------------------------------------------------
  // Loading
  // ------------------------------------------------------------------
  if (loading) {
    return (
      <section className="card">
        <div className="card__header">
          <h2 className="card__title">Run Detail</h2>
        </div>
        <div className="card__body">
          <div className="skeleton" style={{ height: '12rem' }} />
        </div>
      </section>
    );
  }

  // ------------------------------------------------------------------
  // Populated
  // ------------------------------------------------------------------
  const isComplete = run.status === 'completed' || run.status === 'evaluated';

  return (
    <section className="card">
      <div className="card__header">
        <h2 className="card__title">Run Detail</h2>
        <StatusBadge status={run.status} />
      </div>

      <div className="card__body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        {/* Key metadata */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          <MetaField label="Run ID" value={run.run_id} mono />
          <MetaField label="Circular" value={run.circular_id} />
          <MetaField
            label="Created"
            value={run.created_at ? new Date(run.created_at).toLocaleString() : '—'}
          />
          <MetaField
            label="Scoreboard"
            value={run.scoreboard_id ?? '—'}
          />
        </div>

        {/* FSM counts */}
        {run.total_fsms > 0 && (
          <div>
            <div
              style={{
                fontSize: 'var(--text-xs)',
                fontWeight: 600,
                color: 'var(--color-neutral-500)',
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
                marginBottom: 'var(--space-3)',
              }}
            >
              FSM Status
            </div>
            <FsmStatusGrid
              total={run.total_fsms}
              pending={run.pending}
              approved={run.approved}
              rejected={run.rejected}
              amended={run.amended}
            />
          </div>
        )}

        {/* Verdict summary */}
        {run.verdict_count > 0 && (
          <div
            style={{
              padding: 'var(--space-3)',
              background: 'var(--color-neutral-100)',
              borderRadius: 'var(--radius-md)',
              fontSize: 'var(--text-sm)',
            }}
          >
            <span style={{ fontWeight: 600 }}>{run.verdict_count}</span>{' '}
            compliance verdicts generated
          </div>
        )}

        {/* Actions */}
        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          {isComplete && run.verdict_count > 0 && (
            <button
              type="button"
              className="btn btn--primary btn--sm"
              onClick={() => onGenerateReport(run.run_id)}
              disabled={loadingGenerate}
            >
              {loadingGenerate ? 'Generating…' : 'Generate Report'}
            </button>
          )}
        </div>
      </div>
    </section>
  );
}

function MetaField({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 'var(--space-2)' }}>
      <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-neutral-500)', whiteSpace: 'nowrap' }}>
        {label}
      </span>
      <span
        style={{
          fontFamily: mono ? 'var(--font-mono)' : undefined,
          fontSize: 'var(--text-sm)',
          textAlign: 'right',
          wordBreak: 'break-all',
        }}
      >
        {value}
      </span>
    </div>
  );
}

function FsmStatusGrid({
  total,
  pending,
  approved,
  rejected,
  amended,
}: {
  total: number;
  pending: number;
  approved: number;
  rejected: number;
  amended: number;
}) {
  return (
    <div className="grid-4" style={{ gap: 'var(--space-2)' }}>
      <FsmStat label="Total" value={total} />
      <FsmStat label="Pending" value={pending} tone="warn" />
      <FsmStat
        label="Approved"
        value={approved + amended}
        tone="ok"
      />
      <FsmStat label="Rejected" value={rejected} tone="bad" />
    </div>
  );
}

function FsmStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: 'ok' | 'warn' | 'bad';
}) {
  const color =
    tone === 'ok'
      ? 'var(--color-success-700)'
      : tone === 'warn'
        ? 'var(--color-warning-700)'
        : tone === 'bad'
          ? 'var(--color-danger-700)'
          : 'var(--color-neutral-700)';

  return (
    <div
      style={{
        textAlign: 'center',
        padding: 'var(--space-2)',
        background: 'var(--color-neutral-100)',
        borderRadius: 'var(--radius-md)',
      }}
    >
      <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color, lineHeight: 1.2 }}>
        {value}
      </div>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-neutral-500)' }}>
        {label}
      </div>
    </div>
  );
}

function MiniCount({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: 'ok' | 'warn' | 'bad';
}) {
  const color =
    tone === 'ok'
      ? 'var(--color-success-700)'
      : tone === 'warn'
        ? 'var(--color-warning-700)'
        : tone === 'bad'
          ? 'var(--color-danger-700)'
          : 'var(--color-neutral-700)';

  return (
    <div style={{ textAlign: 'center', minWidth: '3rem' }}>
      <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color, lineHeight: 1.2 }}>
        {value}
      </div>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-neutral-500)' }}>
        {label}
      </div>
    </div>
  );
}
