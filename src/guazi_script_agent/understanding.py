"""把豆包的视频理解结果收成参考结构。转写只留下做查重。"""

from __future__ import annotations

from typing import Protocol

from pydantic import Field, ValidationError

from guazi_script_agent.errors import AgentError, OutputError
from guazi_script_agent.llm.base import LLMClient
from guazi_script_agent.prompts.text_v1 import TEXT_INSTRUCTION, render_text_prompt
from guazi_script_agent.prompts.video_v1 import VIDEO_INSTRUCTION
from guazi_script_agent.schemas import (
    MAX_DURATION_SECONDS,
    MIN_DURATION_SECONDS,
    TIME_TOLERANCE_SECONDS,
    HookType,
    ReferenceVideo,
    RhythmNote,
    ScriptRequest,
    StrictModel,
)


class VideoUnderstander(Protocol):
    def understand(self, video_url: str, instruction: str) -> str:
        """返回 VideoUnderstanding 的 JSON 文本。"""


class VideoUnderstanding(StrictModel):
    duration_seconds: float = Field(ge=MIN_DURATION_SECONDS, le=MAX_DURATION_SECONDS)
    hook_type: HookType
    rhythm_notes: list[RhythmNote] = Field(default_factory=list, max_length=12)
    transcript: str = Field(default="", max_length=8000)
    why_viral: str | None = Field(default=None, max_length=500)


def needs_video_understanding(video: ReferenceVideo) -> bool:
    """没有转写的直链才送给视频理解模型。已有转写时改走文本理解。"""
    if not video.url:
        return False
    return not video.transcript.strip()


def needs_text_understanding(video: ReferenceVideo) -> bool:
    """有转写、还没有节奏，并且不需要再看视频时，交给文本模型。"""
    if needs_video_understanding(video):
        return False
    return bool(video.transcript.strip()) and not video.rhythm_notes


def apply_video_understanding(
    request: ScriptRequest, understander: VideoUnderstander
) -> tuple[ScriptRequest, bool]:
    if not needs_video_understanding(request.reference):
        return request, False
    if not request.reference.url:
        return request, False
    understood = _understand(understander, request.reference.url)
    merged = _merge(request.reference, understood)
    return request.model_copy(update={"reference": merged}), True


def apply_text_understanding(
    request: ScriptRequest, client: LLMClient
) -> tuple[ScriptRequest, bool]:
    if not needs_text_understanding(request.reference):
        return request, False
    understood = _understand_text(client, request.reference)
    merged = _merge(request.reference, understood, keep_transcript=True)
    return request.model_copy(update={"reference": merged}), True


def _understand(understander: VideoUnderstander, video_url: str) -> VideoUnderstanding:
    instruction = VIDEO_INSTRUCTION
    last_error: OutputError | None = None
    for _ in range(2):
        raw = understander.understand(video_url, instruction)
        try:
            return VideoUnderstanding.model_validate_json(_extract_json_object(raw))
        except ValidationError as exc:
            last_error = OutputError(
                f"视频理解结果不符合结构（{exc.error_count()} 处）"
            )
        except OutputError as exc:
            last_error = exc
        instruction = f"{VIDEO_INSTRUCTION}\n\n上次输出不合格，请只返回修正后的 JSON。问题：{last_error}"
    raise AgentError(f"两次视频理解都未通过校验：{last_error}") from last_error


def _understand_text(client: LLMClient, video: ReferenceVideo) -> VideoUnderstanding:
    instruction = TEXT_INSTRUCTION
    user_prompt = render_text_prompt(video)
    last_error: OutputError | None = None
    for _ in range(2):
        raw = client.complete(system_prompt=instruction, user_prompt=user_prompt)
        try:
            return VideoUnderstanding.model_validate_json(_extract_json_object(raw))
        except ValidationError as exc:
            last_error = OutputError(
                f"文本理解结果不符合结构（{exc.error_count()} 处）"
            )
        except OutputError as exc:
            last_error = exc
        instruction = f"{TEXT_INSTRUCTION}\n\n上次输出不合格，请只返回修正后的 JSON。问题：{last_error}"
        user_prompt = render_text_prompt(video)
    raise AgentError(f"两次文本理解都未通过校验：{last_error}") from last_error


def _merge(
    video: ReferenceVideo,
    understood: VideoUnderstanding,
    *,
    keep_transcript: bool = False,
) -> ReferenceVideo:
    duration = video.duration_seconds or understood.duration_seconds
    if video.rhythm_notes:
        notes = list(video.rhythm_notes)
    else:
        notes = list(understood.rhythm_notes)
        if (
            video.duration_seconds is not None
            and abs(video.duration_seconds - understood.duration_seconds)
            > TIME_TOLERANCE_SECONDS
        ):
            notes = _scale_notes(
                notes, understood.duration_seconds, video.duration_seconds
            )
            duration = video.duration_seconds
    hook = video.hook_type or understood.hook_type
    payload = video.model_dump()
    payload.update(
        {
            "duration_seconds": duration,
            "hook_type": hook.value,
            "transcript": (
                video.transcript
                if keep_transcript and video.transcript.strip()
                else understood.transcript or video.transcript
            ),
            "why_viral": video.why_viral or understood.why_viral,
            "rhythm_notes": [note.model_dump() for note in notes],
        }
    )
    try:
        return ReferenceVideo.model_validate(payload)
    except ValidationError:
        payload["rhythm_notes"] = []
        return ReferenceVideo.model_validate(payload)


def _scale_notes(
    notes: list[RhythmNote], source_duration: float, target_duration: float
) -> list[RhythmNote]:
    if not notes or source_duration <= 0:
        return []
    scale = target_duration / source_duration
    cursor = 0.0
    target = round(float(target_duration), 2)
    scaled: list[RhythmNote] = []
    for index, note in enumerate(notes):
        end = target if index == len(notes) - 1 else round(note.end_seconds * scale, 2)
        if end <= cursor:
            return []
        scaled.append(
            note.model_copy(update={"start_seconds": cursor, "end_seconds": end})
        )
        cursor = end
    return scaled


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
