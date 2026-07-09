/**
 * HTTP API client for the Agentic Compliance backend.
 *
 * Uses native `fetch` — no Axios dependency.
 * All requests are proxied through Vite (`/api` → `http://localhost:8000/api`).
 *
 * Every public function maps 1:1 to an M7 REST endpoint.
 * All return types are plain TypeScript interfaces that mirror the backend
 * Pydantic response models exactly.
 */

// ============================================================================
// Shared / utility types
// ============================================================================

/** Generic JSON object — used for dynamic payloads and metadata. */
export type JsonObject = Record<string, unknown>;

// ============================================================================
// Hash chain
// ============================================================================

export interface HashLink {
  index: number;
  timestamp: string;
  data_hash: string;
  previous_hash: string;
  link_hash: string;
}

export interface HashChain {
  root_hash: string;
  chain: HashLink[];
  verified_at: string | null;
}

// ============================================================================
// Compliance obligation models (mirrors backend models/fsm.py)
// ============================================================================

export interface FSMState {
  name: string;
  description: string;
}

export interface FSMTransition {
  from_state: string;
  to_state: string;
  trigger_event: string;
  conditions: JsonObject | null;
}

export interface TimelineRule {
  start_event: string;
  deadline_offset: number;
  grace_period: number;
  time_unit: 'days' | 'hours' | 'months';
  overdue_transition: string;
}

export interface HybridFSM {
  fsm_id: string;
  obligation_ref: string;
  circular_ref: string;
  states: FSMState[];
  initial_state: string;
  transitions: FSMTransition[];
  timeline_rules: TimelineRule[];
  metadata: JsonObject;
}

// ============================================================================
// Locked FSM (mirrors backend models/locked_fsm.py)
// ============================================================================

export type LockStatus =
  | 'pending_review'
  | 'approved'
  | 'rejected'
  | 'amended';

export interface AmendmentRecord {
  version: number;
  amended_by: string;
  amended_at: string;
  changes: string;
  prior_fsm: HybridFSM;
}

export interface LockedFSM {
  locked_fsm_id: string;
  fsm_id: string;
  obligation_ref: string;
  circular_ref: string;
  version: number;
  original_fsm: HybridFSM;
  status: LockStatus;
  reviewer: string | null;
  reviewed_at: string | null;
  review_comments: string | null;
  amendment_history: AmendmentRecord[];
  integrity_hash: string | null;
  hash_link: HashLink | null;
}

// ============================================================================
// Verdict & scoreboard (mirrors backend models/verdict.py, scoreboard.py)
// ============================================================================

export type VerdictStatus = 'compliant' | 'non_compliant' | 'pending';

export interface ComplianceVerdict {
  verdict_id: string;
  obligation_ref: string;
  broker_id: string;
  fsm_ref: string;
  status: VerdictStatus;
  current_state: string;
  evidence: JsonObject;
  evaluated_at: string;
  /** Human-readable explanation derived from the evidence trail (V1.0.2). */
  explanation?: string;
}

export interface ObligationResult {
  obligation_ref: string;
  fsm_ref: string;
  status: VerdictStatus;
  current_state: string;
  evidence_summary: string;
  evaluated_at: string;
}

export interface BrokerScore {
  broker_id: string;
  total_obligations: number;
  compliant: number;
  non_compliant: number;
  pending: number;
  compliance_rate: number;
  obligation_details: ObligationResult[];
  hash_link: HashLink | null;
}

export interface Scoreboard {
  scoreboard_id: string;
  circular_id: string;
  generated_at: string;
  broker_summaries: BrokerScore[];
  hash_chain: HashChain | null;
  metadata: JsonObject;
}

// ============================================================================
// Telemetry (mirrors backend models/telemetry.py)
// ============================================================================

export interface TelemetryEvent {
  event_id: string;
  broker_id: string;
  event_type: string;
  timestamp: string;
  payload: JsonObject;
}

/** Raw input before validation — used for ingest. */
export type TelemetryInput = JsonObject;

export interface TelemetryQueryParams {
  broker_id?: string;
  event_type?: string;
  limit?: number;
  offset?: number;
}

// ============================================================================
// Pipeline Endpoint types
// ============================================================================

/** POST /api/pipeline/trigger — request body */
export interface TriggerRequest {
  circular_path: string;
  circular_id: string;
  telemetry?: TelemetryInput[];
}

/** POST /api/pipeline/trigger — response */
export interface TriggerResponse {
  run_id: string;
  status: string;
  message: string;
}

/** GET /api/pipeline/status/{run_id} — response */
export interface PipelineStatus {
  run_id: string;
  circular_id: string;
  status: string;
  total_fsms: number;
  pending: number;
  approved: number;
  rejected: number;
  amended: number;
  verdict_count: number;
  scoreboard_id: string | null;
  created_at: string | null;
}

/** GET /api/pipeline/result/{run_id} — response */
export interface PipelineResult {
  run_id: string;
  circular_id: string;
  status: string;
  verdicts: ComplianceVerdict[];
  scoreboard: Scoreboard | null;
}

