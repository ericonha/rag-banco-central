import { useEffect, useRef, useState } from 'react';
import type { GroundingFlag, Language, Message } from '../types';
import { STRINGS } from '../i18n';
import { SourceCitations } from './SourceCitations';
import { renderMarkdown } from './Markdown';
import type { CiteHandler } from './Markdown';

interface MessageListProps {
  messages: Message[];
  loading: boolean;
  language: Language;
  onFeedback?: (message: Message, value: 1 | -1) => void;
  onComment?: (message: Message, comment: string) => void;
  /** Regenerate the last answer (shown on the last assistant message only). */
  onRegenerate?: () => void;
}

function describeFlag(flag: GroundingFlag, t: (typeof STRINGS)[Language]): string {
  const label =
    flag.type === 'invalid_citation'
      ? t.flagInvalidCitation
      : flag.type === 'unsupported_number'
        ? t.flagNumber
        : flag.type === 'no_citations'
          ? t.flagNoCitations
          : t.flagLowSupport;
  const sentence = typeof flag['sentence'] === 'string' ? (flag['sentence'] as string) : '';
  return sentence && flag.type !== 'no_citations' ? `${label}: “${sentence}”` : label;
}

export function MessageList({ messages, loading, language, onFeedback, onComment, onRegenerate }: MessageListProps) {
  const t = STRINGS[language];
  const [commentFor, setCommentFor] = useState<string | null>(null);
  const [commentText, setCommentText] = useState('');
  const lastAssistantId = [...messages].reverse().find((m) => m.role === 'assistant')?.id;
  const endRef = useRef<HTMLDivElement>(null);
  const [focus, setFocus] = useState<{ messageId: string; index: number; tick: number } | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, loading]);

  const cite = (messageId: string): CiteHandler => (n) =>
    setFocus((prev) => ({ messageId, index: n - 1, tick: (prev?.tick ?? 0) + 1 }));

  return (
    <div className="turns">
      {messages.map((message) =>
        message.role === 'user' ? (
          <div key={message.id} className="turn turn-user">
            <div className="bubble">{message.content}</div>
          </div>
        ) : (
          <article key={message.id} className="turn turn-assistant">
            <div className="answer">{renderMarkdown(message.content, cite(message.id), t.sourceWord)}</div>
            {message.sources && message.sources.length > 0 && (
              <SourceCitations
                sources={message.sources}
                retrievedChunks={message.retrieved_chunks}
                language={language}
                focus={
                  focus && focus.messageId === message.id
                    ? { index: focus.index, tick: focus.tick }
                    : undefined
                }
              />
            )}
            {message.grounding && !message.grounding.ok && (
              <div className="grounding-warn" role="note">
                <span aria-hidden="true">⚠</span> {t.groundingWarn}
                <ul>
                  {message.grounding.flags.slice(0, 4).map((f, i) => (
                    <li key={i}>{describeFlag(f, t)}</li>
                  ))}
                </ul>
              </div>
            )}
            {message.dbId && onFeedback && (
              <div className="feedback" role="group" aria-label={t.feedbackLabel}>
                <button
                  type="button"
                  className={message.feedback === 1 ? 'on' : ''}
                  aria-pressed={message.feedback === 1}
                  title={t.helpful}
                  aria-label={t.helpful}
                  onClick={() => onFeedback(message, 1)}
                >
                  👍
                </button>
                <button
                  type="button"
                  className={message.feedback === -1 ? 'on' : ''}
                  aria-pressed={message.feedback === -1}
                  title={t.notHelpful}
                  aria-label={t.notHelpful}
                  onClick={() => {
                    onFeedback(message, -1);
                    // opening the comment box only when the vote is being set, not cleared
                    setCommentFor(message.feedback === -1 ? null : message.id);
                    setCommentText('');
                  }}
                >
                  👎
                </button>
                {onRegenerate && message.id === lastAssistantId && !loading && (
                  <button type="button" className="regen" title={t.regenerate} aria-label={t.regenerate} onClick={onRegenerate}>
                    ↻ {t.regenerate}
                  </button>
                )}
              </div>
            )}
            {commentFor === message.id && message.feedback === -1 && onComment && (
              <form
                className="feedback-comment"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (commentText.trim()) onComment(message, commentText.trim());
                  setCommentFor(null);
                }}
              >
                <input
                  value={commentText}
                  maxLength={1000}
                  autoFocus
                  placeholder={t.feedbackWhy}
                  aria-label={t.feedbackWhy}
                  onChange={(e) => setCommentText(e.target.value)}
                />
                <button type="submit" disabled={!commentText.trim()}>
                  {t.feedbackSend}
                </button>
                <button type="button" onClick={() => setCommentFor(null)}>
                  {t.feedbackSkip}
                </button>
              </form>
            )}
          </article>
        ),
      )}
      {loading && (
        <div className="turn turn-assistant" role="status" aria-label="…">
          <div className="typing">
            <span />
            <span />
            <span />
          </div>
        </div>
      )}
      <div ref={endRef} />
    </div>
  );
}
