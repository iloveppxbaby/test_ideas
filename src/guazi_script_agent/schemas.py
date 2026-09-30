"""脚本生成的输入、结构分析和成稿 schema。"""

from __future__ import annotations

from enum import Enum
from itertools import pairwise
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from guazi_script_agent.errors import AgentError

TIME_TOLERANCE_SECONDS = 0.05
MIN_DURATION_SECONDS = 3
MAX_DURATION_SECONDS = 600


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class HookType(str, Enum):
    """从参考视频推断出的钩子类型，只描述写法，不携带原文。"""

    question = "question"
    contrast = "contrast"
    number = "number"
    pain = "pain"
    story = "story"


class BeatRole(str, Enum):
    hook = "hook"
    build = "build"
    proof = "proof"
    turn = "turn"
    cta = "cta"


class ComplianceKind(str, Enum):
    unverified_claim = "unverified_claim"
    evidence_bound = "evidence_bound"
    forbidden_phrase = "forbidden_phrase"
    no_false_promise = "no_false_promise"


class RhythmNote(StrictModel):
    start_seconds: float = Field(ge=0, description="这一拍的开始时间（秒）")
    end_seconds: float = Field(gt=0, description="这一拍的结束时间（秒）")
    shot: str = Field(
        min_length=1, max_length=200, description="分镜或节奏描述，只作结构参考"
    )
    purpose: str = Field(
        min_length=1, max_length=80, description="这一拍在节奏上的作用"
    )

    @model_validator(mode="after")
    def end_after_start(self) -> RhythmNote:
        if self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds 必须大于 start_seconds")
        return self


