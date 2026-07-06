/**
 * Dashboard page — pipeline overview, review queue, and telemetry.
 *
 * Route: `/`
 *
 * Layout:
 *  1. Pipeline trigger / current run panel
 *  2. Pipeline runs list + detail (side-by-side)
 *  3. Review queue summary
 *  4. Telemetry quick stats
 */

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import useComplianceStore from '../store/useComplianceStore';
import CircularPanel from '../components/CircularPanel';
import type { PipelineStatus } from '../api/client';

export default function DashboardPage() {
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
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  useEffect(() => {
    fetchHitlList();
    queryTelemetry({ limit: 5, offset: 0 });
  }, [fetchHitlList, queryTelemetry]);

  useEffect(() => {
    if (selectedRunId) fetchStatus(selectedRunId);
  }, [selectedRunId, fetchStatus]);

  function handleTriggered(runId: string) {
    setSelectedRunId(runId);
    fetchHitlList();
  }

  async function handleGenerateReport(runId: string) {
    const id = await generateReport(runId);
    if (id) navigate(`/report/${id}`);
  }

  function handleClearAll() {
    reset();
    setSelectedRunId(null);
  }

  const selectedRun = runs.find((r) => r.run_id === selectedRunId) ?? currentRun;
  const pendingHitlCount = hitlRuns.reduce((sum, r) => sum + (r.pending ?? 0), 0);
  const latestEvents = telemetryEvents.slice(0, 3);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      {/* ================================================================
          Section 1 — Pipeline trigger / current run
          ================================================================ */}
      <CircularPanel run={selectedRun} onTriggered={handleTriggered} />

      {/* ================================================================
          Section 2 — Runs List + Detail
          ================================================================ */}
      <div className="grid-2" style={{ alignItems: 'start' }}>
        {/* Runs list */}
        <section className="card">
          <div className="card__header">
            <h2 className="card__title">
              <span className="card__title-icon">📋</span>
              Pipeline Runs
            </h2>
            {runs.length > 0 && (
              <span className="badge badge--brand">{runs.length}</span>
            )}
          </div>
          <div className="card__body">
            {runs.length === 0 && (
              <div className="placeholder-page" style={{ minHeight: '10vh', padding: 'var(--space-6)' }}>
                <p className="placeholder-page__subtitle">
                  No pipeline runs yet. Trigger one above to get started.
                </p>
              </div>
            )}

            {runs.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                {runs.map((run) => (
                  <button
                    key={run.run_id}
                    type="button"
                    onClick={() => setSelectedRunId(run.run_id)}
                    className={
                      selectedRunId === run.run_id
                        ? 'run-card run-card--selected'
                        : 'run-card'
                    }
                  >
                    <div style={{ minWidth: 0 }}>
                      <div className="run-card__id">
                        {run.circular_id}
                      </div>
                      <div className="run-card__circular">
                        {run.run_id}
                      </div>
                    </div>
                    <StatusBadge status={run.status} />
                  </button>
                ))}
              </div>
            )}

            {runs.length > 0 && (
              <button
                type="button"
                className="btn btn--secondary btn--sm"
                style={{ marginTop: 'var(--space-3)' }}
                onClick={handleClearAll}
              >
                Clear All
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
          Section 3 — Review Queue
          ================================================================ */}
      <section className="card">
        <div className="card__header">
          <h2 className="card__title">
            <span className="card__title-icon">👁️</span>
            Pending Reviews
          </h2>
          {pendingHitlCount > 0 && (
            <span className="badge badge--pending">{pendingHitlCount} to review</span>
          )}
        </div>
        <div className="card__body">
          {loadingHitl && !hitlRuns.length && (
            <div className="skeleton" style={{ height: '3rem' }} />
          )}

          {!loadingHitl && hitlRuns.length === 0 && (
            <div className="placeholder-page" style={{ minHeight: '6vh', padding: 'var(--space-4)' }}>
              <p className="placeholder-page__subtitle">
                No compliance obligations awaiting review. Trigger a pipeline to populate the queue.
              </p>
            </div>
          )}

          {hitlRuns.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
              {hitlRuns.map((run) => (
                <div
                  key={run.run_id}
                  className="review-banner review-banner--pending"
                  style={{ justifyContent: 'space-between', flexWrap: 'wrap' }}
                >
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>
                      {run.circular_ref}
                    </div>
                    <div style={{ fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)', opacity: 0.7, marginTop: 'var(--space-1)' }}>
                      {run.run_id}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 'var(--space-5)', alignItems: 'center' }}>
                    <MiniStat label="Total" value={run.total_fsms} />
                    <MiniStat label="Pending" value={run.pending} tone="warn" />
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
          Section 4 — Telemetry
          ================================================================ */}
      <section className="card">
        <div className="card__header">
          <h2 className="card__title">
            <span className="card__title-icon">📡</span>
            Broker Telemetry
          </h2>
          {telemetryTotal > 0 && (
            <span className="badge badge--neutral">{telemetryTotal.toLocaleString()} events</span>
          )}
        </div>
        <div className="card__body">
          {loadingTelemetry && telemetryTotal === 0 && (
            <div className="skeleton" style={{ height: '3rem' }} />
          )}

          {!loadingTelemetry && telemetryTotal === 0 && (
            <div className="placeholder-page" style={{ minHeight: '6vh', padding: 'var(--space-4)' }}>
              <p className="placeholder-page__subtitle">
                No telemetry events ingested yet. Use the Telemetry Table to ingest broker events for evaluation.
              </p>
            </div>
          )}

          {telemetryTotal > 0 && (
            <div>
              {latestEvents.length > 0 && (
                <div style={{ marginBottom: 'var(--space-3)' }}>
                  <div style={{ fontSize: 'var(--text-2xs)', fontWeight: 600, color: 'var(--color-slate-500)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 'var(--space-2)' }}>
                    Recent Events
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                    {latestEvents.map((ev) => (
                      <div
                        key={ev.event_id}
                        style={{
                          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                          padding: 'var(--space-2) var(--space-3)',
                          background: 'var(--color-slate-50)',
                          borderRadius: 'var(--radius-md)',
                          border: '1px solid var(--color-slate-200)',
                          fontSize: 'var(--text-sm)',
                        }}
                      >
                        <div style={{ display: 'flex', gap: 'var(--space-4)', alignItems: 'center', minWidth: 0 }}>
                          <span style={{ fontWeight: 500 }}>{ev.broker_id}</span>
                          <code style={{ fontSize: 'var(--text-xs)', color: 'var(--color-slate-500)' }}>
                            {ev.event_type}
                          </code>
                        </div>
                        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-slate-400)', whiteSpace: 'nowrap' }}>
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
// Sub-components
// ============================================================================

function StatusBadge({ status }: { status: string }) {
  let cls: string;
  switch (status) {
    case 'completed': case 'evaluated': case 'approved':
      cls = 'badge--compliant'; break;
    case 'awaiting_approval': case 'generating_scoreboard':
      cls = 'badge--pending'; break;
    case 'rejected': case 'failed':
      cls = 'badge--non-compliant'; break;
    default:
      cls = 'badge--neutral';
  }
  const label = status.replace(/_/g, ' ');
  return <span className={`badge ${cls}`}>{label}</span>;
}

function RunDetailCard({
  run, loading, onGenerateReport, loadingGenerate,
}: {
  run: PipelineStatus | null | undefined;
  loading: boolean;
  onGenerateReport: (runId: string) => void;
  loadingGenerate: boolean;
}) {
  if (!run) {
    return (
      <section className="card">
        <div className="card__header">
          <h2 className="card__title">Run Detail</h2>
        </div>
        <div className="card__body">
          <div className="placeholder-page" style={{ minHeight: '10vh', padding: 'var(--space-4)' }}>
            <p className="placeholder-page__subtitle">
              Select a pipeline run from the list to view its details.
            </p>
          </div>
        </div>
      </section>
    );
  }

  if (loading) {
    return (
      <section className="card">
        <div className="card__header">
          <h2 className="card__title">Run Detail</h2>
        </div>
        <div className="card__body">
          <div className="skeleton" style={{ height: '10rem' }} />
        </div>
      </section>
    );
  }

  const isComplete = run.status === 'completed' || run.status === 'evaluated';

  return (
    <section className="card">
      <div className="card__header">
        <h2 className="card__title">Run Detail</h2>
        <StatusBadge status={run.status} />
      </div>
      <div className="card__body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
          <div className="meta-row">
            <span className="meta-row__label">Run ID</span>
            <span className="meta-row__value meta-row__value--mono">{run.run_id}</span>
          </div>
          <div className="meta-row">
            <span className="meta-row__label">Circular</span>
            <span className="meta-row__value">{run.circular_id}</span>
          </div>
          <div className="meta-row">
            <span className="meta-row__label">Created</span>
            <span className="meta-row__value">{run.created_at ? new Date(run.created_at).toLocaleString() : '—'}</span>
          </div>
          <div className="meta-row">
            <span className="meta-row__label">Scoreboard</span>
            <span className="meta-row__value meta-row__value--mono">{run.scoreboard_id ?? '—'}</span>
          </div>
        </div>

        {run.total_fsms > 0 && (
          <div>
            <div style={{ fontSize: 'var(--text-2xs)', fontWeight: 600, color: 'var(--color-slate-500)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 'var(--space-3)' }}>
              Obligations
            </div>
            <div className="grid-4" style={{ gap: 'var(--space-2)' }}>
              <StatMini label="Total" value={run.total_fsms} variant="brand" />
              <StatMini label="Pending" value={run.pending} variant="warn" />
              <StatMini label="Resolved" value={(run.approved ?? 0) + (run.amended ?? 0)} variant="ok" />
              <StatMini label="Rejected" value={run.rejected} variant="bad" />
            </div>
          </div>
        )}

        {run.verdict_count > 0 && (
          <div style={{ padding: 'var(--space-3)', background: 'var(--color-slate-50)', borderRadius: 'var(--radius-md)', fontSize: 'var(--text-sm)' }}>
            <span style={{ fontWeight: 600 }}>{run.verdict_count}</span> compliance verdicts generated
          </div>
        )}

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

function StatMini({
  label, value, variant,
}: {
  label: string; value: number; variant: 'ok' | 'warn' | 'bad' | 'brand';
}) {
  return (
    <div className={`stat-card stat-card--${variant}`} style={{ padding: 'var(--space-3)' }}>
      <div className="stat-card__value" style={{ fontSize: 'var(--text-xl)' }}>{value}</div>
      <div className="stat-card__label">{label}</div>
    </div>
  );
}

function MiniStat({
  label, value, tone,
}: {
  label: string; value: number; tone?: 'ok' | 'warn' | 'bad';
}) {
  const color = tone === 'ok' ? 'var(--color-success-700)'
    : tone === 'warn' ? 'var(--color-warning-700)'
    : tone === 'bad' ? 'var(--color-danger-700)'
    : 'var(--color-slate-700)';
  return (
    <div style={{ textAlign: 'center', minWidth: '3rem' }}>
      <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color, lineHeight: 1.2 }}>{value}</div>
      <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--color-slate-500)', textTransform: 'uppercase', letterSpacing: '0.03em' }}>{label}</div>
    </div>
  );
}
