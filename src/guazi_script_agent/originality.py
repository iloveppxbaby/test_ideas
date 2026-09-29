"""拒绝与参考文案连续重复的成稿。"""

from __future__ import annotations

import re

from guazi_script_agent.errors import OutputError
from guazi_script_agent.schemas import DraftScript, ReferenceVideo, VideoScript

VERBATIM_WINDOW = 12
_MIN_SOURCE_CHARS = 8
_NOT_WORD = re.compile(r"[^\w]+", re.UNICODE)


def normalize_copy(text: str) -> str:
    return _NOT_WORD.sub("", text).lower()


def find_verbatim_overlap(
    generated: str, sources: list[str], window: int = VERBATIM_WINDOW
) -> str | None:
    """返回第一段连续重复。短于 8 字的原文跳过，避免误伤「二手车」这类通用词。"""
    output = normalize_copy(generated)
    for source in sources:
        compact = normalize_copy(source)
        size = min(window, len(compact))
        if size < _MIN_SOURCE_CHARS:
            continue
        for index in range(len(compact) - size + 1):
            gram = compact[index : index + size]
            if gram in output:
                return gram
    return None


def reference_sources(video: ReferenceVideo) -> list[str]:
    sources = [video.title, video.transcript]
    if video.why_viral:
        sources.append(video.why_viral)
    for note in video.rhythm_notes:
        sources.extend((note.shot, note.purpose))
    return sources


def customer_facing_text(draft: DraftScript | VideoScript) -> str:
    parts = [draft.title, draft.opening_hook, draft.cta]
    for beat in draft.beats:
        parts.extend((beat.voiceover, beat.visual, beat.subtitle))
    notes = getattr(draft, "compliance_notes", None)
    if notes:
        parts.extend(note.message for note in notes)
    return "\n".join(parts)


def assert_original(draft: DraftScript | VideoScript, video: ReferenceVideo) -> None:
    overlap = find_verbatim_overlap(
        customer_facing_text(draft), reference_sources(video)
    )
    if overlap:
        raise OutputError(f"成稿与参考文案连续重复「{overlap}」，已拒绝照搬。")
