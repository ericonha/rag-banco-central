import { useCallback, useEffect, useState } from 'react';
import { ApiClient } from '../services/api';
import type { DocumentsDashboard } from '../types/admin';
import './Logs.css';
import './Documents.css';

const PAGE = 25;
const REFRESH_MS = 5000;

const fmtDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : '—';

export function Documents() {
  const [data, setData] = useState<DocumentsDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [docType, setDocType] = useState('');
  const [page, setPage] = useState(0);

  const load = useCallback(() => {
    ApiClient.getDocumentsDashboard({
      q: query,
      doc_type: docType,
      limit: PAGE,
      offset: page * PAGE,
    })
      .then((d) => {
        setData(d);
        setError(null);
        setUpdatedAt(new Date());
      })
      .catch((e: Error) => setError(e.message));
  }, [query, docType, page]);

  useEffect(load, [load]);
  useEffect(() => {
    if (!live) return;
    const id = window.setInterval(load, REFRESH_MS);
    return () => window.clearInterval(id);
  }, [live, load]);

  // Debounce the search box.
  useEffect(() => {
    const id = window.setTimeout(() => {
      setQuery(search);
      setPage(0);
    }, 300);
    return () => window.clearTimeout(id);
  }, [search]);

  const s = data?.summary;
  const pct = s && s.chunks > 0 ? Math.round((s.embedded / s.chunks) * 100) : 0;
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE)) : 1;

  return (
    <div className="logs-page">
      <div className="live-bar">
        <span className={`live-dot${live && !error ? ' on' : ''}`} aria-hidden="true" />
        <span>
          {live ? 'Ao vivo' : 'Pausado'}
          {updatedAt && ` · atualizado às ${updatedAt.toLocaleTimeString('pt-BR')}`}
        </span>
        <button type="button" className="link-btn" onClick={() => setLive((v) => !v)}>
          {live ? 'Pausar' : 'Retomar'}
        </button>
      </div>

      {error && <div className="error-box">{error}</div>}

      <div className="stat-grid">
        <div className="stat-card">
          <div className="stat-label">Documentos</div>
          <div className="stat-value">{s?.documents ?? '—'}</div>
          <div className="stat-hint">{s ? `${s.without_chunks} sem trechos` : ''}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Trechos (chunks)</div>
          <div className="stat-value">{s?.chunks ?? '—'}</div>
          <div className="stat-hint">{s ? `${s.chunks - s.embedded} aguardando embedding` : ''}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Vetorizados</div>
          <div className="stat-value">{s ? `${pct}%` : '—'}</div>
          <div className="stat-hint">{s ? `${s.embedded} de ${s.chunks}` : ''}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Última coleta</div>
          <div className="stat-value stat-value-sm">{fmtDate(s?.last_fetched_at ?? null)}</div>
        </div>
      </div>

      {data && data.types.length > 0 && (
        <div className="type-bars" aria-label="Documentos por tipo">
          {data.types.map((t) => (
            <button
              type="button"
              key={t.doc_type}
              className={`type-chip${docType === t.doc_type ? ' active' : ''}`}
              onClick={() => {
                setDocType(docType === t.doc_type ? '' : t.doc_type);
                setPage(0);
              }}
            >
              {t.doc_type} <strong>{t.count}</strong>
            </button>
          ))}
        </div>
      )}

      <div className="filters">
        <input
          type="search"
          className="doc-search"
          placeholder="Buscar por título ou URL"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <table className="logs-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Título</th>
            <th>Tipo</th>
            <th>Publicado</th>
            <th>Coletado</th>
            <th>Vetorização</th>
          </tr>
        </thead>
        <tbody>
          {data?.items.length === 0 && (
            <tr>
              <td colSpan={6} className="muted center">
                Nenhum documento encontrado.
              </td>
            </tr>
          )}
          {data?.items.map((d) => {
            const done = d.chunks > 0 && d.embedded === d.chunks;
            return (
              <tr key={d.id}>
                <td>{d.id}</td>
                <td className="question-cell" title={d.title ?? d.url}>
                  <a href={d.url} target="_blank" rel="noreferrer">
                    {d.title || d.url}
                  </a>
                </td>
                <td>{d.doc_type || '—'}</td>
                <td>{fmtDate(d.published_at)}</td>
                <td>{fmtDate(d.fetched_at)}</td>
                <td>
                  {d.chunks === 0 ? (
                    <span className="badge badge-warning">sem trechos</span>
                  ) : (
                    <span className="embed-cell">
                      <span className="meter" aria-hidden="true">
                        <span style={{ width: `${(d.embedded / d.chunks) * 100}%` }} />
                      </span>
                      <span className={done ? '' : 'muted'}>
                        {d.embedded}/{d.chunks}
                      </span>
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="pager">
        <span>{data ? `${data.total} documentos` : ''}</span>
        <span>
          <button type="button" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
            ←
          </button>
          <span className="pager-page">
            {page + 1} / {pages}
          </span>
          <button type="button" disabled={page + 1 >= pages} onClick={() => setPage((p) => p + 1)}>
            →
          </button>
        </span>
      </div>
    </div>
  );
}
