/**
 * HITL Review page — FSM review, approve, reject, amend, and pipeline resume.
 *
 * Route: `/hitl/:runId`
 *
 * Displays each pending LockedFSM with its state diagram (FSMViewer) and
 * review actions.  Once all FSMs are resolved, a "Resume Pipeline" button
 * advances the pipeline through evaluator → scoreboard → completed.
 *
 * States handled:
 *  - loading:   fetching HITL queue
 *  - error:     fetch or review action failed
 *  - populated: FSMs displayed with review controls
 *  - complete:  all FSMs resolved — resume button shown
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

  // ------------------------------------------------------------------
  // Store
  // ------------------------------------------------------------------
  const hitlQueue = useComplianceStore((s) => s.hitlQueue);
  const hitlRuns = useComplianceStore((s) => s.hitlRuns);
  const fetchHitlList = useComplianceStore((s) => s.fetchHitlList);
  const resumePipeline = useComplianceStore((s) => s.resumePipeline);
  const fetchStatus = useComplianceStore((s) => s.fetchStatus);
  const loadingHitl = useComplianceStore((s) => s.loading.fetchHitl);
  const loadingResume = useComplianceStore((s) => s.loading.resumePipeline);
  const errorResume = useComplianceStore((s) => s.errors.resumePipeline);

  // ------------------------------------------------------------------
  // Derive run info from the HITL response
  // ------------------------------------------------------------------
  const runInfo = hitlRuns.find((r) => r.run_id === runId);

  // Filter to FSMs that are still pending
  const pendingFsms = hitlQueue.filter((f) => f.status === 'pending_review');
  const resolvedFsms = hitlQueue.filter((f) => f.status !== 'pending_review');
  const allResolved = pendingFsms.length === 0 && hitlQueue.length > 0;

  // ------------------------------------------------------------------
  // On mount: fetch pending FSMs for this run
  // ------------------------------------------------------------------
  useEffect(() => {
    if (runId) {
      fetchHitlList(runId);
    }
  }, [runId, fetchHitlList]);

  // ------------------------------------------------------------------
  // Resume handler
  // ------------------------------------------------------------------
  async function handleResume() {
    if (!runId) return;
    const res = await resumePipeline(runId);
    if (res) {
      // Refresh status so the dashboard sees the completed run
      await fetchStatus(runId);
      navigate('/');
    }
  }

  // ------------------------------------------------------------------
  // Loading
  // ------------------------------------------------------------------
  if (loadingHitl && hitlQueue.length === 0) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-8)' }}>
        <section className="card">
          <div className="card__header">
            <h2 className="card__title">HITL Review</h2>
          </div>
          <div className="card__body">
            <div className="skeleton" style={{ height: '16rem' }} />
          </div>
        </section>
      </div>
    );
  }

  // ------------------------------------------------------------------
  // Empty / not found
  // ------------------------------------------------------------------
  if (!loadingHitl && hitlQueue.length === 0) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-8)' }}>
        <section className="card">
          <div className="card__header">
            <h2 className="card__title">HITL Review</h2>
          </div>
          <div className="card__body">
            <div className="placeholder-page" style={{ minHeight: '20vh' }}>
              <div className="placeholder-page__icon" aria-hidden="true">👁️</div>
              <h3 className="placeholder-page__title">No FSMs to Review</h3>
              <p className="placeholder-page__subtitle">
                {runId
                  ? `Run "${runId}" has no pending FSMs. They may already be reviewed, or the run does not exist.`
                  : 'No run ID specified. Navigate from the dashboard HITL queue.'}
              </p>
            </div>
            <div style={{ textAlign: 'center', marginTop: 'var(--space-4)' }}>
              <button
                type="button"
                className="btn btn--secondary"
                onClick={() => navigate('/')}
              >
                ← Back to Dashboard
              </button>
            </div>
          </div>
        </section>
      </div>
    );
  }

  // ------------------------------------------------------------------
  // Derived
  // ------------------------------------------------------------------
  const circularRef = runInfo?.circular_ref ?? hitlQueue[0]?.circular_ref ?? 'Unknown';

  // ------------------------------------------------------------------
  // Populated
  // ------------------------------------------------------------------
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-8)' }}>
      {/* Header */}
      <section className="card">
        <div className="card__header">
          <h2 className="card__title">HITL Review — {circularRef}</h2>
          <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
            {allResolved ? (
              <span className="badge badge--compliant">All Reviewed</span>
            ) : (
              <span className="badge badge--pending">{pendingFsms.length} pending</span>
            )}
            {resolvedFsms.length > 0 && (
              <span className="badge badge--neutral">{resolvedFsms.length} resolved</span>
            )}
          </div>
        </div>

        <div className="card__body">
          <MetaRow label="Run ID" value={runId ?? '—'} mono />
          <MetaRow label="Circular" value={circularRef} />
          <MetaRow label="Total FSMs" value={String(hitlQueue.length)} />

          <div style={{ marginTop: 'var(--space-3)' }}>
            <button
              type="button"
              className="btn btn--secondary btn--sm"
              onClick={() => navigate('/')}
            >
              ← Back to Dashboard
            </button>
          </div>
        </div>
      </section>

      {/* Pending FSMs */}
      {pendingFsms.length > 0 && (
        <section>
          <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: 600, marginBottom: 'var(--space-4)' }}>
            Pending Review ({pendingFsms.length})
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
            {pendingFsms.map((fsm) => (
              <FsmReviewCard
                key={fsm.locked_fsm_id}
                lockedFsm={fsm}
                runId={runId!}
                onApproved={() => fetchHitlList(runId)}
                onRejected={() => fetchHitlList(runId)}
                onAmended={() => fetchHitlList(runId)}
              />
            ))}
          </div>
        </section>
      )}

      {/* Resolved FSMs */}
      {resolvedFsms.length > 0 && (
        <section>
          <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: 600, marginBottom: 'var(--space-4)' }}>
            Reviewed ({resolvedFsms.length})
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            {resolvedFsms.map((fsm) => (
              <ResolvedFsmCard key={fsm.locked_fsm_id} lockedFsm={fsm} />
            ))}
          </div>
        </section>
      )}

      {/* Resume section */}
      {allResolved && (
        <section className="card" style={{ border: '2px solid var(--color-success-500)' }}>
          <div className="card__header">
            <h2 className="card__title">All FSMs Reviewed</h2>
            <span className="badge badge--compliant">Ready</span>
          </div>
          <div className="card__body">
            <p style={{ color: 'var(--color-neutral-600)', fontSize: 'var(--text-sm)', marginBottom: 'var(--space-4)' }}>
              All {hitlQueue.length} FSM(s) have been reviewed. Resume the pipeline to run the
              deterministic evaluator and generate the compliance scoreboard.
            </p>

            {errorResume && (
              <div className="inline-error" style={{ marginBottom: 'var(--space-3)' }}>
                ⚠ {errorResume}
              </div>
            )}

            <button
              type="button"
              className="btn btn--primary"
              onClick={handleResume}
              disabled={loadingResume}
            >
              {loadingResume ? 'Running Evaluator…' : '▶ Resume Pipeline'}
            </button>
          </div>
        </section>
      )}
    </div>
  );
}

