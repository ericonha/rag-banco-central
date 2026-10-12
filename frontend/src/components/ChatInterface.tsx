import { useEffect, useRef, useState } from 'react';
import { MessageList } from './MessageList';
import { ApiClient } from '../services/api';
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
  timestamp: new Date(m.created_at),
});

export function ChatInterface({ conversationId, language, onExchange }: ChatInterfaceProps) {
  const t = STRINGS[language];
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [error, setError] = useState<ChatError | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

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

  const submit = async (raw: string) => {
    const question = raw.trim();
    if (!question || loading) return;

    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: 'user', content: question, timestamp: new Date() },
    ]);
    setInput('');
    requestAnimationFrame(resizeInput);
    setLoading(true);
    setError(null);

    try {
      const response = await ApiClient.chat({
        question,
        language,
        conversation_id: conversationId,
      });
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: response.answer,
          sources: response.sources,
          retrieved_chunks: response.retrieved_chunks,
          timestamp: new Date(),
        },
      ]);
      onExchange();
    } catch (err) {
      setError({ kind: 'text', text: err instanceof Error ? err.message : String(err) });
    } finally {
      setLoading(false);
      textareaRef.current?.focus();
    }
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
          <MessageList messages={messages} loading={loading} language={language} />
          {error && (
            <div className="notice" role="alert">
              {error.kind === 'connect' ? t.connectError : error.text}
            </div>
          )}
        </div>
      </div>

      <div className="composer-wrap">
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
          <button type="submit" className="send" disabled={loading || !input.trim()} aria-label={t.send} title={t.send}>
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
              <path d="M9 14V4M4.5 8.5 9 4l4.5 4.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </form>
        <p className="disclaimer">{t.disclaimer}</p>
      </div>
    </div>
  );
}
