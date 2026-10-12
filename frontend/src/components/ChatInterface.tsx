import { useEffect, useRef, useState } from 'react';
import { MessageList } from './MessageList';
import { ApiClient, StreamUnavailableError } from '../services/api';
import { STRINGS } from '../i18n';
import type { Language, Message, StoredMessage } from '../types';

interface ChatInterfaceProps {
  conversationId: string;
  language: Language;
  /** Called after an exchange is saved so the sidebar can refresh. */
  onExchange: () => void;
}

type ChatError = { kind: 'connect' } | { kind: 'text'; text: string };

const toMessage = (m: StoredMessage): Message => ({
  id: String(m.id),
  role: m.role,
  content: m.content,
  sources: m.sources ?? undefined,
  dbId: m.role === 'assistant' ? m.id : undefined,
  feedback: m.feedback ?? null,
  grounding: m.grounding ?? null,
  timestamp: new Date(m.created_at),
});

export function ChatInterface({ conversationId, language, onExchange }: ChatInterfaceProps) {
  const t = STRINGS[language];
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  // true once the first streamed token arrived (the typing dots give way to the text)
  const [streaming, setStreaming] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [error, setError] = useState<ChatError | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [docType, setDocType] = useState('');
  const [sinceDays, setSinceDays] = useState(0);
  const [docTypes, setDocTypes] = useState<string[]>([]);

  useEffect(() => {
    ApiClient.getDocumentsDashboard({ limit: 1 })
      .then((d) => setDocTypes(d.types.map((x) => x.doc_type).filter(Boolean)))
      .catch(() => undefined);
  }, []);

  useEffect(() => () => abortRef.current?.abort(), []);

  // Load the saved history whenever the conversation changes.
  useEffect(() => {
    let cancelled = false;
    setHistoryLoading(true);
    setMessages([]);
    setError(null);
    ApiClient.getConversation(conversationId)
      .then((detail) => {
        if (!cancelled) setMessages(detail.messages.map(toMessage));
      })
      .catch(() => {
        if (!cancelled) setError({ kind: 'connect' });
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  const resizeInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 168)}px`;
  };

  const stop = () => abortRef.current?.abort();

  /** `regenerateOf`: assistant message id whose answer is being replaced (no new user bubble). */
  const run = async (question: string, regenerateOf?: number) => {
    if (!question || loading) return;

    if (regenerateOf === undefined) {
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: 'user', content: question, timestamp: new Date() },
      ]);
    }
    setInput('');
    requestAnimationFrame(resizeInput);
    setLoading(true);
    setError(null);
    const controller = new AbortController();
    abortRef.current = controller;

    const request = {
      question,
      language,
      conversation_id: conversationId,
      ...(docType ? { doc_type: docType } : {}),
      ...(sinceDays ? { since_days: sinceDays } : {}),
      ...(regenerateOf !== undefined ? { regenerate_of: regenerateOf } : {}),
    };
    const assistantId = crypto.randomUUID();
    let started = false;
    const patch = (fn: (m: Message) => Message) =>
      setMessages((prev) => prev.map((m) => (m.id === assistantId ? fn(m) : m)));

    try {
      try {
        await ApiClient.chatStream(
          request,
          {
          onMeta: (meta) => {
            started = true;
            setMessages((prev) => [
              ...prev,
              {
                id: assistantId,
                role: 'assistant',
                content: '',
                sources: meta.sources,
                retrieved_chunks: meta.retrieved_chunks,
                timestamp: new Date(),
              },
            ]);
          },
          onDelta: (text) => {
            setStreaming(true);
            patch((m) => ({ ...m, content: m.content + text }));
          },
          onDone: (done) =>
            patch((m) => ({ ...m, dbId: done.message_id ?? undefined, grounding: done.grounding })),
          },
          controller.signal,
        );
      } catch (err) {
        // Nothing arrived: the streaming endpoint is unavailable, so use the regular one.
        if (started || !(err instanceof StreamUnavailableError || err instanceof TypeError)) throw err;
        const response = await ApiClient.chat(request);
        if (regenerateOf !== undefined) setMessages((prev) => prev.filter((m) => m.dbId !== regenerateOf));
        setMessages((prev) => [
          ...prev,
          {
            id: assistantId,
            role: 'assistant',
            content: response.answer,
            sources: response.sources,
            retrieved_chunks: response.retrieved_chunks,
            dbId: response.message_id ?? undefined,
            grounding: response.grounding ?? null,
            timestamp: new Date(),
          },
        ]);
      }
      onExchange();
    } catch (err) {
      if (controller.signal.aborted) {
        // User pressed Stop: keep what was streamed, drop an empty placeholder.
        setMessages((prev) => prev.filter((m) => m.id !== assistantId || m.content.trim() !== ''));
        setError({ kind: 'text', text: t.stopped });
      } else {
        setError({ kind: 'text', text: err instanceof Error ? err.message : String(err) });
      }
    } finally {
      abortRef.current = null;
      setLoading(false);
      setStreaming(false);
      textareaRef.current?.focus();
    }
  };

  const submit = (raw: string) => run(raw.trim());

  const regenerate = () => {
    const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant');
    const lastUser = [...messages].reverse().find((m) => m.role === 'user');
    if (!lastAssistant?.dbId || !lastUser) return;
    // Drop the old answer from the screen; the server replaces it when the new one is saved.
    setMessages((prev) => prev.filter((m) => m.id !== lastAssistant.id));
    run(lastUser.content, lastAssistant.dbId);
  };

  const setComment = (message: Message, comment: string) => {
    if (message.dbId) ApiClient.sendFeedback(message.dbId, -1, comment).catch(() => undefined);
  };

  const setFeedback = (message: Message, value: 1 | -1) => {
    if (!message.dbId) return;
    const next = message.feedback === value ? 0 : value;
    const apply = (fb: 1 | -1 | null) =>
      setMessages((prev) => prev.map((m) => (m.id === message.id ? { ...m, feedback: fb } : m)));
    apply(next === 0 ? null : (next as 1 | -1));
    ApiClient.sendFeedback(message.dbId, next as -1 | 0 | 1).catch(() => apply(message.feedback ?? null));
  };

  const showEmpty = messages.length === 0 && !loading && !historyLoading;

  return (
    <div className="chat">
      <div className="thread">
        <div className="thread-inner">
          {showEmpty && (
            <div className="empty">
              <h1>{t.emptyTitle}</h1>
              <p>{t.emptyBody}</p>
              <div className="examples" role="list" aria-label={t.examplesLabel}>
                {t.examples.map((example) => (
                  <button
                    key={example}
                    type="button"
                    role="listitem"
                    className="example"
                    onClick={() => submit(example)}
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>
          )}
          <MessageList
            messages={messages}
            loading={loading && !streaming}
            language={language}
            onFeedback={setFeedback}
            onComment={setComment}
            onRegenerate={regenerate}
          />
          {error && (
            <div className="notice" role="alert">
              {error.kind === 'connect' ? t.connectError : error.text}
            </div>
          )}
        </div>
      </div>

      <div className="composer-wrap">
        <div className="chat-filters" role="group" aria-label={t.filtersActive}>
          <select value={docType} onChange={(e) => setDocType(e.target.value)} aria-label={t.filterType} disabled={loading}>
            <option value="">{t.allTypes}</option>
            {docTypes.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
          <select value={sinceDays} onChange={(e) => setSinceDays(Number(e.target.value))} aria-label={t.filterPeriod} disabled={loading}>
            <option value={0}>{t.anyTime}</option>
            <option value={7}>{t.last7}</option>
            <option value={30}>{t.last30}</option>
            <option value={365}>{t.last365}</option>
          </select>
          {(docType || sinceDays > 0) && (
            <button
              type="button"
              className="link-btn"
              onClick={() => {
                setDocType('');
                setSinceDays(0);
              }}
            >
              {t.clearFilters}
            </button>
          )}
        </div>
        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            submit(input);
          }}
        >
          <textarea
            ref={textareaRef}
            value={input}
            rows={1}
            placeholder={t.placeholder}
            aria-label={t.placeholder}
            disabled={loading}
            autoFocus
            onChange={(e) => {
              setInput(e.target.value);
              resizeInput();
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                submit(input);
              }
            }}
          />
          {loading ? (
            <button type="button" className="send stop" onClick={stop} aria-label={t.stop} title={t.stop}>
              <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
                <rect x="3.5" y="3.5" width="9" height="9" rx="1.5" fill="currentColor" />
              </svg>
            </button>
          ) : (
            <button type="submit" className="send" disabled={!input.trim()} aria-label={t.send} title={t.send}>
              <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
                <path d="M9 14V4M4.5 8.5 9 4l4.5 4.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          )}
        </form>
        <p className="disclaimer">{t.disclaimer}</p>
      </div>
    </div>
  );
}
