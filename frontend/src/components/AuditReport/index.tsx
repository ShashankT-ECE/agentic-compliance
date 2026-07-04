/**
 * AuditReport — compliance scoreboard, verdict details, and hash-chain status.
 *
 * Displays a full compliance audit report: summary stats, per-broker
 * compliance cards, a verdicts table, and hash-chain integrity status.
 *
 * Two modes:
 *  1. `reportId` prop → fetches the report via the Zustand store
 *  2. `report` prop   → renders directly from provided data
 *
 * States handled:
 *  - empty:     no report data, prompts to generate/fetch one
 *  - loading:   API request in-flight
 *  - error:     fetch failed
 *  - populated: report rendered
 */

import { useEffect } from 'react';
import useComplianceStore from '../../store/useComplianceStore';
import type {
  ReportDetail,
  BrokerScore,
  ComplianceVerdict,
  HashChain,
  HashLink,
} from '../../api/client';

// ============================================================================
// Props
// ============================================================================

export interface AuditReportProps {
  /** If provided, fetch this report from the API on mount. */
  reportId?: string;
  /** Pre-fetched report data (avoids store fetch). */
  report?: ReportDetail | null;
  /** Show a "Generate Report" button for a completed run. */
  runIdForGenerate?: string;
  /** Callback when a report is successfully generated. */
  onGenerated?: (reportId: string) => void;
  /** Callback when the user requests to view an FSM. */
  onViewFsm?: (fsmRef: string) => void;
}

// ============================================================================
// Component
// ============================================================================

export default function AuditReport({
  reportId,
  report: reportProp,
  runIdForGenerate,
  onGenerated,
}: AuditReportProps) {
  // ------------------------------------------------------------------
  // Store
  // ------------------------------------------------------------------
  const storeReport = useComplianceStore((s) => s.currentReport);
  const fetchReport = useComplianceStore((s) => s.fetchReport);
  const generateReport = useComplianceStore((s) => s.generateReport);
  const loadingFetch = useComplianceStore((s) => s.loading.fetchReport);
  const loadingGenerate = useComplianceStore((s) => s.loading.generateReport);
  const errorFetch = useComplianceStore((s) => s.errors.fetchReport);
  const errorGenerate = useComplianceStore((s) => s.errors.generateReport);

  const loading = loadingFetch || loadingGenerate;
  const error = errorFetch ?? errorGenerate;

  const report = reportProp ?? storeReport;

  // Fetch on mount if reportId is given
  useEffect(() => {
    if (reportId) fetchReport(reportId);
  }, [reportId, fetchReport]);

  // ------------------------------------------------------------------
  // Generate handler
  // ------------------------------------------------------------------
  async function handleGenerate() {
    if (!runIdForGenerate) return;
    const id = await generateReport(runIdForGenerate);
    if (id) onGenerated?.(id);
  }

  // ------------------------------------------------------------------
  // Empty
  // ------------------------------------------------------------------
  if (!report && !loading && !error && !runIdForGenerate) {
    return (
      <section className="card">
        <div className="card__header">
          <h2 className="card__title">Audit Report</h2>
        </div>
        <div className="card__body">
          <div className="placeholder-page" style={{ minHeight: '20vh' }}>
            <div className="placeholder-page__icon" aria-hidden="true">📋</div>
            <p className="placeholder-page__subtitle">
              Complete a pipeline run and generate a report to view audit findings here.
            </p>
          </div>
        </div>
      </section>
    );
  }

  // ------------------------------------------------------------------
  // Generate prompt (completed run, no report yet)
  // ------------------------------------------------------------------
  if (!report && runIdForGenerate && !loading) {
    return (
      <section className="card">
        <div className="card__header">
          <h2 className="card__title">Audit Report</h2>
        </div>
        <div className="card__body">
          <div className="placeholder-page" style={{ minHeight: '16vh' }}>
            <div className="placeholder-page__icon" aria-hidden="true">📋</div>
            <p className="placeholder-page__subtitle" style={{ marginBottom: 'var(--space-4)' }}>
              The pipeline run is complete. Generate an immutable audit report.
            </p>
            <button type="button" className="btn btn--primary" onClick={handleGenerate}>
              Generate Report
            </button>
            {errorGenerate && (
              <p style={{ color: 'var(--color-danger-500)', marginTop: 'var(--space-3)', fontSize: 'var(--text-sm)' }}>
                {errorGenerate}
              </p>
            )}
          </div>
        </div>
      </section>
    );
  }

  // ------------------------------------------------------------------
  // Loading
  // ------------------------------------------------------------------
  if (loading && !report) {
    return (
      <section className="card">
        <div className="card__header">
          <h2 className="card__title">Audit Report</h2>
        </div>
        <div className="card__body">
          <div className="skeleton" style={{ height: '12rem' }} />
        </div>
      </section>
    );
  }

  // ------------------------------------------------------------------
  // Error (no data)
  // ------------------------------------------------------------------
  if (error && !report) {
    return (
      <section className="card">
        <div className="card__header">
          <h2 className="card__title">Audit Report</h2>
        </div>
        <div className="card__body">
          <div className="placeholder-page" style={{ minHeight: '16vh' }}>
            <div className="placeholder-page__icon" aria-hidden="true">⚠️</div>
            <p className="placeholder-page__subtitle" style={{ color: 'var(--color-danger-500)' }}>
              {error}
            </p>
            {reportId && (
              <button
                type="button"
                className="btn btn--secondary"
                style={{ marginTop: 'var(--space-4)' }}
                onClick={() => fetchReport(reportId)}
              >
                Retry
              </button>
            )}
          </div>
        </div>
      </section>
    );
  }

  if (!report) return null;

  // ------------------------------------------------------------------
  // Populated
  // ------------------------------------------------------------------
  return (
    <section className="card">
      <div className="card__header">
        <h2 className="card__title">Audit Report</h2>
        <span className="badge badge--neutral">{report.report_id}</span>
      </div>

      <div className="card__body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
        {/* Report metadata */}
        <ReportMeta report={report} />

        {/* Summary stats */}
        <SummaryCards summary={report.summary} />

        {/* Broker scorecards */}
        {report.scoreboard && report.scoreboard.broker_summaries.length > 0 && (
          <BrokerCards brokers={report.scoreboard.broker_summaries} />
        )}

        {/* Verdicts table */}
        {report.verdicts.length > 0 && (
          <VerdictsTable verdicts={report.verdicts} />
        )}

        {/* Hash chain */}
        {report.scoreboard?.hash_chain && (
          <HashChainStatus chain={report.scoreboard.hash_chain} />
        )}
      </div>
    </section>
  );
}

