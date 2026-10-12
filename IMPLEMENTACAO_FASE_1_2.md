# Implementação das Fases 1 e 2 - Sistema de Logging do Pipeline

**Data de criação:** 2026-10-12  
**Status:** ✅ Concluído  

## Resumo

Implementadas as Fases 1 e 2 do PLANO_LOGS_PIPELINE.md, criando:
- **Fase 1 (Schema):** Migração Alembic com 3 tabelas de logging
- **Fase 2 (Tracking):** Camada de rastreamento reutilizável

## Fase 1: Schema (Migração Alembic)

### Arquivo Criado
- `backend/migrations/versions/0002_add_pipeline_logging.py`

### Tabelas Criadas

#### `pipeline_runs`
Rastreia cada execução de scrape, chunk, ou embed:
- `id, stage, status, started_at, finished_at, duration_ms`
- `params (JSONB)` - Ex: `{days: 90}`, `{model, batch_size}`
- `items_total, items_ok, items_failed` - Contadores
- Índice: `(stage, started_at DESC)`

#### `pipeline_events`
Logs granulares de falhas e eventos importantes:
- `id, run_id, level (info/warning/error)`
- `document_id, chunk_id` - Referências nullable
- `message, details (JSONB)`
- Índices: `(run_id)`, `(level)`

#### `query_logs`
Rastreamento completo de perguntas ao RAG:
- `question, answer` - Completos
- `retrieved (JSONB)` - Lista de chunks recuperados com scores
- `embedding_model, llm_model` - Modelos usados
- `tokens_in, tokens_out` - Consumo de tokens
- `latency_retrieval_ms, latency_llm_ms, latency_total_ms` - Tempos
- `status, error` - Resultado
- Índices: `(created_at DESC)`, `(status)`

### Como Executar a Migração

```bash
# 1. Inicie o Docker
docker compose up -d

# 2. Execute a migração dentro do container
docker compose exec api alembic upgrade head

# 3. Verifique a criação das tabelas
docker compose exec db psql -U postgresml postgresml -c "\dt pipeline_*"
```

## Fase 2: Camada de Tracking

### Arquivos Criados

#### `backend/app/observability/__init__.py`
Exporta as funções públicas:
```python
from .tracker import track_run, PipelineRun
from .logger import log_query
```

#### `backend/app/observability/tracker.py`
Context manager `track_run()` que:
- Cria registro com status `running`
- Entrega objeto `run` com métodos: `ok()`, `fail()`, `event()`
- No `__exit__`, calcula duração e define status final
- Falhas ao gravar log nunca derrubam o pipeline (try/except com fallback)

**Uso:**
```python
from sqlalchemy.orm import Session
from app.observability import track_run

with track_run(session, "scrape", {"days": 30}) as run:
    for document in documents:
        try:
            content = fetch_content(document)
            run.ok()
        except Exception as e:
            run.fail(document.id, e, {"url": document.url})
```

#### `backend/app/observability/logger.py`
Função `log_query()` que registra:
- Pergunta e resposta completas
- Chunks recuperados com scores
- Modelos usados
- Métricas de tokens e latência
- Status e erros

**Uso:**
```python
from app.observability import log_query

log_query(
    session,
    question="Como funciona o sistema de capital?",
    answer="...",
    retrieved=[{"chunk_id": 1, "score": 0.95}, ...],
    embedding_model="intfloat/multilingual-e5-base",
    llm_model="gpt-4",
    tokens_in=150,
    tokens_out=200,
    latency_retrieval_ms=250,
    latency_llm_ms=1500,
    latency_total_ms=1750,
)
```

## Fase 3: Integração (Próximo Passo)

Será necessário integrar o tracking nos workers:

### `backend/app/worker/scrape.py`
```python
from app.observability import track_run

with track_run(session, "scrape", {"days": days}) as run:
    for document in scraped:
        try:
            # salvar documento
            run.ok()
        except EmptyContentError as e:
            run.fail(document.url, e, {"source": document.source})
```

### `backend/app/worker/chunk.py`
```python
with track_run(session, "chunk", {"chunk_size": size}) as run:
    # processar e contar chunks criados
    run.ok(count=len(chunks))
```

### `backend/app/worker/embed.py`
```python
with track_run(session, "embed", {"model": model, "batch_size": batch_size}) as run:
    # processar em lotes
    run.ok(count=successful_embeds)
```

### Endpoint de perguntas
```python
@app.post("/api/query")
def query(q: str):
    latency_start = time.time()
    
    # Retrieval
    retrieval_start = time.time()
    retrieved = semantic_search(q)
    latency_retrieval_ms = int((time.time() - retrieval_start) * 1000)
    
    # LLM
    llm_start = time.time()
    answer = generate_answer(q, retrieved)
    latency_llm_ms = int((time.time() - llm_start) * 1000)
    
    # Log
    log_query(
        session,
        q,
        answer,
        retrieved,
        latency_retrieval_ms=latency_retrieval_ms,
        latency_llm_ms=latency_llm_ms,
        latency_total_ms=int((time.time() - latency_start) * 1000),
    )
    
    return {"answer": answer}
```

## Fase 4: Consulta e Visualização (Roadmap)

Será necessário criar:
- Endpoints API: `/api/admin/runs`, `/api/admin/runs/{id}/events`, `/api/admin/queries`
- Página "Logs" no frontend com abas de execuções e perguntas
- Atualizar `check_docs.py` para mostrar última execução de cada etapa

## Fase 5: Verificação (Roadmap)

- [ ] Testar scrape com track_run
- [ ] Testar chunk com track_run
- [ ] Testar embed com track_run
- [ ] Testar pergunta com log_query
- [ ] Forçar falhas e verificar registros
- [ ] Testes unitários
- [ ] Testar migration em banco limpo

## Verificação Rápida

Após executar a migração, verifique:

```bash
# 1. Verifique as tabelas
docker compose exec db psql -U postgresml postgresml << 'SQL'
\dt pipeline_*
SELECT COUNT(*) as total FROM pipeline_runs;
SELECT COUNT(*) as total FROM pipeline_events;
SELECT COUNT(*) as total FROM query_logs;
SQL

# 2. Verifique os índices
docker compose exec db psql -U postgresml postgresml -c "\di pipeline_*"

# 3. Teste a estrutura
docker compose exec db psql -U postgresml postgresml << 'SQL'
-- Insira um run de teste
INSERT INTO pipeline_runs (stage, status, params, items_total, items_ok)
VALUES ('test', 'ok', '{"test": true}', 1, 1);

-- Verifique
SELECT * FROM pipeline_runs ORDER BY id DESC LIMIT 1;
SQL
```

## Próximos Passos

1. **Imediato:** Executar a migração
2. **Curto prazo:** Integrar tracking em scrape.py (Fase 3)
3. **Médio prazo:** Adicionar endpoints e frontend (Fase 4)
4. **Verificação:** Testar cada etapa com dados reais

## Notas

- A camada de tracking nunca derruba o pipeline se falhar
- Estrutura é extensível para adicionar tracing (Langfuse, Phoenix) depois
- Logs são consultáveis por SQL e via API (quando endpoints forem criados)
