# Implementação da Fase 3 - Integração nos Workers

**Data:** 2026-10-12  
**Status:** ✅ Concluído  

## Resumo

Integrado o sistema de tracking nas três etapas do pipeline:
- `scrape.py` - Com tracking de documentos novos e falhas
- `chunk.py` - Com rastreamento de chunks criados
- `embed.py` - Com tracking de embeddings gerados

## O Que Mudou

### 1. Novo Módulo: `async_tracker.py`

Criado em `backend/app/observability/async_tracker.py`:
- Context manager `track_run()` para asyncpg (não SQLAlchemy)
- Classe `AsyncPipelineRun` com métodos `ok()`, `fail()`, `event()`
- Funciona com as conexões asyncpg existentes do projeto

**Características:**
- Registra início com status `running`
- Calcula duração automaticamente
- Define status final baseado em erros (ok / done_with_errors)
- Nunca derruba o pipeline se falhar

### 2. Integração em `scrape.py`

**Antes:**
```python
# Escrita manual para ingest_runs
run_row = await conn.execute("INSERT INTO ingest_runs ...")
# ... processamento ...
await conn.execute("UPDATE ingest_runs SET ...")
```

**Depois:**
```python
from app.observability.async_tracker import track_run

async with track_run(conn, "scrape", {"days": days}) as run:
    for document in scraped:
        try:
            doc_id = await save_document(document)
            await run.ok()  # Incrementa contador
            logger.info("NEW [%d] %s", doc_id, document.title)
        except Exception as e:
            await run.fail(document.url, e, {"source": source_name})
```

**Resultado:**
- ✅ Cada documento novo → `run.ok()`
- ✅ Cada falha → `run.fail(url, exception, details)`
- ✅ Automaticamente gera registro em `pipeline_runs`
- ✅ Cria eventos em `pipeline_events` para cada erro
- ✅ Mantém compatibilidade com `ingest_runs` (escrita dual)

### 3. Integração em `chunk.py`

**Antes:**
```python
# Contagem manual
total_chunks = 0
for doc in docs:
    chunks = chunker.chunk(doc["raw_text"])
    total_chunks += len(chunks)
```

**Depois:**
```python
async with track_run(conn, "chunk", {"chunk_size": 512}) as run:
    for doc in docs:
        chunks = chunker.chunk(doc["raw_text"])
        await insert_chunks(conn, doc["id"], chunks)
        await run.ok(count=len(chunks))  # Registra total de chunks
```

**Resultado:**
- ✅ Conta total de chunks criados
- ✅ Registra erros por documento
- ✅ Gera duração da etapa de chunking

### 4. Integração em `embed.py`

**Antes:**
```python
total_embedded = 0
for batch in batches:
    result = await embed_batch(batch)
    total_embedded += len(result)
```

**Depois:**
```python
async with track_run(conn, "embed", {"model": model, "batch_size": batch_size}) as run:
    batch_num = 0
    while True:
        chunks = await get_chunks_needing_embedding(conn, batch_size)
        if not chunks:
            break
        result = await embed_batch(chunks)
        await run.ok(count=len(result))  # Conta embeddings
```

**Resultado:**
- ✅ Rastreia embeddings por lote
- ✅ Registra modelo usado
- ✅ Gera tempo total de embedding

## Estrutura de Dados Registrada

### `pipeline_runs` (criado pelo context manager)
```json
{
  "id": 42,
  "stage": "scrape",
  "status": "ok",
  "started_at": "2026-10-12T14:35:00Z",
  "finished_at": "2026-10-12T14:45:00Z",
  "duration_ms": 600000,
  "params": {"days": 30},
  "items_total": 25,
  "items_ok": 24,
  "items_failed": 1
}
```

### `pipeline_events` (criado por `run.fail()` e `run.event()`)
```json
{
  "run_id": 42,
  "level": "error",
  "document_id": null,
  "message": "Failed to process https://bcb.gov.br/...",
  "details": {
    "item_id": "https://bcb.gov.br/...",
    "error": "Empty conteudo from API",
    "source": "bcb_resolucoes"
  }
}
```

