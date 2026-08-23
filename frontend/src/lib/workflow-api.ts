import api from './api';

/**
 * Attempt history record stored in WorkflowStep.step_metadata.attempt_history.
 * Produced by RetryingChatProvider (WP-REC-03D).
 */
export interface AttemptHistoryRecord {
  attempt_number: number;
  outcome: string;
  error_type: string;
  backoff_delay_seconds: number;
}

/**
 * Source citation referenced by a risk recommendation.
 */
export interface RecommendationSource {
  document_id: string;
  version: string;
  chunk_id: string;
}

/**
 * Recommended action for mitigating a supply risk.
 */
export interface RecommendedAction {
  action_type: string;
  title: string;
  rationale: string;
  requires_approval: boolean;
}

/**
 * A single risk addressed by the AI recommendation.
 */
export interface RecommendationRisk {
  risk_id: string;
  summary: string;
  business_impact: string;
  recommended_actions: RecommendedAction[];
  sources: RecommendationSource[];
}

/**
 * Validated recommendation content (mirrors RecommendationData wire schema).
 */
export interface RecommendationContent {
  schema_version: string;
  run_id: string;
  plan_id: string;
  risks: RecommendationRisk[];
}

/**
 * Read-only API response for a Recommendation row.
 */
export interface RecommendationResponse {
  id: string;
  status: 'VALIDATED';
  schema_version: string | null;
  content: RecommendationContent | null;
  created_at: string;
  updated_at: string;
}

/**
 * A single workflow step record.
 */
export interface WorkflowStep {
  id: string;
  run_id: string;
  correlation_id: string;
  seq: number;
  step_name: string;
  status: string;
  model_name: string | null;
  latency_ms: number | null;
  token_usage: Record<string, number> | null;
  step_metadata: Record<string, unknown> | null;
  error_code: string | null;
  error_detail: string | null;
  started_at: string;
  completed_at: string | null;
  created_at: string;
}

/**
 * Detailed workflow run response (GET /workflow-runs/{run_id}).
 */
export interface WorkflowRunDetail {
  id: string;
  correlation_id: string;
  state: string;
  plan_id: string;
  triggered_by: string | null;
  error_code: string | null;
  error_detail: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  steps: WorkflowStep[];
  recommendation: RecommendationResponse | null;
}

/**
 * Lightweight workflow run summary (GET /workflow-runs list items).
 */
export interface WorkflowRunSummary {
  id: string;
  correlation_id: string;
  state: string;
  plan_id: string;
  triggered_by: string | null;
  error_code: string | null;
  error_detail: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * Paginated list response.
 */
export interface WorkflowRunListResponse {
  items: WorkflowRunSummary[];
  limit: number;
  offset: number;
  total: number;
}

/**
 * Fetch a single workflow run with steps and optional recommendation.
 */
export async function fetchWorkflowRun(runId: string): Promise<WorkflowRunDetail> {
  const response = await api.get(`/workflow-runs/${runId}`);
  return response.data;
}

/**
 * Fetch a paginated list of workflow run summaries.
 *
 * @param limit   - page size.
 * @param offset  - page offset.
 * @param planCode - optional production plan code filter (e.g. PLAN-2026-W31).
 *   When provided, the backend resolves the code to the plan UUID server-side
 *   and returns only runs for that plan. Omitted/undefined → no filter.
 */
export async function fetchWorkflowRuns(
  limit: number,
  offset: number,
  planCode?: string,
): Promise<WorkflowRunListResponse> {
  const params: Record<string, number | string> = { limit, offset };
  if (planCode !== undefined) {
    params.plan_code = planCode;
  }
  const response = await api.get('/workflow-runs', { params });
  return response.data;
}
