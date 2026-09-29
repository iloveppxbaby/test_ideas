"""把结构提取、提示词、生成器、合规和原创性校验串起来。"""

from __future__ import annotations

from pydantic import ValidationError

from guazi_script_agent.compliance import (
    build_compliance_notes,
    forbidden_phrases_of,
    scrub_draft,
)
from guazi_script_agent.errors import AgentError, OutputError
from guazi_script_agent.llm.base import LLMClient
from guazi_script_agent.llm.mock import MockLLMClient
from guazi_script_agent.originality import assert_original
from guazi_script_agent.prompts import PROMPT_VERSION, render_prompts
from guazi_script_agent.schemas import (
    TIME_TOLERANCE_SECONDS,
    DraftScript,
    ReferenceStructure,
    ScriptRequest,
    StructureBorrowed,
    VideoScript,
)
from guazi_script_agent.structure import extract_structure


def generate_script(
    request: ScriptRequest, llm: LLMClient | None = None
) -> VideoScript:
    client = llm if llm is not None else MockLLMClient()
    structure = extract_structure(request.reference, request.resolved_duration())
    system_prompt, user_prompt = render_prompts(request, structure)
    prompt = user_prompt
    last_error: OutputError | None = None
    for _ in range(2):
        raw = client.complete(system_prompt=system_prompt, user_prompt=prompt)
        try:
            return _accept(raw, request, structure, client.name)
        except OutputError as exc:
            last_error = exc
            prompt = f"{user_prompt}\n\n请只输出修正后的 JSON。问题：{exc}"
    raise AgentError(f"两次生成都未通过校验：{last_error}") from last_error


def _accept(
    raw: str, request: ScriptRequest, structure: ReferenceStructure, provider: str
) -> VideoScript:
    draft = _parse_draft(raw)
    _assert_matches_request(draft, request, structure)
    phrases = forbidden_phrases_of(request.value_points.value_points)
    scrubbed, hits = scrub_draft(draft, phrases)
    notes = build_compliance_notes(request.value_points.value_points, hits)
    script = VideoScript(
        prompt_version=PROMPT_VERSION,
        provider=provider,
        title=scrubbed.title,
        target_duration_seconds=scrubbed.target_duration_seconds,
        opening_hook=scrubbed.opening_hook,
        beats=scrubbed.beats,
        cta=scrubbed.cta,
        compliance_notes=notes,
        structure_borrowed=StructureBorrowed(
            hook_type=structure.hook_type,
            beat_count=structure.beat_count,
            shot_density_per_10s=structure.shot_density_per_10s,
            source_duration_seconds=request.reference.duration_seconds,
            timing_scaled=abs(
                structure.duration_seconds - request.reference.duration_seconds
            )
            > TIME_TOLERANCE_SECONDS,
        ),
    )
    assert_original(script, request.reference)
    return script


def _parse_draft(raw: str) -> DraftScript:
    try:
        return DraftScript.model_validate_json(_extract_json_object(raw))
    except ValidationError as exc:
        raise OutputError(f"模型输出不符合草稿结构（{exc.error_count()} 处）") from exc
    except OutputError:
        raise


def _extract_json_object(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise OutputError("模型输出里没有 JSON 对象")
    return text[start : end + 1]


def _assert_matches_request(
    draft: DraftScript, request: ScriptRequest, structure: ReferenceStructure
) -> None:
    if (
        abs(draft.target_duration_seconds - structure.duration_seconds)
        > TIME_TOLERANCE_SECONDS
    ):
        raise OutputError("草稿时长与目标时长不一致")
    if len(draft.beats) != len(structure.beats):
        raise OutputError("草稿节拍数量与参考结构不一致")
    for beat, spec in zip(draft.beats, structure.beats, strict=True):
        if beat.role != spec.role:
            raise OutputError(f"第 {beat.index} 镜的角色应为 {spec.role.value}")
        if abs(beat.start_seconds - spec.start_seconds) > TIME_TOLERANCE_SECONDS:
            raise OutputError(f"第 {beat.index} 镜的开始时间偏离结构")
        if abs(beat.end_seconds - spec.end_seconds) > TIME_TOLERANCE_SECONDS:
            raise OutputError(f"第 {beat.index} 镜的结束时间偏离结构")
    known = {point.id for point in request.value_points.value_points}
    seen: set[str] = set()
    for beat in draft.beats:
        for identifier in beat.value_point_ids:
            if identifier not in known:
                raise OutputError(f"未知价值点：{identifier}")
            seen.add(identifier)
    missing = known - seen
    if missing:
        raise OutputError("有价值点没有进入分镜：" + "、".join(sorted(missing)))
