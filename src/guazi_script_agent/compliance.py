"""合规后处理：缺证据标待核实，禁用表述从观众可见文案里删除。"""

from __future__ import annotations

import re

from guazi_script_agent.schemas import (
    ComplianceKind,
    ComplianceNote,
    DraftScript,
    ValuePoint,
)

_PUNCT_RUN = re.compile(r"[，。、；：]{2,}")
_EDGE = "，。、；： \n\t"
_CUSTOMER_FIELDS = ("voiceover", "visual", "subtitle")


def forbidden_phrases_of(value_points: list[ValuePoint]) -> list[str]:
    phrases: list[str] = []
    for point in value_points:
        for phrase in point.forbidden_phrases:
            if phrase not in phrases:
                phrases.append(phrase)
    return phrases


def scrub_draft(
    draft: DraftScript, phrases: list[str]
) -> tuple[DraftScript, list[str]]:
    if not phrases:
        return draft, []
    found: list[str] = []
    payload = draft.model_dump()
    payload["title"] = _scrub(payload["title"], phrases, found)
    payload["opening_hook"] = _scrub(payload["opening_hook"], phrases, found)
    payload["cta"] = _scrub(payload["cta"], phrases, found)
    for beat in payload["beats"]:
        for field in _CUSTOMER_FIELDS:
            beat[field] = _scrub(beat[field], phrases, found)
    return DraftScript.model_validate(payload), _unique(found)


def build_compliance_notes(
    value_points: list[ValuePoint], forbidden_hits: list[str]
) -> list[ComplianceNote]:
    notes = [
        ComplianceNote(
            kind=ComplianceKind.no_false_promise,
            message=(
                "避免虚假承诺：不要说绝对最低、未经证据的零事故，也不要承诺一定过户。"
                "未核实的信息不能说成既定事实。"
            ),
        )
    ]
    for point in value_points:
        if point.evidence:
            notes.append(
                ComplianceNote(
                    kind=ComplianceKind.evidence_bound,
                    message=(
                        f"价值点「{point.title}」（{point.id}）只能说到所给证据之内。"
                        "本工具不核验该证据在平台外是否真实。"
                    ),
                    related_value_point_ids=[point.id],
                )
            )
        else:
            notes.append(
                ComplianceNote(
                    kind=ComplianceKind.unverified_claim,
                    message=(
                        f"价值点「{point.title}」（{point.id}）没有证据或事实，已标为待核实。"
                        "发布前需要核对，不能写成承诺。"
                    ),
                    related_value_point_ids=[point.id],
                )
            )
    if forbidden_hits:
        related = [
            point.id
            for point in value_points
            if any(phrase in point.forbidden_phrases for phrase in forbidden_hits)
        ]
        quoted = "、".join(forbidden_hits)
        if len(quoted) > 120:
            quoted = quoted[:120] + "…"
        notes.append(
            ComplianceNote(
                kind=ComplianceKind.forbidden_phrase,
                message=f"观众可见文案出现过禁用表述（{quoted}），已从标题、钩子、口播、画面、字幕和行动号召中删除。",
                related_value_point_ids=related,
            )
        )
    return notes


def _scrub(text: str, phrases: list[str], found: list[str]) -> str:
    updated = text
    removed = False
    for phrase in sorted(phrases, key=len, reverse=True):
        if phrase and phrase in updated:
            found.append(phrase)
            updated = updated.replace(phrase, "")
            removed = True
    if not removed:
        return text
    updated = _PUNCT_RUN.sub("。", updated).strip(_EDGE)
    if not updated:
        return _fallback(phrases)
    if updated.endswith(("。", "！", "？", "…")):
        return updated
    return updated + "。"


def _fallback(phrases: list[str]) -> str:
    for candidate in ("具体以页面公示为准。", "已省略。", "见说明。"):
        if not any(phrase in candidate for phrase in phrases):
            return candidate
    return "已处理。"


def _unique(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item not in result:
            result.append(item)
    return result