// ============================================================================
// Sub-components
// ============================================================================

function ReportMeta({ report }: { report: ReportDetail }) {
  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 'var(--space-6)',
        fontSize: 'var(--text-sm)',
        color: 'var(--color-neutral-600)',
      }}
    >
      <div><strong>Circular</strong> {report.circular_id}</div>
      <div><strong>Run</strong> <code>{report.run_id}</code></div>
      <div><strong>Generated</strong> {new Date(report.generated_at).toLocaleString()}</div>
    </div>
  );
}

function SummaryCards({ summary }: { summary: ReportDetail['summary'] }) {
  return (
    <div className="grid-4">
      <StatCard label="Total Verdicts" value={summary.total_verdicts} />
      <StatCard label="Compliant" value={summary.compliant} tone="ok" />
      <StatCard label="Non-Compliant" value={summary.non_compliant} tone="bad" />
      <StatCard
        label="Compliance Rate"
        value={`${summary.compliance_pct}%`}
        tone={summary.compliance_pct >= 80 ? 'ok' : summary.compliance_pct >= 50 ? 'warn' : 'bad'}
      />
    </div>
  );
}

function StatCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | string;
  tone?: 'ok' | 'warn' | 'bad';
}) {
  const bg =
    tone === 'ok'
      ? 'var(--color-success-100)'
      : tone === 'warn'
        ? 'var(--color-warning-100)'
        : tone === 'bad'
          ? 'var(--color-danger-100)'
          : 'var(--color-neutral-100)';

  const fg =
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
        background: bg,
        borderRadius: 'var(--radius-lg)',
        padding: 'var(--space-5)',
        textAlign: 'center',
      }}
    >
      <div style={{ fontSize: 'var(--text-3xl)', fontWeight: 700, color: fg, lineHeight: 1.2 }}>
        {value}
      </div>
      <div style={{ fontSize: 'var(--text-xs)', fontWeight: 500, color: 'var(--color-neutral-500)', marginTop: 'var(--space-1)' }}>
        {label}
      </div>
    </div>
  );
}

