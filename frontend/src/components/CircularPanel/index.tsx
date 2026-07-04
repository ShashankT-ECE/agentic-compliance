/**
 * CircularPanel — pipeline trigger form and circular metadata display.
 *
 * Provides a form to kick off a new compliance pipeline run
 * and displays information about the currently selected run.
 *
 * States handled:
 *  - idle:      form ready, no active run
 *  - loading:   trigger request in-flight
 *  - error:     trigger failed (shows inline error + retry)
 *  - populated: run triggered, shows run_id + status
 */

import { useState, type FormEvent } from 'react';
import useComplianceStore from '../../store/useComplianceStore';
import type { PipelineStatus } from '../../api/client';

export interface CircularPanelProps {
  /** Pre-selected run to display. If omitted, the store's `currentRun` is used. */
  run?: PipelineStatus | null;
  /** Callback fired after a successful pipeline trigger. */
  onTriggered?: (runId: string) => void;
}

export default function CircularPanel({
  run: runProp,
  onTriggered,
}: CircularPanelProps) {
  // ------------------------------------------------------------------
  // Store
  // ------------------------------------------------------------------
  const storeRun = useComplianceStore((s) => s.currentRun);
  const triggerPipeline = useComplianceStore((s) => s.triggerPipeline);
  const loading = useComplianceStore((s) => s.loading.triggerPipeline);
  const error = useComplianceStore((s) => s.errors.triggerPipeline);
  const clearError = useComplianceStore((s) => s.clearError);

  const run = runProp ?? storeRun;

  // ------------------------------------------------------------------
  // Form state
  // ------------------------------------------------------------------
  const [circularPath, setCircularPath] = useState('');
  const [circularId, setCircularId] = useState('');

  // ------------------------------------------------------------------
  // Handlers
  // ------------------------------------------------------------------
  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (error) clearError('triggerPipeline');

    const runId = await triggerPipeline(circularPath.trim(), circularId.trim());
    if (runId) {
      setCircularPath('');
      setCircularId('');
      onTriggered?.(runId);
    }
  }

  // ------------------------------------------------------------------
  // Render: populated
  // ------------------------------------------------------------------
  if (run) {
    return (
      <section className="card">
        <div className="card__header">
          <h2 className="card__title">Circular</h2>
          <span className="badge badge--neutral">{run.status}</span>
        </div>

        <div className="card__body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <Field label="Run ID" value={run.run_id} mono />
          <Field label="Circular ID" value={run.circular_id} />
          <Field label="Created" value={run.created_at ? new Date(run.created_at).toLocaleString() : '—'} />
          <Field label="Scoreboard" value={run.scoreboard_id ?? '—'} />

          {run.total_fsms > 0 && (
            <div style={{ display: 'flex', gap: 'var(--space-3)', marginTop: 'var(--space-2)' }}>
              <MiniStat label="Total FSMs" value={run.total_fsms} />
              <MiniStat label="Pending" value={run.pending} tone="warn" />
              <MiniStat label="Approved" value={run.approved} tone="ok" />
              <MiniStat label="Rejected" value={run.rejected} tone="bad" />
            </div>
          )}

          {/* New pipeline button when viewing a completed/active run */}
          <button
            type="button"
            className="btn btn--secondary btn--sm"
            style={{ alignSelf: 'flex-start', marginTop: 'var(--space-2)' }}
            onClick={() => useComplianceStore.getState().reset()}
          >
            + New Pipeline
          </button>
        </div>
      </section>
    );
  }

  // ------------------------------------------------------------------
  // Render: idle / loading / error
  // ------------------------------------------------------------------
  return (
    <section className="card">
      <div className="card__header">
        <h2 className="card__title">New Pipeline Run</h2>
      </div>

      <div className="card__body">
        <p style={{ color: 'var(--color-neutral-500)', fontSize: 'var(--text-sm)', marginBottom: 'var(--space-4)' }}>
          Trigger a compliance pipeline by providing a SEBI circular PDF path
          and its reference identifier.
        </p>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          {/* Circular path */}
          <label style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
            <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>
              Circular PDF Path
            </span>
            <input
              type="text"
              className="field-input"
              value={circularPath}
              onChange={(e) => setCircularPath(e.target.value)}
              placeholder="/data/circulars/SEBI_CIRC_2025_57.pdf"
              required
              disabled={loading}
            />
          </label>

          {/* Circular ID */}
          <label style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
            <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>
              Circular Reference
            </span>
            <input
              type="text"
              className="field-input"
              value={circularId}
              onChange={(e) => setCircularId(e.target.value)}
              placeholder="SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57"
              required
              disabled={loading}
            />
          </label>

          {/* Error */}
          {error && (
            <div className="inline-error">
              <span aria-hidden="true">⚠</span> {error}
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            className="btn btn--primary"
            disabled={loading || !circularPath.trim() || !circularId.trim()}
            style={{ alignSelf: 'flex-start' }}
          >
            {loading ? 'Starting pipeline…' : 'Trigger Pipeline'}
          </button>
        </form>
      </div>
    </section>
  );
}

// ============================================================================
// Internal sub-components
// ============================================================================

function Field({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
      <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-neutral-500)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
        {label}
      </span>
      <span
        style={{
          fontFamily: mono ? 'var(--font-mono)' : undefined,
          fontSize: mono ? 'var(--text-sm)' : 'var(--text-base)',
          wordBreak: 'break-all',
        }}
      >
        {value}
      </span>
    </div>
  );
}

function MiniStat({
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
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        padding: 'var(--space-2) var(--space-3)',
        backgroundColor: 'var(--color-neutral-100)',
        borderRadius: 'var(--radius-md)',
        minWidth: '4.5rem',
      }}
    >
      <span style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color, lineHeight: 1.2 }}>
        {value}
      </span>
      <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-neutral-500)' }}>
        {label}
      </span>
    </div>
  );
}
