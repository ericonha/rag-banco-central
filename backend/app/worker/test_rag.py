"""
Test the RAG pipeline with sample questions.

Usage:
    python -m app.worker.test_rag [--language pt|en] [--model claude-haiku-5-5]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from app.config import get_settings
from app.db.session import get_conn
from app.rag.answering import answer_question
from app.rag.retrieval import retrieve_chunks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("test_rag")

# Sample questions in Portuguese
SAMPLE_QUESTIONS_PT = [
    "O que é o CCS e qual é seu propósito?",
    "Como as instituições de pagamento são incluídas no Ranking de Reclamações?",
    "Quais são os requisitos para participação no CCS?",
    "O que foi comunicado sobre a inclusão de novas instituições?",
]

# Sample questions in English
SAMPLE_QUESTIONS_EN = [
    "What is the CCS and what is its purpose?",
    "How are payment institutions included in the Complaints Ranking?",
    "What are the requirements for participation in the CCS?",
    "What was communicated about the inclusion of new institutions?",
]


async def test_rag(language: str = "pt", model: str = "claude-haiku-5-5") -> None:
    """Test RAG with sample questions."""
    settings = get_settings()
    
    if not settings.embedding_model:
        logger.error("EMBEDDING_MODEL not set in .env")
        sys.exit(1)
    
    if not settings.anthropic_api_key:
        logger.error("ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    questions = SAMPLE_QUESTIONS_PT if language == "pt" else SAMPLE_QUESTIONS_EN
    
    logger.info("Testing RAG pipeline: language=%s model=%s", language, model)
    logger.info("Sample questions: %d", len(questions))

    results = []

    async with get_conn() as conn:
        for i, question in enumerate(questions, 1):
            logger.info("\n[%d/%d] %s", i, len(questions), question)
            
            try:
                # Retrieve relevant chunks
                chunks = await retrieve_chunks(
                    conn,
                    question=question,
                    embedding_model=settings.embedding_model,
                    embedding_dim=settings.embedding_dim,
                    k=3,
                )
                
                if not chunks:
                    logger.warning("No chunks retrieved")
                    continue
                
                logger.info("Retrieved %d chunks", len(chunks))
                
                # Answer the question
                answer, sources = answer_question(
                    question=question,
                    chunks=chunks,
                    language=language,
                    anthropic_api_key=settings.anthropic_api_key,
                    anthropic_model=model,
                )
                
                logger.info("Answer: %s...", answer[:100])
                logger.info("Sources: %d", len(sources))
                
                results.append({
                    "question": question,
                    "answer": answer,
                    "sources": sources,
                })

            except Exception as exc:
                logger.error("Error processing question: %s", exc)

    # Print summary
    logger.info("\n\n=== RAG Test Results ===")
    logger.info("Processed %d/%d questions", len(results), len(questions))
    
    for i, result in enumerate(results, 1):
        print(f"\n[{i}] Q: {result['question']}")
        print(f"A: {result['answer'][:200]}...")
        print(f"Sources: {len(result['sources'])}")
        for source in result['sources']:
            print(f"  - {source['title']} ({source['published_at'].date()})")

    # Save results to file
    output_file = f"rag_test_results_{language}.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info(f"\nResults saved to {output_file}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test RAG pipeline")
    parser.add_argument("--language", choices=["pt", "en"], default="pt", help="Question language")
    parser.add_argument("--model", default="claude-haiku-5-5", help="Claude model to use")
    args = parser.parse_args()
    asyncio.run(test_rag(language=args.language, model=args.model))


if __name__ == "__main__":
    main()
