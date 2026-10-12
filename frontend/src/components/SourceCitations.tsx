import { useState } from 'react';
import type { SourceRef } from '../types';

interface SourceCitationsProps {
  sources: SourceRef[];
  retrievedChunks: number;
}

export function SourceCitations({ sources, retrievedChunks }: SourceCitationsProps) {
  const [expandedSources, setExpandedSources] = useState<Set<number>>(new Set());

  const toggleExpand = (index: number) => {
    const newExpanded = new Set(expandedSources);
    if (newExpanded.has(index)) {
      newExpanded.delete(index);
    } else {
      newExpanded.add(index);
    }
    setExpandedSources(newExpanded);
  };

  if (sources.length === 0) {
    return null;
  }

  return (
    <div className="sources-section">
      <h4>📚 Sources ({sources.length} of {retrievedChunks} chunks)</h4>
      <div className="sources-list">
        {sources.map((source, index) => (
          <div key={index} className="source-item">
            <div
              className="source-header"
              onClick={() => toggleExpand(index)}
              style={{ cursor: 'pointer' }}
            >
              <div className="source-title">
                <span className="source-badge">{index + 1}</span>
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="source-link"
                >
                  {source.title}
                </a>
              </div>
              <div className="source-meta">
                <span className="doc-type">{source.doc_type}</span>
                <span className="date">
                  {new Date(source.published_at).toLocaleDateString('pt-BR')}
                </span>
                <span className="expand-icon">
                  {expandedSources.has(index) ? '▼' : '▶'}
                </span>
              </div>
            </div>
            {expandedSources.has(index) && (
              <div className="source-content">
                <p className="chunk-text">{source.chunk_text}</p>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
