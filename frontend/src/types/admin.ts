/** Types for the /api/admin endpoints (pipeline runs + query logs). */

export type Stage = 'scrape' | 'chunk' | 'embed';
export type RunStatus = 'running' | 'ok' | 'done_with_errors' | 'failed';

export interface PipelineRun {
  id: number;
  stage: Stage;
  status: RunStatus;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  params: Record<string, unknown> | null;
  items_total: number;
  items_ok: number;
  items_failed: number;
  error: string | null;
}

export interface PipelineEvent {
  id: number;
  run_id: number;
  level: 'info' | 'warning' | 'error';
  document_id: number | null;
  chunk_id: number | null;
  message: string;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface RetrievedChunk {
  chunk_id: number;
  document_id: number;
  score: number;
}

export interface QueryLog {
  id: number;
  created_at: string;
  question: string;
  answer: string | null;
  retrieved: RetrievedChunk[] | null;
  top_k: number;
  embedding_model: string | null;
  llm_model: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  cost_usd: number | null;
  latency_retrieval_ms: number | null;
  latency_llm_ms: number | null;
  latency_total_ms: number | null;
  status: 'ok' | 'error';
  error: string | null;
}

export interface PipelineStats {
  stage: string;
  total_runs: number;
  successful_runs: number;
  failed_runs: number;
  avg_duration_ms: number;
  total_items_processed: number;
  total_items_failed: number;
  last_run_at: string | null;
  last_run_status: string | null;
}

export interface QueryStats {
  total_queries: number;
  successful_queries: number;
  failed_queries: number;
  avg_latency_retrieval_ms: number;
  avg_latency_llm_ms: number;
  avg_latency_total_ms: number;
  avg_tokens_in: number;
  avg_tokens_out: number;
  total_tokens_in: number;
  total_tokens_out: number;
  total_cost_usd: number;
  queries_last_24h: number;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface DocumentRow {
  id: number;
  title: string | null;
  url: string;
  doc_type: string | null;
  published_at: string | null;
  fetched_at: string;
  chunks: number;
  embedded: number;
}

export interface DocumentsDashboard {
  summary: {
    documents: number;
    chunks: number;
    embedded: number;
    without_chunks: number;
    last_fetched_at: string | null;
  };
  types: { doc_type: string; count: number }[];
  total: number;
  items: DocumentRow[];
}


export interface FeedbackItem {
  id: number;
  conversation_id: string;
  feedback: 1 | -1;
  feedback_comment: string | null;
  feedback_at: string | null;
  question: string | null;
  answer: string;
  grounding: { score: number; ok: boolean } | null;
}

export interface FeedbackDashboard {
  up: number;
  down: number;
  total: number;
  satisfaction: number | null;
  items: FeedbackItem[];
}

export interface PipelineHealth {
  status: 'ok' | 'warning' | 'error';
  issues: { stage: string; severity: 'warning' | 'error'; kind: string; message: string; at: string }[];
  last_run_at: string | null;
}

export interface TimeseriesPoint {
  day: string;
  queries: number;
  errors: number;
  avg_latency_ms: number;
  tokens: number;
  cost_usd: number;
  ungrounded: number;
  up: number;
  down: number;
}

export interface Timeseries {
  days: number;
  points: TimeseriesPoint[];
}
