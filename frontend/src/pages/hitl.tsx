/**
 * HITL Review page — compliance obligation review, approve, reject, amend, resume.
 *
 * Route: `/hitl/:runId`
 *
 * Displays each pending LockedFSM with the obligation text, workflow diagram,
 * transition/timeline tables, and review actions. Once all obligations are
 * reviewed, a "Resume Pipeline" button advances through evaluator → scoreboard.
 *
 * States: loading | error | populated | all-reviewed
 */

import { useEffect, useState, type FormEvent } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import useComplianceStore from '../store/useComplianceStore';
import FSMViewer from '../components/FSMViewer';
import type { LockedFSM } from '../api/client';

// ============================================================================
// Page
// ============================================================================

export default function HitlReviewPage() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();

  // ── Store ────────────────────────────────────────────────────────────
  const hitlQueue = useComplianceStore((s) => s.hitlQueue);
  const hitlRuns = useComplianceStore((s) => s.hitlRuns);
  const fetchHitlList = useComplianceStore((s) => s.fetchHitlList);
  const resumePipeline = useComplianceStore((s) => s.resumePipeline);
  const fetchStatus = useComplianceStore((s) => s.fetchStatus);
  const loadingHitl = useComplianceStore((s) => s.loading.fetchHitl);
  const loadingResume = useComplianceStore((s) => s.loading.resumePipeline);
  const errorResume = useComplianceStore((s) => s.errors.resumePipeline);

  // ── Derived ──────────────────────────────────────────────────────────
  const runInfo = hitlRuns.find((r) => r.run_id === runId);
  const pendingFsms = hitlQueue.filter((f) => f.status === 'pending_review');
  const resolvedFsms = hitlQueue.filter((f) => f.status !== 'pending_review');
  const allResolved = pendingFsms.length === 0 && hitlQueue.length > 0;
  const totalFsms = hitlQueue.length;

  // ── On mount ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (runId) fetchHitlList(runId);
  }, [runId, fetchHitlList]);

  // ── Resume handler ───────────────────────────────────────────────────
  async function handleResume() {
    if (!runId) return;
    const res = await resumePipeline(runId);
    if (res) {
      await fetchStatus(runId);
      navigate('/');
    }
  }

  const circularRef = runInfo?.circular_ref ?? hitlQueue[0]?.circular_ref ?? 'Unknown';

  // ── Loading ──────────────────────────────────────────────────────────
  if (loadingHitl && hitlQueue.length === 0) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
        <PageHeader circularRef="Loading…" total={0} pending={0} resolved={0} />
        <section className="card">
          <div className="card__body" style={{ padding: 'var(--space-10)' }}>
            <div className="skeleton" style={{ height: '12rem' }} />
          </div>
        </section>
      </div>
    );
  }

  // ── Empty / not found ────────────────────────────────────────────────
  if (!loadingHitl && hitlQueue.length === 0) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
        <PageHeader circularRef="Not Found" total={0} pending={0} resolved={0} />
        <section className="card">
          <div className="card__body">
            <div className="placeholder-page" style={{ minHeight: '20vh' }}>
              <div className="placeholder-page__icon">🔍</div>
              <h3 className="placeholder-page__title">No Pending Reviews</h3>
              <p className="placeholder-page__subtitle">
                All compliance obligations for this run have been reviewed, or the run does not exist.
              </p>
              <button
                type="button"
                className="btn btn--secondary"
                style={{ marginTop: 'var(--space-4)' }}
                onClick={() => navigate('/')}
              >
                Back to Dashboard
              </button>
            </div>
          </div>
        </section>
      </div>
    );
  }

  // ── Populated ────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      {/* Page header with progress */}
      <PageHeader
        circularRef={circularRef}
        total={totalFsms}
        pending={pendingFsms.length}
        resolved={resolvedFsms.length}
      />

      {/* Run metadata */}
      <section className="card">
        <div className="card__body">
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-6)', fontSize: 'var(--text-sm)' }}>
            <div className="meta-row" style={{ flex: 1, minWidth: 0 }}>
              <span className="meta-row__label">Run ID</span>
              <span className="meta-row__value meta-row__value--mono">{runId}</span>
            </div>
            <div className="meta-row" style={{ flex: 1, minWidth: 0 }}>
              <span className="meta-row__label">Circular</span>
              <span className="meta-row__value">{circularRef}</span>
            </div>
            <button
              type="button"
              className="btn btn--secondary btn--sm"
              onClick={() => navigate('/')}
            >
              Back to Dashboard
            </button>
          </div>
        </div>
      </section>

      {/* Pending obligations */}
      {pendingFsms.length > 0 && (
        <div>
          <div className="section-header">
            Pending Review
            <span className="section-header__count">
              {pendingFsms.length} of {totalFsms} obligation{pendingFsms.length !== 1 ? 's' : ''}
            </span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
            {pendingFsms.map((fsm, i) => (
              <FsmReviewCard
                key={fsm.locked_fsm_id}
                lockedFsm={fsm}
                runId={runId!}
                index={totalFsms - pendingFsms.length + i + 1}
                total={totalFsms}
                onReviewed={() => fetchHitlList(runId)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Reviewed obligations */}
      {resolvedFsms.length > 0 && (
        <div>
          <div className="section-header">
            Reviewed
            <span className="section-header__count">{resolvedFsms.length}</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            {resolvedFsms.map((fsm) => (
              <ResolvedFsmCard key={fsm.locked_fsm_id} lockedFsm={fsm} />
            ))}
          </div>
        </div>
      )}

      {/* Resume — all reviewed */}
      {allResolved && (
        <section
          className="card"
          style={{ border: '2px solid var(--color-success-500)', boxShadow: 'var(--shadow-md)' }}
        >
          <div className="card__header">
            <h2 className="card__title">
              <span className="card__title-icon">✅</span>
              All Obligations Reviewed
            </h2>
            <span className="badge badge--compliant">Ready</span>
          </div>
          <div className="card__body">
            <p style={{ color: 'var(--color-slate-600)', fontSize: 'var(--text-sm)', marginBottom: 'var(--space-5)' }}>
              All {totalFsms} compliance obligation{totalFsms !== 1 ? 's' : ''} have been reviewed.
              Resume the pipeline to run the deterministic compliance evaluator and generate an audit scoreboard
              with verifiable hash-chain integrity.
            </p>

            {errorResume && (
              <div className="inline-error" style={{ marginBottom: 'var(--space-4)' }}>
                {errorResume}
              </div>
            )}

            <button
              type="button"
              className="btn btn--primary btn--xl"
              onClick={handleResume}
              disabled={loadingResume}
            >
              {loadingResume ? 'Running Evaluator…' : 'Resume Pipeline'}
            </button>
          </div>
        </section>
      )}
    </div>
  );
}

// ============================================================================
// Page header with progress
// ============================================================================

function PageHeader({
  circularRef,
  total,
  pending,
  resolved,
}: {
  circularRef: string;
  total: number;
  pending: number;
  resolved: number;
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 'var(--space-4)' }}>
      <div>
        <h1 style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, color: 'var(--color-slate-900)', marginBottom: 'var(--space-1)' }}>
          Compliance Review
        </h1>
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-slate-500)', fontFamily: 'var(--font-mono)' }}>
          {circularRef}
        </p>
      </div>
      {total > 0 && (
        <div className="progress-indicator">
          Reviewing obligation{' '}
          <span className="progress-indicator__current">{resolved + 1}</span>
          {' '}of{' '}{total}
          {pending > 0 && (
            <span className="badge badge--pending" style={{ marginLeft: 'var(--space-2)' }}>
              {pending} pending
            </span>
          )}
          {pending === 0 && (
            <span className="badge badge--compliant" style={{ marginLeft: 'var(--space-2)' }}>
              Complete
            </span>
          )}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// FsmReviewCard — pending obligation with review actions
// ============================================================================

function FsmReviewCard({
  lockedFsm,
  runId,
  index,
  total,
  onReviewed,
}: {
  lockedFsm: LockedFSM;
  runId: string;
  index: number;
  total: number;
  onReviewed: () => void;
}) {
  const approveFsm = useComplianceStore((s) => s.approveFsm);
  const rejectFsm = useComplianceStore((s) => s.rejectFsm);
  const amendFsm = useComplianceStore((s) => s.amendFsm);
  const loadingApprove = useComplianceStore((s) => s.loading.approveFsm);
  const loadingReject = useComplianceStore((s) => s.loading.rejectFsm);
  const loadingAmend = useComplianceStore((s) => s.loading.amendFsm);

  const [action, setAction] = useState<'none' | 'approve' | 'reject' | 'amend'>('none');
  const [reviewer, setReviewer] = useState('');
  const [comments, setComments] = useState('');
  const [amendedJson, setAmendedJson] = useState(
    JSON.stringify(lockedFsm.original_fsm, null, 2),
  );
  const [error, setError] = useState<string | null>(null);

  const og = lockedFsm.original_fsm;
  const clauseText = (og?.metadata as Record<string, unknown>)?.clause_text as string | undefined;

  function reset() {
    setAction('none'); setReviewer(''); setComments(''); setError(null);
  }

  async function handleApprove(e: FormEvent) {
    e.preventDefault(); setError(null);
    if (!reviewer.trim()) { setError('Reviewer name is required.'); return; }
    const ok = await approveFsm(lockedFsm.locked_fsm_id, runId, reviewer.trim(), comments.trim() || undefined);
    ok ? (reset(), onReviewed()) : setError('Approval failed.');
  }

  async function handleReject(e: FormEvent) {
    e.preventDefault(); setError(null);
    if (!reviewer.trim()) { setError('Reviewer name is required.'); return; }
    if (!comments.trim()) { setError('A reason is required for rejection.'); return; }
    const ok = await rejectFsm(lockedFsm.locked_fsm_id, runId, reviewer.trim(), comments.trim());
    ok ? (reset(), onReviewed()) : setError('Rejection failed.');
  }

  async function handleAmend(e: FormEvent) {
    e.preventDefault(); setError(null);
    if (!reviewer.trim()) { setError('Reviewer name is required.'); return; }
    if (!comments.trim()) { setError('A description of changes is required.'); return; }
    let parsed: Record<string, unknown>;
    try { parsed = JSON.parse(amendedJson); } catch { setError('Invalid JSON in corrected obligation.'); return; }
    const ok = await amendFsm(lockedFsm.locked_fsm_id, runId, reviewer.trim(), comments.trim(), parsed);
    ok ? (reset(), onReviewed()) : setError('Amendment failed.');
  }

  const isLoading = loadingApprove || loadingReject || loadingAmend;

  return (
    <section className="card" style={{ borderColor: 'var(--color-warning-500)', borderWidth: 1 }}>
      {/* Card header */}
      <div className="card__header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '1.5rem',
              height: '1.5rem',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--color-warning-100)',
              color: 'var(--color-warning-700)',
              fontSize: 'var(--text-xs)',
              fontWeight: 700,
            }}
          >
            {index}
          </span>
          <div>
            <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, margin: 0, color: 'var(--color-slate-900)' }}>
              Compliance Obligation — {lockedFsm.obligation_ref}
            </h3>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-slate-500)', fontFamily: 'var(--font-mono)', marginTop: 'var(--space-1)' }}>
              Obligation ID: {lockedFsm.locked_fsm_id}
            </div>
          </div>
        </div>
        <span className="badge badge--pending">Reviewing {index} of {total}</span>
      </div>

      <div className="card__body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>
        {/* Obligation text — prominent */}
        {clauseText && (
          <div className="obligation-text">
            <div style={{ fontSize: 'var(--text-2xs)', fontWeight: 600, color: 'var(--color-brand-500)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 'var(--space-2)' }}>
              Regulatory Text
            </div>
            {clauseText}
          </div>
        )}

        {/* Workflow diagram */}
        <FSMViewer lockedFsm={lockedFsm} />

        {/* Action buttons */}
        {action === 'none' && (
          <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap', marginTop: 'var(--space-2)' }}>
            <button type="button" className="btn btn--success btn--lg" onClick={() => setAction('approve')} disabled={isLoading}>
              Approve
            </button>
            <button type="button" className="btn btn--danger btn--lg" onClick={() => setAction('reject')} disabled={isLoading}>
              Reject
            </button>
            <button type="button" className="btn btn--secondary btn--lg" onClick={() => setAction('amend')} disabled={isLoading}>
              Amend
            </button>
          </div>
        )}

        {/* Approve form */}
        {action === 'approve' && (
          <form onSubmit={handleApprove} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            <div className="action-panel action-panel--approve">
              <p style={{ fontSize: 'var(--text-sm)', fontWeight: 500, margin: 0, color: 'var(--color-success-800)' }}>
                The compliance obligation, workflow states, transitions, and timeline rules are correct as shown.
              </p>
            </div>
            <ReviewerField value={reviewer} onChange={setReviewer} />
            <label style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
              <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--color-slate-700)' }}>Comments (optional)</span>
              <input type="text" className="field-input" value={comments} onChange={(e) => setComments(e.target.value)} placeholder="All states and timeline rules are accurate." />
            </label>
            {error && <div className="inline-error">{error}</div>}
            <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
              <button type="submit" className="btn btn--success btn--lg" disabled={isLoading}>{loadingApprove ? 'Approving…' : 'Confirm Approval'}</button>
              <button type="button" className="btn btn--secondary" onClick={reset} disabled={isLoading}>Cancel</button>
            </div>
          </form>
        )}

        {/* Reject form */}
        {action === 'reject' && (
          <form onSubmit={handleReject} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            <div className="action-panel action-panel--reject">
              <p style={{ fontSize: 'var(--text-sm)', fontWeight: 500, margin: 0, color: 'var(--color-danger-800)' }}>
                This obligation is incorrectly extracted and must be re-processed from the source circular.
              </p>
            </div>
            <ReviewerField value={reviewer} onChange={setReviewer} />
            <label style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
              <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--color-slate-700)' }}>
                Reason for Rejection <span style={{ color: 'var(--color-danger-500)' }}>*</span>
              </span>
              <textarea className="field-input field-textarea" rows={3} value={comments} onChange={(e) => setComments(e.target.value)} placeholder="Explain why this obligation is incorrect — e.g., wrong deadline offset, missing state, incorrect trigger event." required />
            </label>
            {error && <div className="inline-error">{error}</div>}
            <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
              <button type="submit" className="btn btn--danger btn--lg" disabled={isLoading}>{loadingReject ? 'Rejecting…' : 'Confirm Rejection'}</button>
              <button type="button" className="btn btn--secondary" onClick={reset} disabled={isLoading}>Cancel</button>
            </div>
          </form>
        )}

        {/* Amend form */}
        {action === 'amend' && (
          <form onSubmit={handleAmend} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            <div className="action-panel action-panel--amend">
              <p style={{ fontSize: 'var(--text-sm)', fontWeight: 500, margin: 0, color: 'var(--color-warning-800)' }}>
                The obligation is mostly correct but requires minor corrections. Edit the workflow JSON below and re-submit.
              </p>
            </div>
            <ReviewerField value={reviewer} onChange={setReviewer} />
            <label style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
              <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--color-slate-700)' }}>
                Description of Changes <span style={{ color: 'var(--color-danger-500)' }}>*</span>
              </span>
              <input type="text" className="field-input" value={comments} onChange={(e) => setComments(e.target.value)} placeholder="Fixed deadline offset from T+1 to T+2 per the circular text." required />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
              <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--color-slate-700)' }}>
                Corrected Workflow (JSON) <span style={{ color: 'var(--color-danger-500)' }}>*</span>
              </span>
              <textarea className="field-input field-textarea" rows={16} value={amendedJson} onChange={(e) => setAmendedJson(e.target.value)} required />
            </label>
            {error && <div className="inline-error">{error}</div>}
            <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
              <button type="submit" className="btn btn--primary btn--lg" disabled={isLoading}>{loadingAmend ? 'Submitting…' : 'Submit Amendment'}</button>
              <button type="button" className="btn btn--secondary" onClick={reset} disabled={isLoading}>Cancel</button>
            </div>
          </form>
        )}
      </div>
    </section>
  );
}

