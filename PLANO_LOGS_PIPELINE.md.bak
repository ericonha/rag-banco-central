# Plano: logs de pipeline no Postgres

Objetivo: registrar metadados de cada execução de scrape, chunk, embed e de cada pergunta feita ao RAG, em tabelas consultáveis por SQL, API e frontend.

> Os nomes de colunas são propostas. Ainda não foram conferidos contra `models.py` e o `ingest_runs` atual; ajustar na Fase 1.

## Fase 0: Decisões
- **Estender `ingest_runs` ou criar `pipeline_runs`?** Recomendado: criar `pipeline_runs` e migrar o `ingest_runs` para ela (scrape, chunk, embed e query têm o mesmo formato). Se o `ingest_runs` tiver poucos campos, basta renomear.
- **Escopo do log de perguntas:** salvar pergunta e resposta completas ou só hash e metadados? Para projeto de portfólio, completas.

## Fase 1: Schema (migration Alembic)

### `pipeline_runs`
| Coluna | Descrição |
|---|---|
| `id` | PK |
| `stage` | `scrape` / `chunk` / `embed` |
| `status` | `running` / `ok` / `done_with_errors` / `failed` |
| `started_at`, `finished_at`, `duration_ms` | Tempos |
| `params` (JSONB) | Ex.: `{days: 90, source: "bcb_resolucoes"}` ou `{model, batch_size}` |
| `items_total`, `items_ok`, `items_failed` | Contadores |
| `error` | Erro fatal, se houver |

### `pipeline_events`
Um registro por falha ou item relevante. É onde entram os "Empty conteudo" de forma consultável.

| Coluna | Descrição |
|---|---|
| `id` | PK |
| `run_id` | FK para `pipeline_runs` |
| `level` | `info` / `warning` / `error` |
| `document_id`, `chunk_id` | Nullable |
| `message` | Texto curto |
| `details` (JSONB) | URL, stack trace, resposta da API etc. |
| `created_at` | Timestamp |

### `query_logs`
| Coluna | Descrição |
|---|---|
| `id`, `created_at` | PK e timestamp |
| `question`, `answer` | Texto completo |
| `retrieved` (JSONB) | Lista de `{chunk_id, document_id, score}` |
| `top_k` | Parâmetro de busca |
| `embedding_model`, `llm_model` | Modelos usados |
| `tokens_in`, `tokens_out` | Consumo do LLM |
| `latency_retrieval_ms`, `latency_llm_ms`, `latency_total_ms` | Latências por etapa |
| `status`, `error` | Resultado |

### Índices
- `pipeline_runs (stage, started_at DESC)`
- `pipeline_events (run_id)`
- `query_logs (created_at DESC)`

## Fase 2: Camada de tracking (`app/observability/`)
1. **`track_run(stage, params)`**: context manager que
   - cria o run com status `running`;
   - entrega um objeto `run` com `run.ok()`, `run.fail(item, exc)` e `run.event(level, msg, **details)`;
   - no `__exit__`, calcula a duração e define o status (`ok`; `done_with_errors` se houve falhas; `failed` se a exceção escapou) e fecha o registro, inclusive com Ctrl+C.
2. **`log_query(...)`**: mede as latências por etapa e grava em `query_logs`.
3. **structlog em JSON no stdout**, com `run_id` no contexto, para correlacionar `docker logs` com o banco.
4. **Regra:** falha ao gravar log nunca derruba o pipeline (try/except com fallback para stdout).

## Fase 3: Integração
1. `worker/scrape.py`: trocar o registro manual de `ingest_runs` por `track_run("scrape", {...})`; cada "Empty conteudo" vira `run.fail(url, exc)`.
2. `worker/chunk.py`: `track_run("chunk", {chunk_size, overlap})`.
3. `worker/embed.py`: `track_run("embed", {model, batch_size})`.
4. Endpoint de perguntas: medir recuperação e chamada ao LLM separadamente e chamar `log_query` no final, inclusive em caso de erro.

## Fase 4: Consulta e visualização
1. Endpoints `GET /api/admin/runs`, `GET /api/admin/runs/{id}/events` e `GET /api/admin/queries` (com paginação).
2. Página "Logs" no frontend com duas abas: execuções do pipeline e perguntas.
3. Atualizar o `check_docs.py` para mostrar também a última execução de cada etapa.

## Fase 5: Verificação
1. Rodar scrape, chunk, embed e uma pergunta; conferir que cada um gerou registro.
2. Forçar falhas (URL inválida, API key errada); conferir status `failed` e o evento.
3. Testes unitários do `track_run`: caso ok, com falhas parciais e com exceção.
4. Rodar a migration em banco limpo e sobre o banco atual.

## Ordem sugerida
Fase 1, 2, 3 (scrape primeiro, que já tem erros reais), integração da pergunta, e por fim a Fase 4. As fases 1 a 3 já entregam o valor principal.

## Evolução futura
Se quiser uma UI de traces, dá para adicionar Langfuse ou Arize Phoenix (self-hosted no docker-compose) sem descartar estas tabelas.
