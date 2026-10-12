import { useEffect, useRef, useState } from 'react';
import type { Language, SourceRef } from '../types';
import { STRINGS } from '../i18n';

export interface CitationFocus {
  index: number;
  tick: number;
}

interface SourceCitationsProps {
  sources: SourceRef[];
  retrievedChunks?: number;
  language: Language;
  /** Set when the reader clicks a [n] marker in the answer. */
  focus?: CitationFocus;
}

export function SourceCitations({ sources, retrievedChunks, language, focus }: SourceCitationsProps) {
  const t = STRINGS[language];
  const [open, setOpen] = useState<Set<number>>(new Set());
  const [flash, setFlash] = useState<number | null>(null);
  const itemRefs = useRef<(HTMLLIElement | null)[]>([]);

  useEffect(() => {
    if (!focus || focus.index < 0 || focus.index >= sources.length) return;
    const index = focus.index;
    setOpen((prev) => new Set(prev).add(index));
    setFlash(index);
    itemRefs.current[index]?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    const timer = window.setTimeout(() => setFlash(null), 1400);
    return () => window.clearTimeout(timer);
  }, [focus?.tick]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = (index: number) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });

  if (sources.length === 0) return null;

  return (
    <section className="sources" aria-label={t.sources}>
      <h4 className="sources-title">
        {t.sources}
        {retrievedChunks ? <span className="sources-count">{retrievedChunks} {t.chunks}</span> : null}
      </h4>
      <ol className="source-list">
        {sources.map((source, index) => {
          const isOpen = open.has(index);
          return (
            <li
              key={index}
              ref={(el) => {
                itemRefs.current[index] = el;
              }}
              className={`source${flash === index ? ' flash' : ''}`}
            >
              <button
                type="button"
                className="source-head"
                aria-expanded={isOpen}
                onClick={() => toggle(index)}
              >
                <span className="source-num">{index + 1}</span>
                <span className="source-main">
                  <span className="source-name">{source.title}</span>
                  <span className="source-meta">
                    {source.doc_type} · {new Date(source.published_at).toLocaleDateString('pt-BR')}
                  </span>
                </span>
                <svg className={`chevron${isOpen ? ' open' : ''}`} width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
                  <path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
              {isOpen && (
                <div className="source-body">
                  <p className="source-excerpt">{source.chunk_text}</p>
                  <a href={source.url} target="_blank" rel="noopener noreferrer" className="source-link">
                    {source.url}
                  </a>
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
