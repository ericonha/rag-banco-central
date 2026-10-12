/**
 * API client for BCB RAG backend
 */

import type {
  ChatRequest,
  ChatResponse,
  ConversationDetail,
  ConversationSummary,
  DocumentRef,
  HealthResponse,
} from '../types';
import type {
  DocumentsDashboard,
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

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Chat request failed: ${error || response.statusText}`);
    }

    return response.json();
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

  static listConversations(): Promise<ConversationSummary[]> {
    return getJson('/conversations', 'Failed to fetch conversations');
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
