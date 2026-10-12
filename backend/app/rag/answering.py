"""
RAG answering: build the prompt from retrieved chunks and call the Claude API
(blocking or streaming).
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from anthropic import Anthropic, AsyncAnthropic

from app.rag.context import build_messages

logger = logging.getLogger(__name__)

# System prompt for the RAG assistant
SYSTEM_PROMPT_PT = """Você é um assistente especializado em regulações do Banco Central do Brasil (BCB).

Responda apenas com base nos documentos fornecidos. Se a pergunta não puder ser respondida pelos documentos, diga "Não tenho informações sobre isso nos documentos disponíveis".

Ao responder:
1. Termine cada afirmação com o número da fonte que a sustenta ([1], [2], etc.). Nunca cite uma fonte que não sustenta a frase.
2. Use números, datas, prazos e valores exatamente como aparecem nos documentos. Nunca invente nem calcule valores que não estejam neles.
3. Se os documentos respondem só uma parte da pergunta, responda essa parte e diga claramente o que não consta nos documentos.
4. Seja conciso e preciso, com linguagem formal e técnica.
5. Se a pergunta abordar vários tópicos, organize a resposta em seções."""

SYSTEM_PROMPT_EN = """You are an expert assistant on Banco Central do Brasil (BCB) regulations.

Answer only based on the provided documents. If the question cannot be answered from the documents, say "I don't have information about this in the available documents".

When answering:
1. End every claim with the number of the source that supports it ([1], [2], etc.). Never cite a source that does not support the sentence.
2. Use numbers, dates, deadlines and amounts exactly as they appear in the documents. Never invent or compute values that are not in them.
3. If the documents answer only part of the question, answer that part and state clearly what the documents do not cover.
4. Be concise and precise, in formal, technical language.
5. If the question covers multiple topics, organize the answer in sections."""


def _build_context_from_chunks(chunks: list[dict[str, Any]]) -> str:
    """Build a context string from retrieved chunks with source numbering."""
    context = "## Documentos relevantes:\n\n"
    for i, chunk in enumerate(chunks, 1):
        context += f"[{i}] **{chunk['title']}** ({chunk['published_at'].date()})\n"
        context += f"Fonte: {chunk['url']}\n\n"
        context += f"{chunk['text']}\n\n"
        context += "---\n\n"
    return context


def prepare_prompt(
    question: str,
    chunks: list[dict[str, Any]],
    language: str,
    history: list[dict[str, Any]] | None,
) -> tuple[str, list[dict[str, str]]]:
    """(system prompt, messages) for the Anthropic API."""
    system_prompt = SYSTEM_PROMPT_PT if language == "pt" else SYSTEM_PROMPT_EN
    user_message = f"""Pergunta: {question}

{_build_context_from_chunks(chunks)}"""
    return system_prompt, build_messages(history, user_message)


def sources_from_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Source cards shown next to the answer (same order as the [n] numbers)."""
    return [
        {
            "title": chunk["title"],
            "url": chunk["url"],
            "published_at": chunk["published_at"],
            "doc_type": chunk["doc_type"],
            "chunk_text": chunk["text"][:200] + "..." if len(chunk["text"]) > 200 else chunk["text"],
        }
        for chunk in chunks
    ]


def answer_question_with_usage(
    question: str,
    chunks: list[dict[str, Any]],
    language: str = "pt",
    anthropic_api_key: str = "",
    anthropic_model: str = "claude-opus-5-5",
    history: list[dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, int | None]]:
    """
    Answer a question using retrieved chunks and earlier turns of the conversation.

    Returns (answer_text, sources, usage) where usage = {"tokens_in", "tokens_out"}
    (None when the API did not report them).
    """
    empty_usage: dict[str, int | None] = {"tokens_in": None, "tokens_out": None}
    if not chunks:
        msg = "Nenhum documento relevante encontrado." if language == "pt" else "No relevant documents found."
        return msg, [], empty_usage

    system_prompt, messages = prepare_prompt(question, chunks, language, history)
    client = Anthropic(api_key=anthropic_api_key)
    logger.info(
        "Calling Claude API: model=%s language=%s history_msgs=%d",
        anthropic_model, language, len(history or []),
    )

    response = client.messages.create(
        model=anthropic_model,
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
    )

    # Handle both TextBlock and ThinkingBlock responses
    answer_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            answer_text = block.text
            break
    if not answer_text:
        answer_text = "Unable to generate answer"

    usage_obj = getattr(response, "usage", None)
    usage: dict[str, int | None] = {
        "tokens_in": getattr(usage_obj, "input_tokens", None),
        "tokens_out": getattr(usage_obj, "output_tokens", None),
    }
    sources = sources_from_chunks(chunks)
    logger.info("Generated answer with %d sources, usage=%s", len(sources), usage)
    return answer_text, sources, usage


def answer_question(
    question: str,
    chunks: list[dict[str, Any]],
    language: str = "pt",
    anthropic_api_key: str = "",
    anthropic_model: str = "claude-opus-5-5",
    history: list[dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Backwards-compatible wrapper: (answer_text, sources) without usage."""
    text, sources, _ = answer_question_with_usage(
        question, chunks, language, anthropic_api_key, anthropic_model, history
    )
    return text, sources


async def stream_answer(
    question: str,
    chunks: list[dict[str, Any]],
    language: str = "pt",
    anthropic_api_key: str = "",
    anthropic_model: str = "claude-opus-5-5",
    history: list[dict[str, Any]] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """
    Stream an answer. Yields {"type": "delta", "text": ...} for every piece of text and, at
    the end, {"type": "usage", "tokens_in": ..., "tokens_out": ...}.
    """
    system_prompt, messages = prepare_prompt(question, chunks, language, history)
    client = AsyncAnthropic(api_key=anthropic_api_key)
    logger.info("Streaming from Claude API: model=%s history_msgs=%d", anthropic_model, len(history or []))

    async with client.messages.stream(
        model=anthropic_model,
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
    ) as stream:
        async for text in stream.text_stream:
            yield {"type": "delta", "text": text}
        final = await stream.get_final_message()

    usage_obj = getattr(final, "usage", None)
    yield {
        "type": "usage",
        "tokens_in": getattr(usage_obj, "input_tokens", None),
        "tokens_out": getattr(usage_obj, "output_tokens", None),
    }
