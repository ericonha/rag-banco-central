/**
 * API client for BCB RAG backend
 */

import type {
  ChatRequest,
  ChatResponse,
  ChatStreamHandlers,
  ConversationDetail,
  ConversationSummary,
  DocumentRef,
  HealthResponse,
} from '../types';
import type {
  DocumentsDashboard,
  FeedbackDashboard,
  PipelineHealth,
  Timeseries,
  Paginated,
  PipelineEvent,
  PipelineRun,
  PipelineStats,
  QueryLog,
  QueryStats,
} from '../types/admin';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

async function getJson<T>(path: string, errorLabel: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(`${errorLabel}: ${response.statusText}`);
  }
  return response.json();
}

function toQuery(params: Record<string, string | number | undefined>): string {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') qs.set(key, String(value));
  }
  const text = qs.toString();
  return text ? `?${text}` : '';
}

/** HTTP 429: too many requests; `retryAfter` is in seconds. */
export class RateLimitError extends Error {
  constructor(public retryAfter: number) {
    super('Rate limit exceeded');
  }
}

function rateLimited(response: Response): RateLimitError {
  return new RateLimitError(Number(response.headers.get('Retry-After')) || 30);
}

/** The stream endpoint could not be used at all (nothing was received) — safe to fall back. */
export class StreamUnavailableError extends Error {}

function dispatchSse(raw: string, handlers: ChatStreamHandlers): void {
  let event = 'message';
  const data: string[] = [];
  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''));
  }
  if (!data.length) return;
  const payload = JSON.parse(data.join('\n'));
  if (event === 'meta') handlers.onMeta?.(payload);
  else if (event === 'delta') handlers.onDelta?.(payload.text);
  else if (event === 'done') handlers.onDone?.(payload);
  else if (event === 'error') throw new Error(payload.detail || 'Stream error');
}

export class ApiClient {
  static async checkHealth(): Promise<HealthResponse> {
    const response = await fetch(`${API_BASE_URL}/health`);
    if (!response.ok) {
      throw new Error(`Health check failed: ${response.statusText}`);
    }
    return response.json();
  }

  static async chat(request: ChatRequest): Promise<ChatResponse> {
    const response = await fetch(`${API_BASE_URL}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    });

    if (response.status === 429) throw rateLimited(response);
    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Chat request failed: ${error || response.statusText}`);
    }

    return response.json();
  }

  /**
   * Streamed chat (Server-Sent Events). Resolves when the stream ends; rejects on transport
   * errors or an `error` event. `onMeta` fires first, so callers can tell whether anything
   * arrived before a failure.
   */
  static async chatStream(
    request: ChatRequest,
    handlers: ChatStreamHandlers,
    signal?: AbortSignal,
  ): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify(request),
      signal,
    });
    if (response.status === 429) throw rateLimited(response);
    if (!response.ok || !response.body) {
      const error = await response.text().catch(() => '');
      throw new StreamUnavailableError(`Chat request failed: ${error || response.statusText}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let sep: number;
      while ((sep = buffer.indexOf('\n\n')) !== -1) {
        const raw = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        dispatchSse(raw, handlers);
      }
    }
  }

  static async sendFeedback(messageId: number, value: -1 | 0 | 1, comment?: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/messages/${messageId}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value, comment }),
    });
    if (!response.ok) {
      throw new Error(`Failed to save feedback: ${response.statusText}`);
    }
  }

  /** Browser download URL for a conversation export. */
  static exportUrl(conversationId: string, format: 'md' | 'json'): string {
    return `${API_BASE_URL}/conversations/${conversationId}/export?format=${format}`;
  }

  static getFeedback(params: { value?: number; limit?: number; offset?: number } = {}): Promise<FeedbackDashboard> {
    return getJson(`/admin/feedback${toQuery(params)}`, 'Failed to fetch feedback');
  }

  static getPipelineHealth(): Promise<PipelineHealth> {
    return getJson('/admin/pipeline/health', 'Failed to fetch pipeline health');
  }

  static async getDocuments(limit: number = 20): Promise<DocumentRef[]> {
    const response = await fetch(`${API_BASE_URL}/documents?limit=${limit}`);
    if (!response.ok) {
      throw new Error(`Failed to fetch documents: ${response.statusText}`);
    }
    return response.json();
  }

  static getConversation(conversationId: string): Promise<ConversationDetail> {
    return getJson(`/conversations/${conversationId}`, 'Failed to fetch conversation');
  }

  static listConversations(params: { q?: string; days?: number } = {}): Promise<ConversationSummary[]> {
    return getJson(`/conversations${toQuery(params)}`, 'Failed to fetch conversations');
  }

  static getTimeseries(days = 14): Promise<Timeseries> {
    return getJson(`/admin/stats/timeseries${toQuery({ days })}`, 'Failed to fetch timeseries');
  }

  static async deleteConversation(conversationId: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/conversations/${conversationId}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      throw new Error(`Failed to delete conversation: ${response.statusText}`);
    }
  }

  // ---- Admin / observability -------------------------------------------

  static getPipelineRuns(params: {
    stage?: string;
    status?: string;
    page?: number;
    page_size?: number;
  }): Promise<Paginated<PipelineRun>> {
    return getJson(`/admin/runs${toQuery(params)}`, 'Failed to fetch pipeline runs');
  }

  static getDocumentsDashboard(params: {
    q?: string;
    doc_type?: string;
    limit?: number;
    offset?: number;
  }): Promise<DocumentsDashboard> {
    return getJson(`/admin/documents${toQuery(params)}`, 'Failed to fetch documents');
  }

  static getPipelineStats(): Promise<PipelineStats[]> {
    return getJson('/admin/stats/pipeline', 'Failed to fetch pipeline stats');
  }

  static getRunEvents(runId: number): Promise<PipelineEvent[]> {
    return getJson(`/admin/runs/${runId}/events`, 'Failed to fetch run events');
  }

  static getQueryLogs(params: {
    hours?: number;
    page?: number;
    page_size?: number;
  }): Promise<Paginated<QueryLog>> {
    return getJson(`/admin/queries${toQuery(params)}`, 'Failed to fetch query logs');
  }

  static getQueryStats(): Promise<QueryStats> {
    return getJson('/admin/stats/queries', 'Failed to fetch query stats');
  }
}
