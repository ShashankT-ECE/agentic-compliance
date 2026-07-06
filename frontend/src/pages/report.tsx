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

export default function ReportPage() {
  const { reportId } = useParams<{ reportId?: string }>();
  const navigate = useNavigate();

  // ------------------------------------------------------------------
  // Store
  // ------------------------------------------------------------------
  const runs = useComplianceStore((s) => s.runs);

  // ------------------------------------------------------------------
  // Mode 1: reportId is present → delegate to AuditReport
  // ------------------------------------------------------------------
  if (reportId) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-8)' }}>
        <AuditReport reportId={reportId} />
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
              compliance obligations at the HITL gate, and return here to generate a report.
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

