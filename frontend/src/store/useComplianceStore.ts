/**
 * Zustand store for Agentic Compliance frontend state.
 *
 * Holds pipeline runs, HITL review queue, telemetry data, and compliance
 * reports.  Every async action manages its own loading / error flags so
 * the UI can render precise spinners and inline error messages.
 *
 * All side-effects delegate to the typed API client in `api/client.ts`.
 * The store NEVER constructs URLs or serialises request bodies directly —
 * that responsibility lives in the client layer.
 */

import { create } from 'zustand';
import type {
  PipelineStatus,
  PipelineResult,
  HitlRunSummary,
  HitlRunDetail,
  LockedFSM,
  TelemetryEvent,
  TelemetryInput,
  TelemetryQueryParams,
  IngestResponse,
  ResumeResponse,
  ReportDetail,
  ReviewAction,
  AmendAction,
} from '../api/client';
import {
  triggerPipeline,
  getPipelineStatus,
  getPipelineResult,
  listHitlRuns,
  approveFsm,
  rejectFsm,
  amendFsm,
  resumePipeline,
  ingestTelemetry,
  queryTelemetry,
  generateReport,
  getReport,
} from '../api/client';

// ============================================================================
// Loading / error key sets (compile-time safety for action names)
// ============================================================================

const LOADING_KEYS = [
  'triggerPipeline',
  'fetchStatus',
  'fetchResult',
  'fetchHitl',
  'approveFsm',
  'rejectFsm',
  'amendFsm',
  'resumePipeline',
  'ingestTelemetry',
  'queryTelemetry',
  'generateReport',
  'fetchReport',
] as const;

type LoadingKey = (typeof LOADING_KEYS)[number];
type LoadingState = Record<LoadingKey, boolean>;
type ErrorState = Partial<Record<LoadingKey, string>>;

function initialLoading(): LoadingState {
  const state = {} as LoadingState;
  for (const key of LOADING_KEYS) {
    state[key] = false;
  }
  return state;
}

// ============================================================================
// Store shape
// ============================================================================

export interface ComplianceState {
  // --- Data ----------------------------------------------------------------

  /** Pipeline run summaries shown on the dashboard. */
  runs: PipelineStatus[];

  /** The currently-selected pipeline run's status. */
  currentRun: PipelineStatus | null;

  /** The currently-selected pipeline run's full result (verdicts + scoreboard). */
  currentResult: PipelineResult | null;

  /** Runs that have FSMs waiting for human review. */
  hitlRuns: HitlRunSummary[];

  /** FSMs pending review for the currently-focused HITL run. */
  hitlQueue: LockedFSM[];

  /** Paginated telemetry events from the most recent query. */
  telemetryEvents: TelemetryEvent[];

  /** Total matching telemetry events (for pagination). */
  telemetryTotal: number;

  /** A fetched compliance report. */
  currentReport: ReportDetail | null;

  // --- Loading & errors ----------------------------------------------------

  /** Per-action loading flags. `true` while an API call is in-flight. */
  loading: LoadingState;

  /** Per-action error messages. `null` or absent when no error. */
  errors: ErrorState;

  // --- Actions -------------------------------------------------------------

  /** Kick off a new pipeline run. Returns the `run_id` on success. */
  triggerPipeline: (
    circularPath: string,
    circularId: string,
    telemetry?: TelemetryInput[],
  ) => Promise<string | null>;

  /** Fetch and store status for a specific run. */
  fetchStatus: (runId: string) => Promise<void>;

  /** Fetch and store the full result (verdicts + scoreboard) for a run. */
  fetchResult: (runId: string) => Promise<void>;

  /** Load the HITL review queue. Optionally narrow to a specific run. */
  fetchHitlList: (runId?: string) => Promise<void>;

  /** Approve a single FSM at the HITL gate. */
  approveFsm: (
    fsmId: string,
    runId: string,
    reviewer: string,
    comments?: string,
  ) => Promise<boolean>;

  /** Reject a single FSM at the HITL gate. */
  rejectFsm: (
    fsmId: string,
    runId: string,
    reviewer: string,
    comments: string,
  ) => Promise<boolean>;

  /** Amend (correct and re-submit) a single FSM at the HITL gate. */
  amendFsm: (
    fsmId: string,
    runId: string,
    reviewer: string,
    comments: string,
    correctedFsm: Record<string, unknown>,
  ) => Promise<boolean>;

  /** Resume a paused pipeline after all FSMs are reviewed. */
  resumePipeline: (runId: string) => Promise<ResumeResponse | null>;

  /** Ingest broker telemetry events. Returns the ingest summary. */
  ingestTelemetry: (
    events: TelemetryInput[],
    brokerId?: string,
  ) => Promise<IngestResponse | null>;

