# Phase 4: RAG Retrieval and Answering

**Files created:**

1. **`app/rag/retrieval.py`** — Semantic search via pgvector
   - `retrieve_chunks()` — queries for top-k chunks similar to a question
   - Uses pgml.embed on-the-fly with "query: " prefix (e5 model requirement)
   - Returns chunks with cosine distance

2. **`app/rag/answering.py`** — RAG answering with Claude API
   - `answer_question()` — takes question + retrieved chunks, calls Claude
   - Returns answer text + structured sources list
   - Supports Portuguese and English

3. **`app/worker/test_rag.py`** — CLI test script for 4 sample questions
   - Tests both Portuguese and English
   - Saves results to `rag_test_results_pt.json`

4. **`tests/test_rag.py`** — Unit tests for RAG components

**To test Phase 4:**

```bash
# Rebuild the container (no new deps, just cleanup)
docker compose build api

# Run the RAG test with Portuguese questions (default)
docker compose run --rm api python -m app.worker.test_rag

# Or test with English questions
docker compose run --rm api python -m app.worker.test_rag --language en --model claude-opus-5-5

# View results
cat rag_test_results_pt.json | jq '.[0].answer' -r
```

**Expected output:**
- 4 questions asked
- Each retrieves 3 chunks
- Claude generates an answer citing sources
- Results saved to JSON with question, answer, sources

**What's working:**
- Cosine similarity search over embeddings ✅
- Question embedding via pgml.embed ✅
- Multi-language prompts (PT + EN) ✅
- Source tracking and citation ✅

**Next: Phase 5** — Build the FastAPI endpoints to expose the RAG system as an HTTP API.