class ReferenceVideo(StrictModel):
    """热点参考视频。原文只用于本地分析，不会写进成稿。"""

    title: str = Field(default="参考视频", min_length=1, max_length=80)
    platform: str = Field(default="url", min_length=1, max_length=40)
    duration_seconds: float | None = Field(
        default=None, ge=MIN_DURATION_SECONDS, le=MAX_DURATION_SECONDS
    )
    transcript: str = Field(default="", max_length=8000, description="口播或字幕转写")
    rhythm_notes: list[RhythmNote] = Field(default_factory=list)
    why_viral: str | None = Field(default=None, max_length=500)
    url: str | None = Field(default=None, max_length=2000)
    hook_type: HookType | None = None

    @field_validator("url")
    @classmethod
    def url_is_http(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url 必须是 http 或 https 链接")
        if parsed.username or parsed.password:
            raise ValueError("url 不能包含账号密码")
        return value

    @model_validator(mode="after")
    def needs_duration_or_url(self) -> ReferenceVideo:
        if self.duration_seconds is None and not self.url:
            raise ValueError("需要 duration_seconds，或提供视频 url")
        return self

    @model_validator(mode="after")
    def notes_cover_timeline(self) -> ReferenceVideo:
        notes = self.rhythm_notes
        if not notes:
            return self
        if not 2 <= len(notes) <= 12:
            raise ValueError("rhythm_notes 需要 2 到 12 条")
        if self.duration_seconds is None:
            raise ValueError("有节奏要点时必须提供 duration_seconds")
        if notes[0].start_seconds > TIME_TOLERANCE_SECONDS:
            raise ValueError("rhythm_notes 必须从 0 秒开始")
        for previous, current in pairwise(notes):
            gap = current.start_seconds - previous.end_seconds
            if abs(gap) > TIME_TOLERANCE_SECONDS:
                raise ValueError("rhythm_notes 必须首尾相接且不能重叠")
        if abs(notes[-1].end_seconds - self.duration_seconds) > TIME_TOLERANCE_SECONDS:
            raise ValueError("rhythm_notes 的结束时间必须等于 duration_seconds")
        return self


class ValuePoint(StrictModel):
    """一条瓜子卖点。evidence 为空时，成稿必须标成待核实。"""

    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=300)
    evidence: str | None = Field(default=None, max_length=300)
    audience: str = Field(min_length=1, max_length=80)
    tone: str = Field(min_length=1, max_length=40)
    forbidden_phrases: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("id")
    @classmethod
    def id_has_no_whitespace(cls, value: str) -> str:
        if any(char.isspace() for char in value):
            raise ValueError("id 不能包含空白")
        return value

    @field_validator("evidence")
    @classmethod
    def blank_evidence_is_missing(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("forbidden_phrases")
    @classmethod
    def clean_forbidden_phrases(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            text = item.strip()
            if not text:
                continue
            if not 2 <= len(text) <= 40:
                raise ValueError("禁用表述长度需要在 2 到 40 个字符")
            cleaned.append(text)
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("禁用表述不能重复")
        return cleaned


class ValuePointSet(StrictModel):
    brand: str = Field(default="瓜子二手车", min_length=1, max_length=40)
    value_points: list[ValuePoint] = Field(min_length=1, max_length=8)
    target_duration_seconds: float | None = Field(
        default=None,
        ge=MIN_DURATION_SECONDS,
        le=MAX_DURATION_SECONDS,
    )

    @model_validator(mode="after")
    def ids_are_unique(self) -> ValuePointSet:
        identifiers = [item.id for item in self.value_points]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("value_points.id 必须唯一")
        return self


class ScriptRequest(StrictModel):
    reference: ReferenceVideo
    value_points: ValuePointSet
    target_duration_seconds: float | None = Field(
        default=None,
        ge=MIN_DURATION_SECONDS,
        le=MAX_DURATION_SECONDS,
    )

    def resolved_duration(self) -> float:
        """CLI 覆盖文件，文件覆盖参考视频时长。"""
        if self.target_duration_seconds is not None:
            return self.target_duration_seconds
        if self.value_points.target_duration_seconds is not None:
            return self.value_points.target_duration_seconds
        if self.reference.duration_seconds is None:
            raise AgentError(
                "参考视频缺少时长。请提供 duration_seconds，或传入 mp4 直链。"
            )
        return self.reference.duration_seconds


class StructuralBeat(StrictModel):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    role: BeatRole

    @model_validator(mode="after")
    def end_after_start(self) -> StructuralBeat:
        if self.end_seconds <= self.start_seconds:
            raise ValueError("结构节拍的结束时间必须晚于开始时间")
        return self


class ReferenceStructure(StrictModel):
    """从参考视频抽出、可以安全交给模型的结构。不含原文。"""

    hook_type: HookType
    duration_seconds: float = Field(ge=MIN_DURATION_SECONDS, le=MAX_DURATION_SECONDS)
    beat_count: int = Field(ge=2, le=12)
    shot_density_per_10s: float = Field(gt=0)
    beats: list[StructuralBeat] = Field(min_length=2, max_length=12)

    @model_validator(mode="after")
    def count_matches_beats(self) -> ReferenceStructure:
        if len(self.beats) != self.beat_count:
            raise ValueError("beat_count 与 beats 长度不一致")
        return self


class GenerationContext(StrictModel):
    """写进 v1 提示词的全部生成上下文。故意不包含参考文案。"""

    prompt_version: Literal["v1"]
    brand: str
    platform: str
    target_duration_seconds: float = Field(
        ge=MIN_DURATION_SECONDS, le=MAX_DURATION_SECONDS
    )
    hook_type: HookType
    shot_density_per_10s: float = Field(gt=0)
    beats: list[StructuralBeat] = Field(min_length=2, max_length=12)
    value_points: list[ValuePoint] = Field(min_length=1, max_length=8)


class ShotBeat(StrictModel):
    index: int = Field(ge=1)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    role: BeatRole
    voiceover: str = Field(min_length=1, max_length=400)
    visual: str = Field(min_length=1, max_length=300)
    subtitle: str = Field(min_length=1, max_length=40)
    value_point_ids: list[str] = Field(default_factory=list)


class ComplianceNote(StrictModel):
    kind: ComplianceKind
    message: str = Field(min_length=1, max_length=500)
    related_value_point_ids: list[str] = Field(default_factory=list)


class StructureBorrowed(StrictModel):
    hook_type: HookType
    beat_count: int
    shot_density_per_10s: float
    source_duration_seconds: float
    timing_scaled: bool


def validate_timeline(beats: list[ShotBeat], duration: float) -> None:
    if len(beats) < 2:
        raise ValueError("至少需要两个分镜")
    if beats[0].start_seconds > TIME_TOLERANCE_SECONDS:
        raise ValueError("分镜必须从 0 秒开始")
    if beats[0].role != BeatRole.hook:
        raise ValueError("第一镜角色必须是 hook")
    if beats[-1].role != BeatRole.cta:
        raise ValueError("最后一镜角色必须是 cta")
    for expected, beat in enumerate(beats, start=1):
        if beat.index != expected:
            raise ValueError("分镜 index 必须从 1 连续递增")
        if beat.end_seconds <= beat.start_seconds:
            raise ValueError("分镜结束时间必须晚于开始时间")
    for previous, current in pairwise(beats):
        if abs(current.start_seconds - previous.end_seconds) > TIME_TOLERANCE_SECONDS:
            raise ValueError("分镜时间必须首尾相接")
    if abs(beats[-1].end_seconds - duration) > TIME_TOLERANCE_SECONDS:
        raise ValueError("最后一镜结束时间必须等于目标时长")


class DraftScript(BaseModel):
    """模型返回的草稿。合规备注由代码后处理补上，不交给模型填写。"""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=80)
    target_duration_seconds: float = Field(
        ge=MIN_DURATION_SECONDS, le=MAX_DURATION_SECONDS
    )
    opening_hook: str = Field(min_length=1, max_length=200)
    beats: list[ShotBeat] = Field(min_length=2, max_length=12)
    cta: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def timeline_is_valid(self) -> DraftScript:
        validate_timeline(self.beats, self.target_duration_seconds)
        return self


class VideoScript(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    prompt_version: str = Field(min_length=1, max_length=20)
    provider: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=80)
    target_duration_seconds: float = Field(
        ge=MIN_DURATION_SECONDS, le=MAX_DURATION_SECONDS
    )
    opening_hook: str = Field(min_length=1, max_length=200)
    beats: list[ShotBeat] = Field(min_length=2, max_length=12)
    cta: str = Field(min_length=1, max_length=200)
    compliance_notes: list[ComplianceNote] = Field(min_length=1, max_length=30)
    structure_borrowed: StructureBorrowed
    source_url: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def timeline_is_valid(self) -> VideoScript:
        validate_timeline(self.beats, self.target_duration_seconds)
        return self
