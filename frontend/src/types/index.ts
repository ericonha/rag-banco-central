/**
 * TypeScript interfaces for BCB RAG Chatbot API
 */

export type Language = 'pt' | 'en';

export interface ChatRequest {
  question: string;
  language: Language;
  conversation_id?: string;
}

export interface SourceRef {
  title: string;
  url: string;
  published_at: string;
  doc_type: string;
  chunk_text: string;
}

export interface ChatResponse {
  answer: string;
  sources: SourceRef[];
  retrieved_chunks: number;
  conversation_id?: string;
}

export interface DocumentRef {
  id: number;
  title: string;
  url: string;
  published_at: string;
  doc_type: string;
  chunk_count: number;
}

export interface HealthResponse {
  status: string;
  timestamp: string;
  embedding_model?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceRef[];
  retrieved_chunks?: number;
  timestamp: Date;
}

/** Row of GET /api/conversations (sidebar). */
export interface ConversationSummary {
  id: string;
  title: string;
  language: Language;
  created_at: string;
  updated_at: string;
  message_count: number;
}

/** Message as stored by the backend (GET /api/conversations/{id}). */
export interface StoredMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  sources: SourceRef[] | null;
  created_at: string;
}

export interface ConversationDetail {
  conversation_id: string;
  messages: StoredMessage[];
}
