"""
Structure-aware chunking for Portuguese regulatory documents.

Splits documents into chunks of 500-800 tokens, respecting article boundaries.
Uses tiktoken for accurate token counting.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import tiktoken

MIN_CHUNK_TOKENS = 400
TARGET_CHUNK_TOKENS = 650
MAX_CHUNK_TOKENS = 800

ARTICLE_PATTERN = re.compile(r"^Art(?:\.|igo)\.?\s+\d+", re.MULTILINE)


@dataclass
class Chunk:
    """A single chunk of a document."""
    document_id: int
    chunk_index: int
    text: str
    token_count: int


class PortugueseRegulationChunker:
    """Chunks Portuguese regulatory text with structure awareness."""

    def __init__(self) -> None:
        self.encoding = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken."""
        return len(self.encoding.encode(text))

    def _split_into_sections(self, text: str) -> list[str]:
        """Split by articles; fall back to paragraphs."""
        articles = ARTICLE_PATTERN.split(text)
        if len(articles) > 1:
            sections = []
            parts = ARTICLE_PATTERN.findall(text)
            for i, article in enumerate(articles):
                if i == 0 and article.strip():
                    sections.append(article)
                elif i < len(parts):
                    sections.append(parts[i - 1] + " " + article)
            return [s.strip() for s in sections if s.strip()]
        
        # Fall back to paragraphs
        paragraphs = text.split("\n\n")
        return [p.strip() for p in paragraphs if p.strip()]

    def _make_chunks_from_sections(
        self, sections: list[str], document_id: int
    ) -> list[Chunk]:
        """Combine sections into chunks, respecting size limits."""
        chunks: list[Chunk] = []
        current_chunk_text = ""
        current_chunk_tokens = 0

        for section in sections:
            section_tokens = self.count_tokens(section)

            # If section alone exceeds max, split by sentences
            if section_tokens > MAX_CHUNK_TOKENS:
                if current_chunk_text.strip():
                    chunks.append(Chunk(document_id, len(chunks), current_chunk_text.strip(), current_chunk_tokens))
                    current_chunk_text = ""
                    current_chunk_tokens = 0

                sentences = re.split(r"(?<=[.!?])\s+", section)
                temp_chunk = ""
                temp_tokens = 0
                for sent in sentences:
                    sent_tokens = self.count_tokens(sent)
                    if temp_tokens + sent_tokens > MAX_CHUNK_TOKENS and temp_chunk:
                        chunks.append(Chunk(document_id, len(chunks), temp_chunk.strip(), temp_tokens))
                        temp_chunk = sent
                        temp_tokens = sent_tokens
                    else:
                        temp_chunk += (" " + sent) if temp_chunk else sent
                        temp_tokens += sent_tokens

                if temp_chunk.strip():
                    chunks.append(Chunk(document_id, len(chunks), temp_chunk.strip(), temp_tokens))
                continue

            # Check if adding section exceeds target
            if current_chunk_tokens + section_tokens > TARGET_CHUNK_TOKENS and current_chunk_text.strip():
                chunks.append(Chunk(document_id, len(chunks), current_chunk_text.strip(), current_chunk_tokens))
                current_chunk_text = section
                current_chunk_tokens = section_tokens
            else:
                if current_chunk_text.strip():
                    current_chunk_text += "\n\n" + section
                else:
                    current_chunk_text = section
                current_chunk_tokens += section_tokens

        if current_chunk_text.strip():
            chunks.append(Chunk(document_id, len(chunks), current_chunk_text.strip(), current_chunk_tokens))

        return chunks

    def chunk(self, text: str, document_id: int) -> list[Chunk]:
        """Chunk document text into 500-800 token pieces."""
        if not text or not text.strip():
            return []

        text = "\n\n".join(p.strip() for p in text.split("\n\n") if p.strip())
        sections = self._split_into_sections(text)
        chunks = self._make_chunks_from_sections(sections, document_id)

        return chunks