// ============================================================================
// FsmReviewCard — pending FSM with review actions
// ============================================================================

function FsmReviewCard({
  lockedFsm,
  runId,
  onApproved,
  onRejected,
  onAmended,
}: {
  lockedFsm: LockedFSM;
  runId: string;
  onApproved: () => void;
  onRejected: () => void;
  onAmended: () => void;
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

  function reset() {
    setAction('none');
    setReviewer('');
    setComments('');
    setError(null);
  }

  async function handleApprove(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!reviewer.trim()) {
      setError('Reviewer name is required.');
      return;
    }
    const ok = await approveFsm(
      lockedFsm.locked_fsm_id,
      runId,
      reviewer.trim(),
      comments.trim() || undefined,
    );
    if (ok) {
      reset();
      onApproved();
    } else {
      setError('Approval failed. Check the browser console for details.');
    }
  }

  async function handleReject(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!reviewer.trim()) {
      setError('Reviewer name is required.');
      return;
    }
    if (!comments.trim()) {
      setError('A reason is required for rejection.');
      return;
    }
    const ok = await rejectFsm(
      lockedFsm.locked_fsm_id,
      runId,
      reviewer.trim(),
      comments.trim(),
    );
    if (ok) {
      reset();
      onRejected();
    } else {
      setError('Rejection failed. Check the browser console for details.');
    }
  }

  async function handleAmend(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!reviewer.trim()) {
      setError('Reviewer name is required.');
      return;
    }
    if (!comments.trim()) {
      setError('A description of changes is required for amendment.');
      return;
    }
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(amendedJson);
    } catch {
      setError('Invalid JSON in corrected FSM. Please fix the syntax.');
      return;
    }
    const ok = await amendFsm(
      lockedFsm.locked_fsm_id,
      runId,
      reviewer.trim(),
      comments.trim(),
      parsed,
    );
    if (ok) {
      reset();
      onAmended();
    } else {
      setError('Amendment failed. Check the browser console for details.');
    }
  }

  const isLoading = loadingApprove || loadingReject || loadingAmend;

  return (
    <div
      className="card"
      style={{
        border: '1px solid var(--color-warning-500)',
      }}
    >
      <div className="card__header">
        <div>
          <h4 style={{ fontSize: 'var(--text-base)', fontWeight: 600, margin: 0 }}>
            {lockedFsm.obligation_ref}
          </h4>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-neutral-500)', fontFamily: 'var(--font-mono)', marginTop: 'var(--space-1)' }}>
            {lockedFsm.locked_fsm_id}
          </div>
        </div>
        <span className="badge badge--pending">Pending Review</span>
      </div>

      <div className="card__body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        {/* FSM diagram */}
        <FSMViewer lockedFsm={lockedFsm} />

        {/* Action buttons */}
        {action === 'none' && (
          <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn btn--primary btn--sm"
              onClick={() => setAction('approve')}
              disabled={isLoading}
            >
              ✅ Approve
            </button>
            <button
              type="button"
              className="btn btn--secondary btn--sm"
              onClick={() => setAction('reject')}
              disabled={isLoading}
              style={{ color: 'var(--color-danger-600)', borderColor: 'var(--color-danger-400)' }}
            >
              ❌ Reject
            </button>
            <button
              type="button"
              className="btn btn--secondary btn--sm"
              onClick={() => setAction('amend')}
              disabled={isLoading}
            >
              ✏️ Amend
            </button>
          </div>
        )}

        {/* Inline approve form */}
        {action === 'approve' && (
          <form onSubmit={handleApprove} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            <div style={{ padding: 'var(--space-3)', background: 'var(--color-success-100)', borderRadius: 'var(--radius-md)', border: '1px solid var(--color-success-400)' }}>
              <p style={{ fontSize: 'var(--text-sm)', fontWeight: 500, margin: 0 }}>
                ✅ Approve — the FSM is correct as-is and can be used for compliance evaluation.
              </p>
            </div>
            <ReviewerField value={reviewer} onChange={setReviewer} />
            <label style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
              <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>Comments (optional)</span>
              <input
                type="text"
                className="field-input"
                value={comments}
                onChange={(e) => setComments(e.target.value)}
                placeholder="Looks good, all states and transitions are correct."
              />
            </label>
            {error && <div className="inline-error">{error}</div>}
            <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
              <button type="submit" className="btn btn--primary btn--sm" disabled={isLoading}>
                {loadingApprove ? 'Approving…' : 'Confirm Approve'}
              </button>
              <button type="button" className="btn btn--secondary btn--sm" onClick={reset} disabled={isLoading}>
                Cancel
              </button>
            </div>
          </form>
        )}

        {/* Inline reject form */}
        {action === 'reject' && (
          <form onSubmit={handleReject} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            <div style={{ padding: 'var(--space-3)', background: 'var(--color-danger-100)', borderRadius: 'var(--radius-md)', border: '1px solid var(--color-danger-400)' }}>
              <p style={{ fontSize: 'var(--text-sm)', fontWeight: 500, margin: 0 }}>
                ❌ Reject — the FSM is incorrect and must be re-extracted.
              </p>
            </div>
            <ReviewerField value={reviewer} onChange={setReviewer} />
            <label style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
              <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>
                Reason for rejection <span style={{ color: 'var(--color-danger-500)' }}>*</span>
              </span>
              <textarea
                className="field-input"
                rows={3}
                value={comments}
                onChange={(e) => setComments(e.target.value)}
                placeholder="The timeline rule offset is wrong — should be T+2 not T+1 for this obligation type."
                required
              />
            </label>
            {error && <div className="inline-error">{error}</div>}
            <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
              <button type="submit" className="btn btn--primary btn--sm" disabled={isLoading}
                style={{ background: 'var(--color-danger-600)' }}>
                {loadingReject ? 'Rejecting…' : 'Confirm Reject'}
              </button>
              <button type="button" className="btn btn--secondary btn--sm" onClick={reset} disabled={isLoading}>
                Cancel
              </button>
            </div>
          </form>
        )}

        {/* Inline amend form */}
        {action === 'amend' && (
          <form onSubmit={handleAmend} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            <div style={{ padding: 'var(--space-3)', background: 'var(--color-warning-100)', borderRadius: 'var(--radius-md)', border: '1px solid var(--color-warning-400)' }}>
              <p style={{ fontSize: 'var(--text-sm)', fontWeight: 500, margin: 0 }}>
                ✏️ Amend — correct the FSM and re-submit. The original is preserved in amendment history.
              </p>
            </div>
            <ReviewerField value={reviewer} onChange={setReviewer} />
            <label style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
              <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>
                Description of changes <span style={{ color: 'var(--color-danger-500)' }}>*</span>
              </span>
              <input
                type="text"
                className="field-input"
                value={comments}
                onChange={(e) => setComments(e.target.value)}
                placeholder="Fixed the deadline offset from T+1 to T+2 per the circular text."
                required
              />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
              <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>
                Corrected FSM (JSON) <span style={{ color: 'var(--color-danger-500)' }}>*</span>
              </span>
              <textarea
                className="field-input"
                rows={16}
                value={amendedJson}
                onChange={(e) => setAmendedJson(e.target.value)}
                style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', resize: 'vertical' }}
                required
              />
            </label>
            {error && <div className="inline-error">{error}</div>}
            <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
              <button type="submit" className="btn btn--primary btn--sm" disabled={isLoading}>
                {loadingAmend ? 'Amending…' : 'Confirm Amend'}
              </button>
              <button type="button" className="btn btn--secondary btn--sm" onClick={reset} disabled={isLoading}>
                Cancel
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// ResolvedFsmCard — readonly summary of a reviewed FSM
// ============================================================================

function ResolvedFsmCard({ lockedFsm }: { lockedFsm: LockedFSM }) {
  const statusClass =
    lockedFsm.status === 'approved'
      ? 'badge--compliant'
      : lockedFsm.status === 'rejected'
        ? 'badge--non-compliant'
        : 'badge--pending';

  return (
    <div
      className="card"
      style={{ border: '1px solid var(--color-neutral-300)', opacity: 0.85 }}
    >
      <div className="card__header">
        <div>
          <h4 style={{ fontSize: 'var(--text-base)', fontWeight: 600, margin: 0 }}>
            {lockedFsm.obligation_ref}
          </h4>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-neutral-500)', fontFamily: 'var(--font-mono)', marginTop: 'var(--space-1)' }}>
            {lockedFsm.locked_fsm_id}
          </div>
        </div>
        <span className={`badge ${statusClass}`}>
          {lockedFsm.status.replace(/_/g, ' ')}
        </span>
      </div>

      <div className="card__body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        {lockedFsm.reviewer && (
          <MetaRow label="Reviewer" value={lockedFsm.reviewer} />
        )}
        {lockedFsm.review_comments && (
          <div>
            <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-neutral-500)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Comments
            </span>
            <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-neutral-600)', margin: 'var(--space-1) 0 0 0' }}>
              {lockedFsm.review_comments}
            </p>
          </div>
        )}
        {lockedFsm.amendment_history.length > 0 && (
          <div>
            <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-neutral-500)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Amendments ({lockedFsm.amendment_history.length})
            </span>
          </div>
        )}
        <FSMViewer lockedFsm={lockedFsm} />
      </div>
    </div>
  );
}

// ============================================================================
// Shared sub-components
// ============================================================================

function ReviewerField({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
      <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>
        Reviewer <span style={{ color: 'var(--color-danger-500)' }}>*</span>
      </span>
      <input
        type="text"
        className="field-input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Your name"
        required
      />
    </label>
  );
}

function MetaRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 'var(--space-2)', padding: 'var(--space-1) 0' }}>
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
