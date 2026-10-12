"""Admin API against a real, migrated Postgres (skipped unless RUN_DB_TESTS=1)."""
import uuid

import pytest
from psycopg.types.json import Jsonb


async def _client():
    from httpx import ASGITransport, AsyncClient

    from app.main import app, rate_limiter

    rate_limiter.requests.clear()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _insert(db, sql: str, params: tuple, cleanup_table: str) -> int:
    row = db.execute(sql + " RETURNING id", params).fetchone()
    db.cleanups.append((f"DELETE FROM {cleanup_table} WHERE id = %s", (row[0],)))
    return row[0]


@pytest.mark.asyncio
async def test_runs_events_and_stats(db) -> None:
    run_id = _insert(
        db,
        "INSERT INTO pipeline_runs (stage, status, duration_ms, params, items_total, items_ok, "
        "items_failed, finished_at) VALUES ('scrape', 'done_with_errors', 1200, %s, 3, 2, 1, now())",
        (Jsonb({"days": 2}),),
        "pipeline_runs",
    )
    db.execute(
        "INSERT INTO pipeline_events (run_id, level, message, details) VALUES (%s, 'error', %s, %s)",
        (run_id, "Failed to process X", Jsonb({"error_type": "ValueError"})),
    )

    async with await _client() as client:
        listing = (await client.get("/api/admin/runs", params={"stage": "scrape", "page_size": 100})).json()
        assert {"items", "total", "page", "page_size", "total_pages"} <= set(listing)
        assert run_id in [r["id"] for r in listing["items"]]

        detail = (await client.get(f"/api/admin/runs/{run_id}")).json()
        assert detail["status"] == "done_with_errors"
        assert detail["items_failed"] == 1
        assert detail["params"] == {"days": 2}

        events = (await client.get(f"/api/admin/runs/{run_id}/events")).json()
        assert [e["message"] for e in events] == ["Failed to process X"]
        assert events[0]["details"]["error_type"] == "ValueError"

        assert (await client.get("/api/admin/runs/999999999")).status_code == 404
        assert (await client.get("/api/admin/runs", params={"page": 0})).status_code == 422

        stats = (await client.get("/api/admin/stats/pipeline")).json()
        scrape = next(s for s in stats if s["stage"] == "scrape")
        assert scrape["total_runs"] >= 1
        assert scrape["total_items_failed"] >= 1


@pytest.mark.asyncio
async def test_query_logs_and_stats(db) -> None:
    ok_id = _insert(
        db,
        "INSERT INTO query_logs (question, answer, retrieved, tokens_in, tokens_out, cost_usd, "
        "latency_total_ms, status) VALUES ('q ok', 'a', %s, 1000, 200, 0.0025, 900, 'ok')",
        (Jsonb([{"chunk_id": 1, "document_id": 1, "score": 0.9}]),),
        "query_logs",
    )
    err_id = _insert(
        db,
        "INSERT INTO query_logs (question, status, error) VALUES ('q err', 'error', 'boom')",
        (),
        "query_logs",
    )

    async with await _client() as client:
        listing = (await client.get("/api/admin/queries", params={"hours": 1, "page_size": 100})).json()
        by_id = {q["id"]: q for q in listing["items"]}
        assert by_id[ok_id]["tokens_in"] == 1000
        assert by_id[ok_id]["cost_usd"] == pytest.approx(0.0025)
        assert by_id[ok_id]["retrieved"][0]["chunk_id"] == 1
        assert by_id[err_id]["status"] == "error"
        assert by_id[err_id]["cost_usd"] is None

        stats = (await client.get("/api/admin/stats/queries")).json()
        assert stats["total_queries"] >= 2
        assert stats["failed_queries"] >= 1
        assert stats["total_tokens_in"] >= 1000
        assert stats["total_cost_usd"] >= 0.0025


@pytest.mark.asyncio
async def test_documents_dashboard(db, token) -> None:
    doc_id = _insert(
        db,
        "INSERT INTO documents (source, url, title, doc_type, content_hash, raw_text) "
        "VALUES ('test', %s, %s, 'TesteTipo', 'h', 'texto')",
        (f"https://example.test/{token}", f"Resolução Teste {token}"),
        "documents",
    )
    db.execute("INSERT INTO chunks (document_id, chunk_index, text) VALUES (%s, 0, 'a')", (doc_id,))
    db.execute(
        "INSERT INTO chunks (document_id, chunk_index, text, embedding) "
        "VALUES (%s, 1, 'b', array_fill(0.1::real, ARRAY[768])::vector)",
        (doc_id,),
    )

    async with await _client() as client:
        data = (await client.get("/api/admin/documents", params={"q": token})).json()
        assert data["total"] == 1
        item = data["items"][0]
        assert item["id"] == doc_id
        assert (item["chunks"], item["embedded"]) == (2, 1)
        assert {"documents", "chunks", "embedded", "without_chunks", "last_fetched_at"} <= set(data["summary"])
        assert any(t["doc_type"] == "TesteTipo" for t in data["types"])

        none = (await client.get("/api/admin/documents", params={"q": token, "doc_type": "Outro"})).json()
        assert none["total"] == 0 and none["items"] == []


@pytest.mark.asyncio
async def test_title_number_lookup_and_history(db, token) -> None:
    import psycopg
    from psycopg.rows import dict_row

    from app.db.conversations import get_recent_history, save_exchange
    from app.rag.retrieval import _chunks_by_title_number

    number = str(900000 + int(uuid.uuid4().int % 90000))
    doc_id = _insert(
        db,
        "INSERT INTO documents (source, url, title, doc_type, content_hash, raw_text) "
        "VALUES ('test', %s, %s, 'Resolução BCB', 'h', 'texto')",
        (f"https://example.test/{token}", f"Resolução BCB N° {number}"),
        "documents",
    )
    db.execute("INSERT INTO chunks (document_id, chunk_index, text) VALUES (%s, 0, 'conteudo')", (doc_id,))

    import os

    async with await psycopg.AsyncConnection.connect(
        os.environ["DATABASE_URL"], row_factory=dict_row
    ) as conn:
        found = await _chunks_by_title_number(conn, [number], 5, None)
        assert [c["document_id"] for c in found] == [doc_id]
        assert await _chunks_by_title_number(conn, [number], 5, "Comunicado") == []

    conv = uuid.uuid4()
    db.cleanups.append(("DELETE FROM conversations WHERE id = %s", (conv,)))
    await save_exchange(conv, "pt", "pergunta 1", "resposta 1", [])
    await save_exchange(conv, "pt", "pergunta 2", "resposta 2", [])
    last_two = await get_recent_history(conv, 2)
    assert [(m["role"], m["content"]) for m in last_two] == [
        ("user", "pergunta 2"),
        ("assistant", "resposta 2"),
    ]
    assert len(await get_recent_history(conv, 10)) == 4
    assert await get_recent_history(conv, 0) == []