// ============================================================================
// HITL Endpoint types
// ============================================================================

/** POST /api/pipeline/hitl/{fsm_id}/approve — request body */
export interface ReviewAction {
  reviewer: string;
  review_comments?: string;
}

/** POST /api/pipeline/hitl/{fsm_id}/amend — request body */
export interface AmendAction {
  reviewer: string;
  review_comments: string;
  corrected_fsm: JsonObject;
}

/** A single run summary in the HITL list */
export interface HitlRunSummary {
  run_id: string;
  circular_ref: string;
  total_fsms: number;
  pending: number;
  status?: string;
}

/** GET /api/pipeline/hitl — response (no run_id) */
export interface HitlListResponse {
  runs: HitlRunSummary[];
}

/** GET /api/pipeline/hitl?run_id=... — response */
export interface HitlRunDetail {
  run_id: string;
  circular_ref: string;
  total_fsms: number;
  pending: number;
  fsms: LockedFSM[];
}

// ============================================================================
// Telemetry Endpoint types
// ============================================================================

/** POST /api/telemetry/ingest — request body */
export interface IngestRequest {
  events: TelemetryInput[];
  broker_id?: string;
}

/** POST /api/telemetry/ingest — response */
export interface IngestResponse {
  ingested: number;
  rejected: number;
  errors: string[];
}

/** GET /api/telemetry/query — response */
export interface TelemetryQueryResponse {
  total: number;
  events: TelemetryEvent[];
}

// ============================================================================
// Reports Endpoint types
// ============================================================================

/** GET /api/reports/generate/{run_id} — response */
export interface GenerateReportResponse {
  report_id: string;
  run_id: string;
  circular_id: string;
  generated_at: string;
  message: string;
}

/** Report summary block */
export interface ReportSummary {
  total_verdicts: number;
  compliant: number;
  non_compliant: number;
  pending: number;
  compliance_pct: number;
}

/** GET /api/reports/{report_id} — response */
export interface ReportDetail {
  report_id: string;
  run_id: string;
  circular_id: string;
  generated_at: string;
  summary: ReportSummary;
  scoreboard: Scoreboard | null;
  verdicts: ComplianceVerdict[];
}

// ============================================================================
// Internal fetch wrapper
// ============================================================================

class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`HTTP ${status}: ${detail}`);
    this.name = 'ApiError';
  }
}

/**
 * Typed fetch wrapper.  Throws `ApiError` on non-ok responses.
 * All endpoints are relative to `/api` (proxied by Vite).
 */
async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = path.startsWith('/') ? path : `/${path}`;

  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    ...options,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail ?? body?.message ?? JSON.stringify(body);
    } catch {
      // response body is not JSON — keep the status text
    }
    throw new ApiError(res.status, detail);
  }

  // 204 No Content — no body to parse
  if (res.status === 204) {
    return undefined as unknown as T;
  }

  return res.json() as Promise<T>;
}

// ============================================================================
// Public API functions — 1:1 mapping with M7 endpoints
// ============================================================================

// -- Health ------------------------------------------------------------------

/** GET /health */
export async function healthCheck(): Promise<{ status: string; version: string }> {
  return request('/health');
}

// -- Pipeline ----------------------------------------------------------------

