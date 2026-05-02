"""Sentence-aware text splitter for Chatterbox (quality degrades past ~300 chars)."""

from __future__ import annotations

import re
from typing import List

DEFAULT_MAX_CHARS = 300

_LATIN_SENT_END = re.compile(r"(?<=[.!?])\s+")
_CJK_SENT_END = re.compile(r"(?<=[。！？!?])")
_CJK_LANGS = {"zh", "ja", "ko"}


def _split_sentences(text: str, language_id: str) -> List[str]:
    text = text.strip()
    if not text:
        return []
    if language_id in _CJK_LANGS:
        parts = _CJK_SENT_END.split(text)
    else:
        parts = _LATIN_SENT_END.split(text)
    return [p.strip() for p in parts if p.strip()]


def _hard_wrap(sentence: str, max_chars: int) -> List[str]:
    """Fallback for a single sentence longer than max_chars: split on commas, then words."""
    if len(sentence) <= max_chars:
        return [sentence]
    chunks: List[str] = []
    parts = re.split(r"(?<=,)\s+", sentence)
    if len(parts) == 1:
        parts = sentence.split(" ")
    buf = ""
    for p in parts:
        candidate = (buf + " " + p).strip() if buf else p
        if len(candidate) <= max_chars:
            buf = candidate
            continue
        if buf:
            chunks.append(buf)
        if len(p) > max_chars:
            for i in range(0, len(p), max_chars):
                chunks.append(p[i : i + max_chars])
            buf = ""
        else:
            buf = p
    if buf:
        chunks.append(buf)
    return chunks


def split_for_tts(text: str, language_id: str = "en", max_chars: int = DEFAULT_MAX_CHARS) -> List[str]:
    """Split text into TTS-friendly chunks bounded by max_chars."""
    sentences = _split_sentences(text, language_id)
    if not sentences:
        return []

    chunks: List[str] = []
    buf = ""
    for sent in sentences:
        if len(sent) > max_chars:
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.extend(_hard_wrap(sent, max_chars))
            continue
        candidate = (buf + " " + sent).strip() if buf else sent
        if len(candidate) <= max_chars:
            buf = candidate
        else:
            if buf:
                chunks.append(buf)
            buf = sent
    if buf:
        chunks.append(buf)
    return chunks


def estimate_chunks(text: str, language_id: str = "en", max_chars: int = DEFAULT_MAX_CHARS) -> int:
    return len(split_for_tts(text, language_id, max_chars))
