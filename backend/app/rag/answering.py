"""
RAG answering: retrieve chunks and call Claude API to answer questions.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from anthropic import Anthropic

logger = logging.getLogger(__name__)

# System prompt for the RAG assistant
SYSTEM_PROMPT_PT = """Você é um assistente especializado em regulações do Banco Central do Brasil (BCB).

Responda apenas com base nos documentos fornecidos. Se a pergunta não puder ser respondida pelos documentos, diga "Não tenho informações sobre isso nos documentos disponíveis".

Ao responder:
1. Cite as fontes pelo número ([1], [2], etc.)
2. Seja conciso e preciso
3. Mantenha a linguagem formal e técnica
4. Se a pergunta abordar vários tópicos, organize a resposta em seções"""

SYSTEM_PROMPT_EN = """You are an expert assistant on Banco Central do Brasil (BCB) regulations.

Answer only based on the provided documents. If the question cannot be answered from the documents, say "I don't have information about this in the available documents".

When answering:
1. Cite sources by number ([1], [2], etc.)
2. Be concise and precise
3. Maintain formal, technical language
4. If the question covers multiple topics, organize the answer in sections"""


def _build_context_from_chunks(chunks: list[dict[str, Any]]) -> str:
    """Build a context string from retrieved chunks with source numbering."""
    context = "## Documentos relevantes:\n\n"
    for i, chunk in enumerate(chunks, 1):
        context += f"[{i}] **{chunk['title']}** ({chunk['published_at'].date()})\n"
        context += f"Fonte: {chunk['url']}\n\n"
        context += f"{chunk['text']}\n\n"
        context += "---\n\n"
    return context


def answer_question(
    question: str,
    chunks: list[dict[str, Any]],
    language: str = "pt",
    anthropic_api_key: str = "",
    anthropic_model: str = "claude-opus-5-5",
) -> tuple[str, list[dict[str, Any]]]:
    """
    Answer a question using retrieved chunks.
    
    Args:
        question: The user's question
        chunks: Retrieved chunks from retrieve_chunks()
        language: "pt" for Portuguese, "en" for English
        anthropic_api_key: Anthropic API key
        anthropic_model: Claude model to use
    
    Returns:
        Tuple of (answer_text, sources_list)
        sources_list: list of dicts with title, url, date, chunk_text
    """
    if not chunks:
        return "Nenhum documento relevante encontrado." if language == "pt" else "No relevant documents found.", []
    
    context = _build_context_from_chunks(chunks)
    system_prompt = SYSTEM_PROMPT_PT if language == "pt" else SYSTEM_PROMPT_EN
    
    # Prepare the user message
    user_message = f"""Pergunta: {question}

{context}"""
    
    # Call Claude API
    headers = {}
    if anthropic_api_key and "anthropic-workspace-id" not in anthropic_api_key:
        # If we have a separate workspace ID, add it as a header
        # For now, just use the API key as-is; workspace ID would go here if needed
        pass
    client = Anthropic(api_key=anthropic_api_key)
    
    logger.info("Calling Claude API: model=%s language=%s", anthropic_model, language)
    
    response = client.messages.create(
        model=anthropic_model,
        max_tokens=1024,
        system=system_prompt,
        messages=[
            {"role": "user", "content": user_message}
        ],
    )
    
    # Handle both TextBlock and ThinkingBlock responses
    answer_text = ""
    for block in response.content:
        if hasattr(block, 'text'):
            answer_text = block.text
            break
    if not answer_text:
        answer_text = "Unable to generate answer"
    
    # Build sources list
    sources = [
        {
            "title": chunk["title"],
            "url": chunk["url"],
            "published_at": chunk["published_at"],
            "doc_type": chunk["doc_type"],
            "chunk_text": chunk["text"][:200] + "..." if len(chunk["text"]) > 200 else chunk["text"],
        }
        for chunk in chunks
    ]
    
    logger.info("Generated answer with %d sources", len(sources))
    
    return answer_text, sources