/** POST /api/pipeline/trigger — start a new compliance pipeline run. */
export async function triggerPipeline(
  body: TriggerRequest,
): Promise<TriggerResponse> {
  return request<TriggerResponse>('/api/pipeline/trigger', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/** GET /api/pipeline/status/{run_id} */
export async function getPipelineStatus(
  runId: string,
): Promise<PipelineStatus> {
  return request<PipelineStatus>(`/api/pipeline/status/${runId}`);
}

/** GET /api/pipeline/result/{run_id} */
export async function getPipelineResult(
  runId: string,
): Promise<PipelineResult> {
  return request<PipelineResult>(`/api/pipeline/result/${runId}`);
}

// -- HITL --------------------------------------------------------------------

/** GET /api/pipeline/hitl — list runs with pending HITL items. */
export async function listHitlRuns(
  runId?: string,
): Promise<HitlListResponse | HitlRunDetail> {
  const query = runId ? `?run_id=${encodeURIComponent(runId)}` : '';
  return request<HitlListResponse | HitlRunDetail>(
    `/api/pipeline/hitl${query}`,
  );
}

/** POST /api/pipeline/hitl/{fsm_id}/approve */
export async function approveFsm(
  fsmId: string,
  runId: string,
  action: ReviewAction,
): Promise<LockedFSM> {
  const query = `?run_id=${encodeURIComponent(runId)}`;
  return request<LockedFSM>(
    `/api/pipeline/hitl/${fsmId}/approve${query}`,
    {
      method: 'POST',
      body: JSON.stringify(action),
    },
  );
}

/** POST /api/pipeline/hitl/{fsm_id}/reject */
export async function rejectFsm(
  fsmId: string,
  runId: string,
  action: ReviewAction,
): Promise<LockedFSM> {
  const query = `?run_id=${encodeURIComponent(runId)}`;
  return request<LockedFSM>(
    `/api/pipeline/hitl/${fsmId}/reject${query}`,
    {
      method: 'POST',
      body: JSON.stringify(action),
    },
  );
}

/** POST /api/pipeline/hitl/{fsm_id}/amend */
export async function amendFsm(
  fsmId: string,
  runId: string,
  action: AmendAction,
): Promise<LockedFSM> {
  const query = `?run_id=${encodeURIComponent(runId)}`;
  return request<LockedFSM>(
    `/api/pipeline/hitl/${fsmId}/amend${query}`,
    {
      method: 'POST',
      body: JSON.stringify(action),
    },
  );
}

// -- Telemetry ---------------------------------------------------------------

/** POST /api/telemetry/ingest */
export async function ingestTelemetry(
  body: IngestRequest,
): Promise<IngestResponse> {
  return request<IngestResponse>('/api/telemetry/ingest', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/** GET /api/telemetry/query */
export async function queryTelemetry(
  params: TelemetryQueryParams = {},
): Promise<TelemetryQueryResponse> {
  const qs = new URLSearchParams();
  if (params.broker_id) qs.set('broker_id', params.broker_id);
  if (params.event_type) qs.set('event_type', params.event_type);
  if (params.limit != null) qs.set('limit', String(params.limit));
  if (params.offset != null) qs.set('offset', String(params.offset));
  const query = qs.toString() ? `?${qs.toString()}` : '';
  return request<TelemetryQueryResponse>(
    `/api/telemetry/query${query}`,
  );
}

// -- Resume ------------------------------------------------------------------

/** POST /api/pipeline/resume/{run_id} — response */
export interface ResumeResponse {
  run_id: string;
  status: string;
  verdict_count: number;
  scoreboard_id: string | null;
  message: string;
}

/** POST /api/pipeline/{run_id}/resume — resume a paused pipeline. */
export async function resumePipeline(
  runId: string,
): Promise<ResumeResponse> {
  return request<ResumeResponse>(`/api/pipeline/${runId}/resume`, {
    method: 'POST',
  });
}

// -- Reports -----------------------------------------------------------------

/** GET /api/reports/generate/{run_id} */
export async function generateReport(
  runId: string,
): Promise<GenerateReportResponse> {
  return request<GenerateReportResponse>(
    `/api/reports/generate/${runId}`,
  );
}

/** GET /api/reports/{report_id} */
export async function getReport(
  reportId: string,
): Promise<ReportDetail> {
  return request<ReportDetail>(`/api/reports/${reportId}`);
}

// ============================================================================
// Evidence Endpoint types (V2 M3)
// ============================================================================

export interface Rectangle {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface PageRegion {
  page_number: number;
  rectangles: Rectangle[];
}

export interface EvidenceResponse {
  evidence_id: string;
  verdict_id: string;
  circular_ref: string;
  fsm_provenance: {
    fsm_id: string;
    locked_fsm_id: string | null;
    obligation_source: {
      obligation_ref: string;
      source_chunks: {
        chunk_id: string;
        citation_text: string;
        page_range: [number, number];
        page_regions: PageRegion[];
      }[];
      attribution_method: string;
    };
  };
  evaluated_at: string;
  pipeline_run_id: string | null;
  attribution_method: string;
}

export interface FsmEvidenceResponse {
  locked_fsm_id: string | null;
  fsm_id: string;
  circular_ref: string;
  obligation_ref: string;
  source_chunks: {
    chunk_id: string;
    text: string;
    page_range: [number, number];
    section_path: string;
  }[];
  review_status: string | null;
}

export interface ChunkPositionsResponse {
  chunk_id: string;
  circular_ref: string;
  page_range: [number, number];
  page_height: number | null;
  page_width: number | null;
  regions: PageRegion[];
  status: 'complete' | 'extracting' | 'unavailable';
}

// -- Evidence API functions ---------------------------------------------------

/** GET /api/evidence/{verdict_id} */
export async function getEvidenceForVerdict(
  verdictId: string,
): Promise<EvidenceResponse> {
  return request<EvidenceResponse>(`/api/evidence/${verdictId}`);
}

/** GET /api/evidence/fsm/{locked_fsm_id} */
export async function getEvidenceForFsm(
  lockedFsmId: string,
): Promise<FsmEvidenceResponse> {
  return request<FsmEvidenceResponse>(
    `/api/evidence/fsm/${lockedFsmId}`,
  );
}

/** GET /api/chunks/{chunk_id}/positions?circular_ref=... */
export async function getChunkPositions(
  chunkId: string,
  circularRef: string,
): Promise<ChunkPositionsResponse> {
  const qs = `?circular_ref=${encodeURIComponent(circularRef)}`;
  return request<ChunkPositionsResponse>(
    `/api/chunks/${encodeURIComponent(chunkId)}/positions${qs}`,
  );
}

/** GET /api/circulars/{circular_ref}/pdf — returns the PDF URL (not the blob). */
export function getCircularPdfUrl(circularRef: string): string {
  return `/api/circulars/${encodeURIComponent(circularRef)}/pdf`;
}
