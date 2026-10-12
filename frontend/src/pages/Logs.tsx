/**
 * Logs page: pipeline execution history and RAG query history.
 * Plain React + CSS (no UI library), data from /api/admin/*.
 */
import { useEffect, useState } from 'react';
import { ApiClient } from '../services/api';
import type {
  Paginated,
  PipelineEvent,
  PipelineRun,
  PipelineStats,
  QueryLog,
  QueryStats,
} from '../types/admin';
import './Logs.css';

const PAGE_SIZE = 15;

// ---------------------------------------------------------------- helpers

const fmtDate = (iso?: string | null): string =>
  iso ? new Date(iso).toLocaleString('pt-BR') : '—';

const fmtMs = (ms?: number | null): string => {
  if (ms == null) return '—';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)} s`;
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
};

const fmtNum = (n?: number | null): string =>
  n == null ? '—' : Math.round(n).toLocaleString('pt-BR');

const errMsg = (e: unknown): string => (e instanceof Error ? e.message : String(e));

function StatusBadge({ status }: { status: string }) {
  return <span className={`badge badge-${status}`}>{status.replace(/_/g, ' ')}</span>;
}

function Pager(props: { page: number; totalPages: number; total: number; onPage: (p: number) => void }) {
  const { page, totalPages, total, onPage } = props;
  return (
    <div className="pager">
      <span>{total} registros</span>
      <div>
        <button disabled={page <= 1} onClick={() => onPage(page - 1)}>
          ‹ Anterior
        </button>
        <span className="pager-page">
          {page} / {Math.max(totalPages, 1)}
        </span>
        <button disabled={page >= totalPages} onClick={() => onPage(page + 1)}>
          Próxima ›
        </button>
      </div>
    </div>
  );
}

function StatCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

// ---------------------------------------------------------- pipeline runs

function RunsTab() {
  const [stage, setStage] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [tick, setTick] = useState(0);
  const [data, setData] = useState<Paginated<PipelineRun> | null>(null);
  const [stats, setStats] = useState<PipelineStats[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [openRun, setOpenRun] = useState<number | null>(null);
  const [events, setEvents] = useState<Record<number, PipelineEvent[]>>({});

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      ApiClient.getPipelineRuns({ stage, status, page, page_size: PAGE_SIZE }),
      ApiClient.getPipelineStats(),
    ])
      .then(([runs, st]) => {
        if (cancelled) return;
        setData(runs);
        setStats(st);
        setError(null);
      })
      .catch((e) => !cancelled && setError(errMsg(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [stage, status, page, tick]);

  const toggleEvents = async (runId: number) => {
    if (openRun === runId) {
      setOpenRun(null);
      return;
    }
    setOpenRun(runId);
    if (!events[runId]) {
      try {
        const ev = await ApiClient.getRunEvents(runId);
        setEvents((prev) => ({ ...prev, [runId]: ev }));
      } catch (e) {
        setError(errMsg(e));
      }
    }
  };

  return (
    <div>
      <div className="stat-grid">
        {stats.length === 0 && !loading && <p className="muted">Nenhuma execução registrada ainda.</p>}
        {stats.map((s) => (
          <div className="stat-card" key={s.stage}>
            <div className="stat-label">{s.stage}</div>
            <div className="stat-value">{s.total_runs} execuções</div>
            <div className="stat-hint">
              {s.successful_runs} ok · {s.failed_runs} falhas · média {fmtMs(s.avg_duration_ms)}
            </div>
            <div className="stat-hint">
              {fmtNum(s.total_items_processed)} itens ({fmtNum(s.total_items_failed)} com erro)
            </div>
            <div className="stat-hint">
              última: {fmtDate(s.last_run_at)} {s.last_run_status && <StatusBadge status={s.last_run_status} />}
            </div>
          </div>
        ))}
      </div>

      <div className="filters">
        <select value={stage} onChange={(e) => { setStage(e.target.value); setPage(1); }}>
          <option value="">Todas as etapas</option>
          <option value="scrape">scrape</option>
          <option value="chunk">chunk</option>
          <option value="embed">embed</option>
        </select>
        <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">Todos os status</option>
          <option value="running">running</option>
          <option value="ok">ok</option>
          <option value="done_with_errors">done with errors</option>
          <option value="failed">failed</option>
        </select>
        <button onClick={() => setTick((t) => t + 1)}>Atualizar</button>
      </div>

      {error && <div className="error-box">{error}</div>}
      {loading && !data && <p className="muted">Carregando…</p>}

      {data && (
        <>
          <table className="logs-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Etapa</th>
                <th>Status</th>
                <th>Início</th>
                <th>Duração</th>
                <th>Itens (ok / erro)</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.items.length === 0 && (
                <tr>
                  <td colSpan={7} className="muted center">Nenhuma execução encontrada.</td>
                </tr>
              )}
              {data.items.map((run) => (
                <RunRows
                  key={run.id}
                  run={run}
                  open={openRun === run.id}
                  events={events[run.id]}
                  onToggle={() => toggleEvents(run.id)}
                />
              ))}
            </tbody>
          </table>
          <Pager page={data.page} totalPages={data.total_pages} total={data.total} onPage={setPage} />
        </>
      )}
    </div>
  );
}

function RunRows(props: {
  run: PipelineRun;
  open: boolean;
  events?: PipelineEvent[];
  onToggle: () => void;
}) {
  const { run, open, events, onToggle } = props;
  return (
    <>
      <tr>
        <td>{run.id}</td>
        <td>{run.stage}</td>
        <td><StatusBadge status={run.status} /></td>
        <td>{fmtDate(run.started_at)}</td>
        <td>{fmtMs(run.duration_ms)}</td>
        <td>
          {run.items_ok} / <span className={run.items_failed ? 'text-bad' : ''}>{run.items_failed}</span>
        </td>
        <td>
          <button className="link-btn" onClick={onToggle}>{open ? 'Ocultar' : 'Eventos'}</button>
        </td>
      </tr>
      {open && (
        <tr className="detail-row">
          <td colSpan={7}>
            {run.params && <div className="detail-line"><b>Parâmetros:</b> <code>{JSON.stringify(run.params)}</code></div>}
            {run.error && <div className="detail-line text-bad"><b>Erro:</b> {run.error}</div>}
            {!events && <span className="muted">Carregando eventos…</span>}
            {events && events.length === 0 && <span className="muted">Sem eventos registrados.</span>}
            {events && events.length > 0 && (
              <ul className="event-list">
                {events.map((ev) => (
                  <li key={ev.id}>
                    <span className={`badge badge-${ev.level}`}>{ev.level}</span> {fmtDate(ev.created_at)} — {ev.message}
                    {ev.details && <code>{JSON.stringify(ev.details)}</code>}
                  </li>
                ))}
              </ul>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

// ------------------------------------------------------------- query logs

function QueriesTab() {
  const [hours, setHours] = useState(24);
  const [page, setPage] = useState(1);
  const [tick, setTick] = useState(0);
  const [data, setData] = useState<Paginated<QueryLog> | null>(null);
  const [stats, setStats] = useState<QueryStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [openId, setOpenId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      ApiClient.getQueryLogs({ hours, page, page_size: PAGE_SIZE }),
      ApiClient.getQueryStats(),
    ])
      .then(([q, st]) => {
        if (cancelled) return;
        setData(q);
        setStats(st);
        setError(null);
      })
      .catch((e) => !cancelled && setError(errMsg(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [hours, page, tick]);

  const successRate =
    stats && stats.total_queries > 0
      ? `${((stats.successful_queries / stats.total_queries) * 100).toFixed(1)}%`
      : '—';

  return (
    <div>
      {stats && (
        <div className="stat-grid">
          <StatCard label="Consultas" value={fmtNum(stats.total_queries)} hint={`${stats.queries_last_24h} nas últimas 24h`} />
          <StatCard label="Taxa de sucesso" value={successRate} hint={`${stats.failed_queries} com erro`} />
          <StatCard
            label="Latência média"
            value={fmtMs(stats.avg_latency_total_ms)}
            hint={`busca ${fmtMs(stats.avg_latency_retrieval_ms)} · LLM ${fmtMs(stats.avg_latency_llm_ms)}`}
          />
          <StatCard
            label="Tokens (média)"
            value={stats.avg_tokens_in || stats.avg_tokens_out ? `${fmtNum(stats.avg_tokens_in)} / ${fmtNum(stats.avg_tokens_out)}` : '—'}
            hint="entrada / saída"
          />
        </div>
      )}

      <div className="filters">
        <select value={hours} onChange={(e) => { setHours(Number(e.target.value)); setPage(1); }}>
          <option value={1}>Última hora</option>
          <option value={6}>Últimas 6 horas</option>
          <option value={24}>Últimas 24 horas</option>
          <option value={168}>Últimos 7 dias</option>
        </select>
        <button onClick={() => setTick((t) => t + 1)}>Atualizar</button>
      </div>

      {error && <div className="error-box">{error}</div>}
      {loading && !data && <p className="muted">Carregando…</p>}

      {data && (
        <>
          <table className="logs-table">
            <thead>
              <tr>
                <th>Quando</th>
                <th>Pergunta</th>
                <th>Status</th>
                <th>Chunks</th>
                <th>Latência</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.items.length === 0 && (
                <tr>
                  <td colSpan={6} className="muted center">Nenhuma consulta no período.</td>
                </tr>
              )}
              {data.items.map((q) => (
                <QueryRows key={q.id} q={q} open={openId === q.id} onToggle={() => setOpenId(openId === q.id ? null : q.id)} />
              ))}
            </tbody>
          </table>
          <Pager page={data.page} totalPages={data.total_pages} total={data.total} onPage={setPage} />
        </>
      )}
    </div>
  );
}

function QueryRows(props: { q: QueryLog; open: boolean; onToggle: () => void }) {
  const { q, open, onToggle } = props;
  return (
    <>
      <tr>
        <td>{fmtDate(q.created_at)}</td>
        <td className="question-cell" title={q.question}>{q.question}</td>
        <td><StatusBadge status={q.status} /></td>
        <td>{q.retrieved?.length ?? 0}</td>
        <td>{fmtMs(q.latency_total_ms)}</td>
        <td>
          <button className="link-btn" onClick={onToggle}>{open ? 'Ocultar' : 'Detalhes'}</button>
        </td>
      </tr>
      {open && (
        <tr className="detail-row">
          <td colSpan={6}>
            <div className="detail-line"><b>Pergunta:</b> {q.question}</div>
            {q.answer && <div className="detail-line"><b>Resposta:</b> {q.answer}</div>}
            {q.error && <div className="detail-line text-bad"><b>Erro:</b> {q.error}</div>}
            <div className="detail-line">
              <b>Modelos:</b> {q.embedding_model ?? '—'} · {q.llm_model ?? '—'} &nbsp;|&nbsp;
              <b>Busca:</b> {fmtMs(q.latency_retrieval_ms)} · <b>LLM:</b> {fmtMs(q.latency_llm_ms)}
            </div>
            {q.retrieved && q.retrieved.length > 0 && (
              <div className="detail-line">
                <b>Chunks recuperados:</b>{' '}
                {q.retrieved.map((r) => `#${r.chunk_id} (doc ${r.document_id}, ${r.score.toFixed(3)})`).join(' · ')}
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

