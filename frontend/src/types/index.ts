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

export interface AppState {
  messages: Message[];
  language: Language;
  loading: boolean;
  error?: string;
  documents: DocumentRef[];
}
