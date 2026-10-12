/**
 * API client for BCB RAG backend
 */

import type {
  ChatRequest,
  ChatResponse,
  DocumentRef,
  HealthResponse,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

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

  static async getConversation(conversationId: string): Promise<unknown> {
    const response = await fetch(`${API_BASE_URL}/conversations/${conversationId}`);
    if (!response.ok) {
      throw new Error(`Failed to fetch conversation: ${response.statusText}`);
    }
    return response.json();
  }
}