## Como Testar

### 1. Executar a migração
```bash
docker compose exec api alembic upgrade head
```

### 2. Testar scrape com tracking
```bash
docker compose exec api python -m app.worker.scrape --days 1
```

Verifique no banco:
```bash
docker compose exec db psql -U postgresml postgresml << 'SQL'
SELECT * FROM pipeline_runs WHERE stage = 'scrape' ORDER BY id DESC LIMIT 1;
SELECT * FROM pipeline_events WHERE run_id = (SELECT MAX(id) FROM pipeline_runs);
SQL
```

### 3. Testar chunk com tracking
```bash
docker compose exec api python -m app.worker.chunk
```

### 4. Testar embed com tracking
```bash
docker compose exec api python -m app.worker.embed --batch-size 32
```

## Queries Úteis para Monitorar

### Ver todas as execuções de scrape
```sql
SELECT id, stage, status, items_total, items_ok, items_failed, duration_ms
FROM pipeline_runs
WHERE stage = 'scrape'
ORDER BY started_at DESC
LIMIT 10;
```

### Ver últimas 10 falhas
```sql
SELECT r.id, r.stage, e.message, e.details
FROM pipeline_runs r
JOIN pipeline_events e ON r.id = e.run_id
WHERE e.level = 'error'
ORDER BY e.created_at DESC
LIMIT 10;
```

### Tempo total por stage
```sql
SELECT stage, COUNT(*) runs, AVG(duration_ms)::INT avg_duration_ms, 
       MAX(duration_ms) max_duration_ms, SUM(items_total) total_items
FROM pipeline_runs
GROUP BY stage;
```

### Taxa de sucesso por stage
```sql
SELECT stage,
       COUNT(*) total_runs,
       COUNT(CASE WHEN status = 'ok' THEN 1 END) successful_runs,
       ROUND(100.0 * COUNT(CASE WHEN status = 'ok' THEN 1 END) / COUNT(*), 1) success_rate
FROM pipeline_runs
GROUP BY stage;
```

## Próximos Passos

### Fase 4: Endpoints e Frontend
- [ ] `GET /api/admin/runs` - lista de execuções
- [ ] `GET /api/admin/runs/{id}` - detalhes de uma execução
- [ ] `GET /api/admin/runs/{id}/events` - eventos de uma execução
- [ ] `GET /api/admin/queries` - histórico de perguntas
- [ ] Página "Logs" no frontend
- [ ] Atualizar `check_docs.py`

### Fase 5: Verificação Completa
- [ ] Rodar todas as fases com dados reais
- [ ] Verificar registros em `pipeline_runs`
- [ ] Testar com força de falhas
- [ ] Testes unitários

## Notas de Implementação

1. **Dupla escrita**: Scrape mantém compatibilidade escrevendo também em `ingest_runs`
2. **Async/await**: Tudo segue o padrão async/await do projeto
3. **Sem exceções**: Falhas no logging nunca derrubam o pipeline
4. **Contadores**: `items_total`, `items_ok`, `items_failed` são automáticos

## Arquivos Modificados

```
backend/
├── app/
│   ├── observability/
│   │   ├── __init__.py                    [Atualizado: exports async_tracker]
│   │   ├── tracker.py                     [Existente: sync version]
│   │   ├── async_tracker.py               [✓ NOVO: async para asyncpg]
│   │   └── logger.py                      [Existente: log_query]
│   └── worker/
│       ├── scrape.py                      [✓ ATUALIZADO: com track_run]
│       ├── chunk.py                       [✓ ATUALIZADO: com track_run]
│       └── embed.py                       [✓ ATUALIZADO: com track_run]
```

---

**Status:** Fase 3 ✅ Completa. Workers agora registram todas execuções automaticamente!
