/**
 * Report page — compliance audit report viewer.
 *
 * Route: `/report/:reportId?`
 *
 * Two modes:
 *  1. `reportId` present — fetch and display the report via AuditReport.
 *  2. No `reportId` — show a report selection screen with:
 *       a. Manual report ID lookup
 *       b. Completed pipeline runs eligible for report generation
 *
 * All data flows through the Zustand store and the AuditReport component.
 * No mock data. Every section handles loading, empty, and error states.
 */

import { useState, type FormEvent } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import useComplianceStore from '../store/useComplianceStore';
import AuditReport from '../components/AuditReport';
import FSMViewer from '../components/FSMViewer';
import type { HybridFSM } from '../api/client';

export default function ReportPage() {
  const { reportId } = useParams<{ reportId?: string }>();
  const navigate = useNavigate();

  // ------------------------------------------------------------------
  // Store
  // ------------------------------------------------------------------
  const currentResult = useComplianceStore((s) => s.currentResult);
  const currentReport = useComplianceStore((s) => s.currentReport);
  const runs = useComplianceStore((s) => s.runs);

  // ------------------------------------------------------------------
  // Mode 1: reportId is present → delegate to AuditReport
  // ------------------------------------------------------------------
  if (reportId) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-8)' }}>
        <AuditReport reportId={reportId} />

        {/* If we also have verdicts with FSM refs, allow drilling into them */}
        {currentResult?.verdicts && currentResult.verdicts.length > 0 && (
          <VerdictsSection
            verdicts={currentResult.verdicts}
            report={currentReport}
          />
        )}
      </div>
    );
  }

  // ------------------------------------------------------------------
  // Mode 2: No reportId — show selection / generation screen
  // ------------------------------------------------------------------
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-8)' }}>
      {/* Manual report ID lookup */}
      <ReportLookupForm onLookup={(id) => navigate(`/report/${id}`)} />

      {/* Completed runs eligible for generation */}
      <CompletedRunsSection
        runs={runs}
        onGenerate={(id) => navigate(`/report/${id}`)}
      />
    </div>
  );
}

// ============================================================================
// Mode 2 sub-sections
// ============================================================================

function ReportLookupForm({
  onLookup,
}: {
  onLookup: (reportId: string) => void;
}) {
  const [value, setValue] = useState('');

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = value.trim();
    if (trimmed) onLookup(trimmed);
  }

  return (
    <section className="card">
      <div className="card__header">
        <h2 className="card__title">Find Report</h2>
      </div>
      <div className="card__body">
        <p style={{ color: 'var(--color-neutral-500)', fontSize: 'var(--text-sm)', marginBottom: 'var(--space-4)' }}>
          Enter a report ID to view an existing compliance audit report.
        </p>

        <form
          onSubmit={handleSubmit}
          style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'flex-end' }}
        >
          <label style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)', flex: 1 }}>
            <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>
              Report ID
            </span>
            <input
              type="text"
              className="field-input"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="RPT-XXXXXXXXXXXX"
            />
          </label>
          <button
            type="submit"
            className="btn btn--primary"
            disabled={!value.trim()}
          >
            View Report
          </button>
        </form>
      </div>
    </section>
  );
}

