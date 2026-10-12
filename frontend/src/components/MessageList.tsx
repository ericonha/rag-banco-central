import { Fragment, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import type { Language, Message } from '../types';
import { STRINGS } from '../i18n';
import { SourceCitations } from './SourceCitations';

interface MessageListProps {
  messages: Message[];
  loading: boolean;
  language: Language;
}

type CiteHandler = (n: number) => void;

const INLINE_RE = /(\*\*[^*]+\*\*|\[\d+(?:\s*,\s*\d+)*\])/g;
const CITE_RE = /^\[(\d+(?:\s*,\s*\d+)*)\]$/;

/** **bold** and [n] citation markers → React nodes. */
function renderInline(text: string, onCite: CiteHandler, sourceWord: string): ReactNode[] {
  return text
    .split(INLINE_RE)
    .filter(Boolean)
    .map((part, i) => {
      if (part.length > 4 && part.startsWith('**') && part.endsWith('**')) {
        return <strong key={i}>{part.slice(2, -2)}</strong>;
      }
      const cite = part.match(CITE_RE);
      if (cite) {
        return (
          <span className="cites" key={i}>
            {cite[1].split(',').map((s) => {
              const n = Number(s.trim());
              return (
                <button
                  key={n}
                  type="button"
                  className="cite"
                  aria-label={`${sourceWord} ${n}`}
                  onClick={() => onCite(n)}
                >
                  {n}
                </button>
              );
            })}
          </span>
        );
      }
      return part;
    });
}

/** Small block renderer: paragraphs, bullet/numbered lists and #-headings. */
function renderAnswer(content: string, onCite: CiteHandler, sourceWord: string): ReactNode[] {
  const inline = (s: string) => renderInline(s, onCite, sourceWord);
  return content
    .trim()
    .split(/\n{2,}/)
    .map((block, bi) => {
      const lines = block.split('\n');
      if (lines.every((l) => /^\s*[-*•]\s+/.test(l))) {
        return (
          <ul key={bi}>
            {lines.map((l, li) => (
              <li key={li}>{inline(l.replace(/^\s*[-*•]\s+/, ''))}</li>
            ))}
          </ul>
        );
      }
      if (lines.every((l) => /^\s*\d+[.)]\s+/.test(l))) {
        return (
          <ol key={bi}>
            {lines.map((l, li) => (
              <li key={li}>{inline(l.replace(/^\s*\d+[.)]\s+/, ''))}</li>
            ))}
          </ol>
        );
      }
      const heading = lines.length === 1 ? block.match(/^#{1,4}\s+(.*)$/) : null;
      if (heading) return <h4 key={bi}>{inline(heading[1])}</h4>;
      return (
        <p key={bi}>
          {lines.map((l, li) => (
            <Fragment key={li}>
              {li > 0 && <br />}
              {inline(l)}
            </Fragment>
          ))}
        </p>
      );
    });
}

export function MessageList({ messages, loading, language }: MessageListProps) {
  const t = STRINGS[language];
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
            <div className="answer">{renderAnswer(message.content, cite(message.id), t.sourceWord)}</div>
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
