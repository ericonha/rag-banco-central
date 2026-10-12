"""Shared types for all BCB scraping sources."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DocRef:
    """Lightweight reference returned by list_new(); used to decide what to fetch."""

    source: str          # logical name, e.g. "bcb_comunicados"
    url: str             # canonical detail-page URL (used as unique key)
    doc_type: str        # e.g. "Comunicado", "Resolução"
    numero: int
    published_at: datetime
    title: str


@dataclass
class Document:
    """Full document ready for storage."""

    source: str
    url: str
    title: str
    doc_type: str
    published_at: datetime
    language: str
    raw_text: str        # plain text, HTML tags stripped
    content_hash: str    # sha256 of raw_text
    extra: dict = field(default_factory=dict)  # spare bag for future fields