function BrokerCards({ brokers }: { brokers: BrokerScore[] }) {
  return (
    <div>
      <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, marginBottom: 'var(--space-3)' }}>
        Broker Breakdown
      </h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        {brokers.map((b) => (
          <div
            key={b.broker_id}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: 'var(--space-4)',
              background: 'var(--color-neutral-100)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--color-neutral-300)',
              flexWrap: 'wrap',
              gap: 'var(--space-3)',
            }}
          >
            <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>{b.broker_id}</div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-neutral-500)' }}>
                {b.total_obligations} obligations
              </div>
            </div>

            <div style={{ display: 'flex', gap: 'var(--space-4)', alignItems: 'center' }}>
              <MiniCount label="Compliant" value={b.compliant} tone="ok" />
              <MiniCount label="Non-Compliant" value={b.non_compliant} tone="bad" />
              <MiniCount label="Pending" value={b.pending} tone="warn" />
            </div>

            {/* Compliance bar */}
            <div style={{ width: '8rem' }}>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-neutral-500)', marginBottom: 'var(--space-1)' }}>
                {(b.compliance_rate * 100).toFixed(0)}%
              </div>
              <div
                style={{
                  height: 6,
                  borderRadius: 3,
                  background: 'var(--color-neutral-300)',
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    width: `${Math.round(b.compliance_rate * 100)}%`,
                    height: '100%',
                    borderRadius: 3,
                    background:
                      b.compliance_rate >= 0.8
                        ? 'var(--color-success-500)'
                        : b.compliance_rate >= 0.5
                          ? 'var(--color-warning-500)'
                          : 'var(--color-danger-500)',
                  }}
                />
              </div>
            </div>
          </div>
        ))}
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
    <div style={{ textAlign: 'center', minWidth: '3.5rem' }}>
      <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color, lineHeight: 1.2 }}>
        {value}
      </div>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-neutral-500)' }}>
        {label}
      </div>
    </div>
  );
}

function VerdictsTable({ verdicts }: { verdicts: ComplianceVerdict[] }) {
  return (
    <div>
      <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, marginBottom: 'var(--space-3)' }}>
        Verdicts ({verdicts.length})
      </h3>
      <div style={{ overflowX: 'auto' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Verdict ID</th>
              <th>Broker</th>
              <th>Obligation</th>
              <th>Status</th>
              <th>State</th>
              <th>Evaluated</th>
            </tr>
          </thead>
          <tbody>
            {verdicts.map((v) => {
              const statusClass =
                v.status === 'compliant'
                  ? 'badge--compliant'
                  : v.status === 'non_compliant'
                    ? 'badge--non-compliant'
                    : 'badge--pending';
              return (
                <tr key={v.verdict_id}>
                  <td><code>{v.verdict_id}</code></td>
                  <td>{v.broker_id}</td>
                  <td>{v.obligation_ref}</td>
                  <td><span className={`badge ${statusClass}`}>{v.status}</span></td>
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
    </div>
  );
}

function HashChainStatus({ chain }: { chain: HashChain }) {
  const verified = chain.verified_at != null;

  return (
    <div>
      <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, marginBottom: 'var(--space-3)' }}>
        Hash Chain Integrity
      </h3>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-3)',
          padding: 'var(--space-4)',
          background: verified ? 'var(--color-success-100)' : 'var(--color-warning-100)',
          borderRadius: 'var(--radius-md)',
          border: `1px solid ${verified ? 'var(--color-success-500)' : 'var(--color-warning-500)'}`,
          marginBottom: 'var(--space-4)',
        }}
      >
        <span
          className={`status-dot ${verified ? 'status-dot--compliant' : 'status-dot--pending'}`}
        />
        <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>
          {verified
            ? `Chain verified at ${new Date(chain.verified_at!).toLocaleString()}`
            : 'Verification pending'}
        </span>
      </div>

      {/* Chain links */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
        {chain.chain.map((link: HashLink) => (
          <div
            key={link.index}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-3)',
              padding: 'var(--space-2) var(--space-3)',
              background: 'var(--color-neutral-100)',
              borderRadius: 'var(--radius-sm)',
              fontSize: 'var(--text-xs)',
              fontFamily: 'var(--font-mono)',
            }}
          >
            <span style={{ fontWeight: 600, color: 'var(--color-neutral-500)', minWidth: '1.5rem' }}>
              #{link.index}
            </span>
            <span style={{ color: 'var(--color-neutral-500)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {link.link_hash}
            </span>
            <span style={{ color: 'var(--color-neutral-400)', fontSize: 'var(--text-xs)' }}>
              {new Date(link.timestamp).toLocaleString()}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