  /** Query telemetry with optional filters and pagination. */
  queryTelemetry: (params?: TelemetryQueryParams) => Promise<void>;

  /** Generate an immutable compliance report from a completed run. */
  generateReport: (runId: string) => Promise<string | null>;

  /** Fetch a previously-generated report by ID. */
  fetchReport: (reportId: string) => Promise<void>;

  /** Clear a single error slot. */
  clearError: (key: LoadingKey) => void;

  /** Reset the entire store to its initial state. */
  reset: () => void;
}

// ============================================================================
// Initial state factory
// ============================================================================

function getInitialState(): Pick<
  ComplianceState,
  | 'runs'
  | 'currentRun'
  | 'currentResult'
  | 'hitlRuns'
  | 'hitlQueue'
  | 'telemetryEvents'
  | 'telemetryTotal'
  | 'currentReport'
  | 'loading'
  | 'errors'
> {
  return {
    runs: [],
    currentRun: null,
    currentResult: null,
    hitlRuns: [],
    hitlQueue: [],
    telemetryEvents: [],
    telemetryTotal: 0,
    currentReport: null,
    loading: initialLoading(),
    errors: {},
  };
}

// ============================================================================
// Store
// ============================================================================

const useComplianceStore = create<ComplianceState>()((set) => {
  // ------------------------------------------------------------------
  // Internal helpers
  // ------------------------------------------------------------------

  /** Set `loading[key] = true` and clear any previous error. */
  function start(key: LoadingKey): void {
    set((s) => ({
      loading: { ...s.loading, [key]: true },
      errors: { ...s.errors, [key]: undefined },
    }));
  }

  /** Set `loading[key] = false` and optionally store an error message. */
  function finish(key: LoadingKey, error?: string): void {
    set((s) => ({
      loading: { ...s.loading, [key]: false },
      errors: error
        ? { ...s.errors, [key]: error }
        : { ...s.errors, [key]: undefined },
    }));
  }

  // ------------------------------------------------------------------
  // Actions
  // ------------------------------------------------------------------

  async function _triggerPipeline(
    circularPath: string,
    circularId: string,
    telemetry?: TelemetryInput[],
  ): Promise<string | null> {
    start('triggerPipeline');
    try {
      const res = await triggerPipeline({
        circular_path: circularPath,
        circular_id: circularId,
        telemetry,
      });
      // Prepend the new run to the dashboard list
      const status: PipelineStatus = {
        run_id: res.run_id,
        circular_id: circularId,
        status: res.status,
        total_fsms: 0,
        pending: 0,
        approved: 0,
        rejected: 0,
        amended: 0,
        verdict_count: 0,
        scoreboard_id: null,
        created_at: new Date().toISOString(),
      };
      set((s) => ({ runs: [status, ...s.runs] }));
      finish('triggerPipeline');
      return res.run_id;
    } catch (err) {
      finish('triggerPipeline', err instanceof Error ? err.message : String(err));
      return null;
    }
  }

  async function _fetchStatus(runId: string): Promise<void> {
    start('fetchStatus');
    try {
      const status = await getPipelineStatus(runId);
      set((s) => {
        // Replace or insert in the runs list
        const idx = s.runs.findIndex((r) => r.run_id === runId);
        const runs =
          idx >= 0
            ? [...s.runs.slice(0, idx), status, ...s.runs.slice(idx + 1)]
            : [status, ...s.runs];
        return { currentRun: status, runs };
      });
      finish('fetchStatus');
    } catch (err) {
      finish('fetchStatus', err instanceof Error ? err.message : String(err));
    }
  }

  async function _fetchResult(runId: string): Promise<void> {
    start('fetchResult');
    try {
      const result = await getPipelineResult(runId);
      set({ currentResult: result });
      finish('fetchResult');
    } catch (err) {
      finish('fetchResult', err instanceof Error ? err.message : String(err));
    }
  }

  async function _fetchHitlList(runId?: string): Promise<void> {
    start('fetchHitl');
    try {
      const res = await listHitlRuns(runId);
      if (runId) {
        // Single-run detail response
        const detail = res as HitlRunDetail;
        set({ hitlQueue: detail.fsms });
      } else {
        // Multi-run list response
        const list = res as { runs: HitlRunSummary[] };
        set({ hitlRuns: list.runs });
      }
      finish('fetchHitl');
    } catch (err) {
      finish('fetchHitl', err instanceof Error ? err.message : String(err));
    }
  }

  async function _approveFsm(
    fsmId: string,
    runId: string,
    reviewer: string,
    comments?: string,
  ): Promise<boolean> {
    start('approveFsm');
    try {
      const action: ReviewAction = { reviewer, review_comments: comments };
      const updated = await approveFsm(fsmId, runId, action);
      // Replace the approved FSM in the queue
      set((s) => ({
        hitlQueue: s.hitlQueue.map((f) =>
          f.locked_fsm_id === fsmId ? updated : f,
        ),
      }));
      finish('approveFsm');
      return true;
    } catch (err) {
      finish('approveFsm', err instanceof Error ? err.message : String(err));
      return false;
    }
  }

  async function _rejectFsm(
    fsmId: string,
    runId: string,
    reviewer: string,
    comments: string,
  ): Promise<boolean> {
    start('rejectFsm');
    try {
      const action: ReviewAction = { reviewer, review_comments: comments };
      const updated = await rejectFsm(fsmId, runId, action);
      set((s) => ({
        hitlQueue: s.hitlQueue.map((f) =>
          f.locked_fsm_id === fsmId ? updated : f,
        ),
      }));
      finish('rejectFsm');
      return true;
    } catch (err) {
      finish('rejectFsm', err instanceof Error ? err.message : String(err));
      return false;
    }
  }

  async function _amendFsm(
    fsmId: string,
    runId: string,
    reviewer: string,
    comments: string,
    correctedFsm: Record<string, unknown>,
  ): Promise<boolean> {
    start('amendFsm');
    try {
      const action: AmendAction = {
        reviewer,
        review_comments: comments,
        corrected_fsm: correctedFsm,
      };
      const updated = await amendFsm(fsmId, runId, action);
      set((s) => ({
        hitlQueue: s.hitlQueue.map((f) =>
          f.locked_fsm_id === fsmId ? updated : f,
        ),
      }));
      finish('amendFsm');
      return true;
    } catch (err) {
      finish('amendFsm', err instanceof Error ? err.message : String(err));
      return false;
    }
  }

  async function _resumePipeline(
    runId: string,
  ): Promise<ResumeResponse | null> {
    start('resumePipeline');
    try {
      const res = await resumePipeline(runId);
      // Refresh the run status so the dashboard sees the completed state
      await _fetchStatus(runId);
      finish('resumePipeline');
      return res;
    } catch (err) {
      finish(
        'resumePipeline',
        err instanceof Error ? err.message : String(err),
      );
      return null;
    }
  }

  async function _ingestTelemetry(
    events: TelemetryInput[],
    brokerId?: string,
  ): Promise<IngestResponse | null> {
    start('ingestTelemetry');
    try {
      const res = await ingestTelemetry({ events, broker_id: brokerId });
      finish('ingestTelemetry');
      return res;
    } catch (err) {
      finish(
        'ingestTelemetry',
        err instanceof Error ? err.message : String(err),
      );
      return null;
    }
  }

  async function _queryTelemetry(
    params?: TelemetryQueryParams,
  ): Promise<void> {
    start('queryTelemetry');
    try {
      const res = await queryTelemetry(params);
      set({
        telemetryEvents: res.events,
        telemetryTotal: res.total,
      });
      finish('queryTelemetry');
    } catch (err) {
      finish(
        'queryTelemetry',
        err instanceof Error ? err.message : String(err),
      );
    }
  }

  async function _generateReport(runId: string): Promise<string | null> {
    start('generateReport');
    try {
      const res = await generateReport(runId);
      finish('generateReport');
      return res.report_id;
    } catch (err) {
      finish(
        'generateReport',
        err instanceof Error ? err.message : String(err),
      );
      return null;
    }
  }

  async function _fetchReport(reportId: string): Promise<void> {
    start('fetchReport');
    try {
      const report = await getReport(reportId);
      set({ currentReport: report });
      finish('fetchReport');
    } catch (err) {
      finish('fetchReport', err instanceof Error ? err.message : String(err));
    }
  }

  function _clearError(key: LoadingKey): void {
    set((s) => ({ errors: { ...s.errors, [key]: undefined } }));
  }

  function _reset(): void {
    set(getInitialState());
  }

  return {
    ...getInitialState(),
    triggerPipeline: _triggerPipeline,
    fetchStatus: _fetchStatus,
    fetchResult: _fetchResult,
    fetchHitlList: _fetchHitlList,
    approveFsm: _approveFsm,
    rejectFsm: _rejectFsm,
    amendFsm: _amendFsm,
    resumePipeline: _resumePipeline,
    ingestTelemetry: _ingestTelemetry,
    queryTelemetry: _queryTelemetry,
    generateReport: _generateReport,
    fetchReport: _fetchReport,
    clearError: _clearError,
    reset: _reset,
  };
});

export default useComplianceStore;