// ============================================================================
// ResolvedFsmCard — readonly summary of a reviewed obligation
// ============================================================================

function ResolvedFsmCard({ lockedFsm }: { lockedFsm: LockedFSM }) {
  const statusClass =
    lockedFsm.status === 'approved' ? 'badge--compliant'
    : lockedFsm.status === 'rejected' ? 'badge--non-compliant'
    : 'badge--pending';

  return (
    <details style={{ background: '#fff', border: '1px solid var(--color-slate-200)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
      <summary
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: 'var(--space-4) var(--space-5)',
          cursor: 'pointer',
          userSelect: 'none',
          listStyle: 'none',
        }}
      >
        <div style={{ minWidth: 0 }}>
          <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-slate-700)' }}>
            {lockedFsm.obligation_ref}
          </span>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-slate-400)', fontFamily: 'var(--font-mono)', marginLeft: 'var(--space-3)' }}>
            {lockedFsm.locked_fsm_id}
          </span>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center' }}>
          {lockedFsm.reviewer && (
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-slate-500)' }}>
              by {lockedFsm.reviewer}
            </span>
          )}
          <span className={`badge ${statusClass}`}>
            {lockedFsm.status.replace(/_/g, ' ')}
          </span>
        </div>
      </summary>
      <div style={{ padding: '0 var(--space-5) var(--space-5) var(--space-5)' }}>
        {lockedFsm.review_comments && (
          <div className="obligation-text" style={{ marginBottom: 'var(--space-4)' }}>
            <div style={{ fontSize: 'var(--text-2xs)', fontWeight: 600, color: 'var(--color-slate-500)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 'var(--space-2)' }}>
              Review Comments
            </div>
            {lockedFsm.review_comments}
          </div>
        )}
        {lockedFsm.amendment_history.length > 0 && (
          <div style={{ marginBottom: 'var(--space-4)', fontSize: 'var(--text-xs)', color: 'var(--color-slate-500)' }}>
            {lockedFsm.amendment_history.length} amendment{lockedFsm.amendment_history.length !== 1 ? 's' : ''}
          </div>
        )}
        <FSMViewer lockedFsm={lockedFsm} />
      </div>
    </details>
  );
}

// ============================================================================
// Shared components
// ============================================================================

function ReviewerField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
      <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--color-slate-700)' }}>
        Reviewer Name <span style={{ color: 'var(--color-danger-500)' }}>*</span>
      </span>
      <input type="text" className="field-input" value={value} onChange={(e) => onChange(e.target.value)} placeholder="Enter your name" required />
    </label>
  );
}