function CompletedRunsSection({
  runs,
  onGenerate,
}: {
  runs: ReturnType<typeof useComplianceStore.getState>['runs'];
  onGenerate: (reportId: string) => void;
}) {
  const generateReport = useComplianceStore((s) => s.generateReport);
  const loadingGenerate = useComplianceStore((s) => s.loading.generateReport);
  const errorGenerate = useComplianceStore((s) => s.errors.generateReport);

  const completedRuns = runs.filter(
    (r) => r.status === 'completed' || r.status === 'evaluated' || r.status === 'generating_scoreboard',
  );

  async function handleGenerate(runId: string) {
    const id = await generateReport(runId);
    if (id) onGenerate(id);
  }

  return (
    <section className="card">
      <div className="card__header">
        <h2 className="card__title">Generate from Pipeline Run</h2>
        {completedRuns.length > 0 && (
          <span className="badge badge--neutral">{completedRuns.length} eligible</span>
        )}
      </div>

      <div className="card__body">
        {/* Empty */}
        {completedRuns.length === 0 && (
          <div className="placeholder-page" style={{ minHeight: '10vh' }}>
            <p className="placeholder-page__subtitle">
              No completed pipeline runs available. Trigger a pipeline, approve the
              FSMs at the HITL gate, and return here to generate a report.
            </p>
          </div>
        )}

        {/* Error */}
        {errorGenerate && (
          <div className="inline-error" style={{ marginBottom: 'var(--space-4)' }}>
            {errorGenerate}
          </div>
        )}

        {/* List */}
        {completedRuns.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            {completedRuns.map((run) => (
              <div
                key={run.run_id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: 'var(--space-3) var(--space-4)',
                  background: 'var(--color-neutral-100)',
                  border: '1px solid var(--color-neutral-300)',
                  borderRadius: 'var(--radius-md)',
                  flexWrap: 'wrap',
                  gap: 'var(--space-3)',
                }}
              >
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>
                    {run.circular_id}
                  </div>
                  <div
                    style={{
                      fontSize: 'var(--text-xs)',
                      color: 'var(--color-neutral-500)',
                      fontFamily: 'var(--font-mono)',
                      marginTop: 'var(--space-1)',
                    }}
                  >
                    {run.run_id}
                  </div>
                  <div
                    style={{
                      fontSize: 'var(--text-xs)',
                      color: 'var(--color-neutral-500)',
                      marginTop: 'var(--space-1)',
                    }}
                  >
                    {run.verdict_count} verdicts
                    {run.scoreboard_id && (
                      <>
                        {' · '}
                        Scoreboard: {run.scoreboard_id}
                      </>
                    )}
                  </div>
                </div>

                <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
                  <span className={`badge ${run.status === 'completed' ? 'badge--compliant' : 'badge--pending'}`}>
                    {run.status.replace(/_/g, ' ')}
                  </span>
                  <button
                    type="button"
                    className="btn btn--primary btn--sm"
                    onClick={() => handleGenerate(run.run_id)}
                    disabled={loadingGenerate}
                  >
                    {loadingGenerate ? 'Generating…' : 'Generate Report'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

// ============================================================================
// Verdicts drill-down (shown below AuditReport when report is loaded)
// ============================================================================

function VerdictsSection({
  verdicts,
  report,
}: {
  verdicts: NonNullable<ReturnType<typeof useComplianceStore.getState>['currentResult']>['verdicts'];
  report: ReturnType<typeof useComplianceStore.getState>['currentReport'];
}) {
  const [selectedFsm, setSelectedFsm] = useState<HybridFSM | null>(null);

  // Try to resolve FSM detail from the scoreboard when a verdict row is clicked
  function handleViewFsm(fsmRef: string) {
    const scoreboard = report?.scoreboard;
    if (!scoreboard) return;

    // Search broker summaries for an obligation_result matching the FSM ref
    for (const broker of scoreboard.broker_summaries) {
      const detail = broker.obligation_details.find((d) => d.fsm_ref === fsmRef);
      if (detail) {
        // We don't have the full HybridFSM in the report, but we can construct
        // a minimal representation from the broker score for display.
        // For now, close the panel — full FSM drill-down requires the
        // pipeline state to still be in memory.
        setSelectedFsm(null);
        return;
      }
    }
    setSelectedFsm(null);
  }

  // Build a unique set of broker + obligation combinations with evidence summaries
  const uniqueVerdicts = verdicts.filter(
    (v, i, arr) =>
      arr.findIndex(
        (x) => x.broker_id === v.broker_id && x.obligation_ref === v.obligation_ref,
      ) === i,
  );

  return (
    <>
      <section className="card">
        <div className="card__header">
          <h2 className="card__title">Compliance Verdicts</h2>
          <span className="badge badge--neutral">{verdicts.length} verdicts</span>
        </div>

        <div className="card__body">
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Verdict ID</th>
                  <th>Broker</th>
                  <th>Obligation</th>
                  <th>FSM</th>
                  <th>Status</th>
                  <th>State</th>
                  <th>Evaluated</th>
                </tr>
              </thead>
              <tbody>
                {uniqueVerdicts.map((v) => {
                  const statusClass =
                    v.status === 'compliant'
                      ? 'badge--compliant'
                      : v.status === 'non_compliant'
                        ? 'badge--non-compliant'
                        : 'badge--pending';
                  return (
                    <tr key={v.verdict_id}>
                      <td>
                        <code style={{ fontSize: 'var(--text-xs)' }}>{v.verdict_id}</code>
                      </td>
                      <td style={{ fontWeight: 500 }}>{v.broker_id}</td>
                      <td>{v.obligation_ref}</td>
                      <td>
                        <button
                          type="button"
                          className="btn btn--secondary btn--sm"
                          onClick={() => handleViewFsm(v.fsm_ref)}
                          style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}
                        >
                          {v.fsm_ref}
                        </button>
                      </td>
                      <td>
                        <span className={`badge ${statusClass}`}>{v.status}</span>
                      </td>
                      <td>{v.current_state}</td>
                      <td style={{ fontSize: 'var(--text-xs)', whiteSpace: 'nowrap' }}>
                        {new Date(v.evaluated_at).toLocaleString()}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Evidence summary per verdict */}
          {uniqueVerdicts.length > 0 && (
            <details style={{ marginTop: 'var(--space-4)' }}>
              <summary
                style={{
                  cursor: 'pointer',
                  fontSize: 'var(--text-sm)',
                  fontWeight: 500,
                  color: 'var(--color-primary-700)',
                }}
              >
                + Evidence Summaries
              </summary>
              <div
                style={{
                  marginTop: 'var(--space-3)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 'var(--space-3)',
                }}
              >
                {uniqueVerdicts.map((v) => (
                  <div
                    key={v.verdict_id}
                    style={{
                      padding: 'var(--space-3)',
                      background: 'var(--color-neutral-100)',
                      borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--color-neutral-200)',
                    }}
                  >
                    <div
                      style={{
                        fontSize: 'var(--text-xs)',
                        fontWeight: 600,
                        color: 'var(--color-neutral-500)',
                        marginBottom: 'var(--space-2)',
                      }}
                    >
                      {v.verdict_id} — {v.broker_id} / {v.obligation_ref}
                    </div>
                    <pre
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: 'var(--text-xs)',
                        lineHeight: 1.5,
                        margin: 0,
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word',
                        maxHeight: '16rem',
                        overflowY: 'auto',
                      }}
                    >
                      {JSON.stringify(v.evidence, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      </section>

      {/* FSM drill-down panel */}
      {selectedFsm && (
        <FSMViewer fsm={selectedFsm} />
      )}
    </>
  );
}
