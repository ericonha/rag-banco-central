"""
Deterministic grounding check: is each cited sentence of an answer backed by the chunk it cites?

No LLM call, so it is free and reproducible. It is a heuristic: it catches invalid [n]
citations, missing citations, numbers/dates that do not appear in the cited text, and
sentences whose vocabulary barely overlaps with the cited text. It cannot judge meaning.
"""
from __future__ import annotations

import re
from typing import Any

CITE_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
_NUM_RE = re.compile(r"\d+(?:[.,/]\d+)*")
_WORD_RE = re.compile(r"[^\W\d_]{5,}", re.UNICODE)
_SENT_SPLIT = re.compile(r"(?<=[.!?;])\s+|\n+")
_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")

REFUSAL_MARKERS = (
    "não tenho informações",
    "nao tenho informacoes",
    "nenhum documento relevante",
    "i don't have information",
    "no relevant documents",
)

# Frequent long words that say nothing about whether a sentence is supported.
_STOPWORDS = frozenset(
    """sobre entre segundo conforme também quando apenas deste desta destes destas esses essas
    esta estão ainda porém assim todos todas outros outras sendo ficam fica caso nesse nessa
    which their there would about these those other where while should shall under
    banco central brasil documentos documento resolução circular comunicado""".split()
)

MIN_SUPPORT = 0.35
MAX_FLAGS = 6


def _plain_numbers(text: str) -> str:
    """Drop thousands/date separators between digits: "34.977" -> "34977"."""
    return re.sub(r"(?<=\d)[.,/](?=\d)", "", text)


def _numbers(sentence: str) -> list[str]:
    s = _LIST_MARKER_RE.sub("", CITE_RE.sub(" ", sentence))
    return [re.sub(r"[.,/]", "", n) for n in _NUM_RE.findall(s)]


def _content_words(sentence: str) -> set[str]:
    words = {w.lower() for w in _WORD_RE.findall(CITE_RE.sub(" ", sentence))}
    return {w for w in words if w not in _STOPWORDS}


def _flag(kind: str, sentence: str, detail: str) -> dict[str, str]:
    s = " ".join(sentence.split())
    return {"type": kind, "sentence": s if len(s) <= 160 else s[:159] + "…", "detail": detail}


def check_answer(answer: str, chunk_texts: list[str]) -> dict[str, Any]:
    """
    Returns {"score": 0..1, "ok": bool, "checked": int, "flags": [...]}.

    `score` is the share of cited sentences without any flag. Refusals ("não tenho
    informações…") score 1.0, an answer with no citations at all scores 0.0.
    """
    text = (answer or "").strip()
    if not text or any(m in text.lower() for m in REFUSAL_MARKERS):
        return {"score": 1.0, "ok": True, "checked": 0, "flags": []}

    plain_chunks = [_plain_numbers(c) for c in chunk_texts]
    lower_chunks = [c.lower() for c in chunk_texts]

    flags: list[dict[str, str]] = []
    cited = clean = 0
    for sentence in (s.strip() for s in _SENT_SPLIT.split(text)):
        if not sentence or sentence.startswith("#"):
            continue
        groups = CITE_RE.findall(sentence)
        if not groups:
            continue
        cited += 1
        indices = [int(n) for g in groups for n in re.split(r"\s*,\s*", g)]
        invalid = [n for n in indices if not 1 <= n <= len(chunk_texts)]
        valid = [n for n in indices if 1 <= n <= len(chunk_texts)]
        sentence_flags: list[dict[str, str]] = []

        if invalid:
            sentence_flags.append(_flag("invalid_citation", sentence, f"cita [{invalid[0]}], que não existe"))
        if valid:
            support_plain = " ".join(plain_chunks[n - 1] for n in valid)
            support_lower = " ".join(lower_chunks[n - 1] for n in valid)
            missing = [
                n for n in _numbers(sentence) if not re.search(rf"(?<!\d){re.escape(n)}(?!\d)", support_plain)
            ]
            if missing:
                sentence_flags.append(
                    _flag("unsupported_number", sentence, f"{', '.join(missing[:3])} não aparece no trecho citado")
                )
            words = _content_words(sentence)
            if len(words) >= 4:
                found = sum(1 for w in words if w[:6] in support_lower)
                if found / len(words) < MIN_SUPPORT:
                    sentence_flags.append(
                        _flag("low_support", sentence, f"só {found}/{len(words)} termos aparecem no trecho citado")
                    )
        if sentence_flags:
            flags.extend(sentence_flags)
        else:
            clean += 1

    if cited == 0:
        flags.append(_flag("no_citations", text, "a resposta não cita nenhuma fonte"))
        return {"score": 0.0, "ok": False, "checked": 0, "flags": flags[:MAX_FLAGS]}

    return {
        "score": round(clean / cited, 3),
        "ok": not flags,
        "checked": cited,
        "flags": flags[:MAX_FLAGS],
    }
