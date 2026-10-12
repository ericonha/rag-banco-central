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
  queries_last_24h: number;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
