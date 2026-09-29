"""把成稿交给 Seedance 2.0 生成竖屏短视频。只提交任务，不下载成片。"""

from __future__ import annotations

from typing import Protocol

from pydantic import Field

from guazi_script_agent.schemas import StrictModel, VideoScript

SEEDANCE_MIN_SECONDS = 4
SEEDANCE_MAX_SECONDS = 15
SHORT_VIDEO_RATIO = "9:16"
_PROMPT_LIMIT = 4000


class VideoGenerator(Protocol):
    model: str

    def submit(
        self, *, prompt: str, duration: int, ratio: str
    ) -> tuple[str, str | None]:
        """返回任务编号和创建时的状态。"""


class VideoTask(StrictModel):
    model: str = Field(min_length=1, max_length=80)
    task_id: str = Field(min_length=1, max_length=120)
    duration_seconds: int = Field(ge=SEEDANCE_MIN_SECONDS, le=SEEDANCE_MAX_SECONDS)
    ratio: str = Field(min_length=1, max_length=20)
    status: str | None = Field(default=None, max_length=40)
    prompt: str = Field(min_length=1, max_length=_PROMPT_LIMIT)


def clip_duration(seconds: float) -> int:
    """Seedance 2.0 成片时长是 4 到 15 秒。"""
    rounded = round(seconds)
    return min(SEEDANCE_MAX_SECONDS, max(SEEDANCE_MIN_SECONDS, rounded))


def script_to_prompt(script: VideoScript) -> str:
    lines = [
        "为瓜子二手车生成一条原创竖屏口播短视频。画面按下面的分镜，不要出现参考视频里的原句。",
        f"标题：{script.title}",
        f"开场：{script.opening_hook}",
    ]
    for beat in script.beats:
        lines.append(
            f"{beat.start_seconds:g}-{beat.end_seconds:g}秒，画面：{beat.visual}。口播：{beat.voiceover}"
        )
    lines.append(f"结尾：{script.cta}")
    text = "\n".join(lines).strip()
    if len(text) <= _PROMPT_LIMIT:
        return text
    return text[: _PROMPT_LIMIT - 1].rstrip() + "…"


def submit_script_video(script: VideoScript, generator: VideoGenerator) -> VideoTask:
    duration = clip_duration(script.target_duration_seconds)
    prompt = script_to_prompt(script)
    task_id, status = generator.submit(
        prompt=prompt, duration=duration, ratio=SHORT_VIDEO_RATIO
    )
    return VideoTask(
        model=generator.model,
        task_id=task_id,
        duration_seconds=duration,
        ratio=SHORT_VIDEO_RATIO,
        status=status,
        prompt=prompt,
    )
