#!/usr/bin/env python3
"""Check documents and vectorization status in the database."""

import os
import sys

try:
    import psycopg
except ImportError:
    print("Installing psycopg...")
    os.system("pip install psycopg[binary] -q")
    import psycopg

def _conn_string() -> str:
    """DATABASE_URL inside Docker (db:5432); localhost:5433 when run on the Mac."""
    return os.getenv("DATABASE_URL", "postgresql://postgresml:postgresml@localhost:5433/postgresml")


def check_pipeline():
    try:
        with psycopg.connect(_conn_string()) as conn, conn.cursor() as cur:
            print()
            print("=" * 80)
            print("PIPELINE RUNS")
            print("=" * 80)
            cur.execute("""
                SELECT stage, status, COUNT(*), MAX(started_at), COALESCE(AVG(duration_ms), 0)::int
                FROM pipeline_runs GROUP BY stage, status ORDER BY stage, status
            """)
            rows = cur.fetchall()
            if not rows:
                print("No pipeline runs yet.")
            for stage, status, n, last, avg in rows:
                print(f"  {stage:<7} {status:<17} runs={n:<4} avg={avg}ms  last={last}")

            print()
            print("=" * 80)
            print("QUERY LOGS")
            print("=" * 80)
            cur.execute("""
                SELECT COUNT(*), COALESCE(SUM((status = 'ok')::int), 0),
                       COALESCE(AVG(latency_total_ms), 0)::int, MAX(created_at)
                FROM query_logs
            """)
            total, ok, avg_ms, last = cur.fetchone()
            if not total:
                print("No queries logged yet.")
            else:
                print(f"  queries={total} ok={ok} errors={total - ok} avg_latency={avg_ms}ms last={last}")
    except Exception as e:
        print(f"Error reading pipeline tables: {e}")
        sys.exit(1)


def check_documents():
    conn_string = _conn_string()
    
    try:
        with psycopg.connect(conn_string) as conn:
            with conn.cursor() as cur:
                # Get document stats
                cur.execute("""
                    SELECT 
                      COUNT(DISTINCT d.id) as total_documents,
                      COUNT(DISTINCT CASE WHEN c.embedding IS NOT NULL THEN d.id END) as docs_with_embeddings,
                      COUNT(c.id) as total_chunks,
                      COUNT(CASE WHEN c.embedding IS NOT NULL THEN 1 END) as chunks_with_embeddings
                    FROM documents d
                    LEFT JOIN chunks c ON d.id = c.document_id
                """)
                
                total_docs, docs_vec, total_chunks, chunks_vec = cur.fetchone()
                
                print("=" * 80)
                print("DATABASE SUMMARY")
                print("=" * 80)
                print(f"Total Documents:           {total_docs}")
                print(f"Documents with Embeddings: {docs_vec if docs_vec else 0}")
                print(f"Total Chunks:              {total_chunks if total_chunks else 0}")
                print(f"Chunks with Embeddings:    {chunks_vec if chunks_vec else 0}")
                if total_chunks and total_chunks > 0:
                    print(f"Chunk Vectorization Rate:  {(chunks_vec/total_chunks)*100:.1f}%")
                print()
                
                # Show document details
                if total_docs and total_docs > 0:
                    print("=" * 80)
                    print("DOCUMENT DETAILS")
                    print("=" * 80)
                    cur.execute("""
                        SELECT 
                          d.id,
                          d.title,
                          d.source,
                          d.doc_type,
                          d.published_at,
                          COUNT(c.id) as chunk_count,
                          COUNT(CASE WHEN c.embedding IS NOT NULL THEN 1 END) as chunks_vectorized,
                          LENGTH(d.raw_text) as text_bytes,
                          d.fetched_at
                        FROM documents d
                        LEFT JOIN chunks c ON d.id = c.document_id
                        GROUP BY d.id, d.title, d.source, d.doc_type, d.published_at, d.fetched_at
                        ORDER BY d.fetched_at DESC
                    """)
                    
                    for row in cur.fetchall():
                        doc_id, title, source, doc_type, pub_date, chunks, vec_chunks, size, fetched = row
                        status = "✓" if vec_chunks and vec_chunks > 0 else "✗"
                        print(f"\n{status} ID: {doc_id}")
                        print(f"  Title:        {title[:60] if title else 'N/A'}{'...' if title and len(title) > 60 else ''}")
                        print(f"  Source:       {source}")
                        print(f"  Type:         {doc_type if doc_type else 'N/A'}")
                        print(f"  Published:    {pub_date if pub_date else 'N/A'}")
                        print(f"  Chunks:       {chunks if chunks else 0} ({vec_chunks if vec_chunks else 0} vectorized)")
                        print(f"  Text Size:    {size:,} bytes")
                        print(f"  Fetched:      {fetched}")
                else:
                    print("No documents found in database.")
                    
    except Exception as e:
        print(f"Error: {e}")
        print("\nMake sure:")
        print("  1. Docker containers are running: docker-compose up db api frontend")
        print("  2. Database is initialized: docker-compose exec api alembic upgrade head")
        print("  3. PostgreSQL is reachable: localhost:5433 from the Mac, db:5432 inside Docker")
        sys.exit(1)

if __name__ == "__main__":
    check_documents()
    check_pipeline()
