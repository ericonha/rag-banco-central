/**
 * TypeScript interfaces for BCB RAG Chatbot API
 */

export type Language = 'pt' | 'en';

export interface ChatRequest {
  question: string;
  language: Language;
  conversation_id?: string;
  /** Restrict retrieval to this document type. */
  doc_type?: string;
  /** Restrict retrieval to documents published in the last N days. */
  since_days?: number;
  /** Assistant message being regenerated (replaced on the server). */
  regenerate_of?: number;
}

export interface SourceRef {
  title: string;
  url: string;
  published_at: string;
  doc_type: string;
  chunk_text: string;
}

export interface GroundingFlag {
  type: 'invalid_citation' | 'unsupported_number' | 'low_support' | 'no_citations';
  detail?: string;
  [key: string]: unknown;
}

/** Heuristic faithfulness check of an answer against its retrieved passages. */
export interface Grounding {
  score: number;
  ok: boolean;
  checked: number;
  flags: GroundingFlag[];
}

export interface ChatResponse {
  answer: string;
  sources: SourceRef[];
  retrieved_chunks: number;
  conversation_id?: string;
  message_id?: number | null;
  grounding?: Grounding | null;
}

/** Callbacks for the SSE chat stream. */
export interface ChatStreamHandlers {
  onMeta?: (meta: { conversation_id: string; sources: SourceRef[]; retrieved_chunks: number }) => void;
  onDelta?: (text: string) => void;
  onDone?: (done: { message_id: number | null; grounding: Grounding | null }) => void;
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
  /** Database id of an assistant message (needed for feedback). */
  dbId?: number;
  /** 1 = helpful, -1 = not helpful. */
  feedback?: 1 | -1 | null;
  grounding?: Grounding | null;
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
  feedback?: 1 | -1 | null;
  grounding?: Grounding | null;
}

export interface ConversationDetail {
  conversation_id: string;
  messages: StoredMessage[];
}