// ------------------------------------------------------------------- page

const EXPORT_PAGE = 100;

/** Fetch every page of a paginated endpoint. */
async function fetchAll<T>(load: (page: number) => Promise<Paginated<T>>): Promise<T[]> {
  const first = await load(1);
  const items = [...first.items];
  for (let p = 2; p <= first.total_pages; p++) items.push(...(await load(p)).items);
  return items;
}

function downloadJson(name: string, payload: unknown): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${name}-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

export function Logs() {
  const [tab, setTab] = useState<'runs' | 'queries'>('runs');
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const exportJson = async () => {
    setExporting(true);
    setExportError(null);
    try {
      if (tab === 'runs') {
        const runs = await fetchAll((page) => ApiClient.getPipelineRuns({ page, page_size: EXPORT_PAGE }));
        const withEvents = await Promise.all(
          runs.map(async (r) => ({ ...r, events: await ApiClient.getRunEvents(r.id).catch(() => []) })),
        );
        downloadJson('pipeline-runs', withEvents);
      } else {
        const queries = await fetchAll((page) =>
          ApiClient.getQueryLogs({ hours: 24 * 365, page, page_size: EXPORT_PAGE }),
        );
        downloadJson('query-logs', queries);
      }
    } catch (e) {
      setExportError(e instanceof Error ? e.message : String(e));
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="logs-page">
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === 'runs'} className={tab === 'runs' ? 'active' : ''} onClick={() => setTab('runs')}>
          Execuções
        </button>
        <button role="tab" aria-selected={tab === 'queries'} className={tab === 'queries' ? 'active' : ''} onClick={() => setTab('queries')}>
          Consultas
        </button>
        <button type="button" className="export-btn" disabled={exporting} onClick={exportJson}>
          {exporting ? 'Exportando…' : 'Exportar JSON'}
        </button>
      </div>
      {exportError && <div className="error-box">{exportError}</div>}
      <div className="logs-body">{tab === 'runs' ? <RunsTab /> : <QueriesTab />}</div>
    </div>
  );
}
