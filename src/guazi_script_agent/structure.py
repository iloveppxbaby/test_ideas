"""从参考视频提取钩子类型、节拍角色和时间轴，不保留原文。"""

from __future__ import annotations

from guazi_script_agent.errors import AgentError
from guazi_script_agent.schemas import (
    BeatRole,
    HookType,
    ReferenceStructure,
    ReferenceVideo,
    StructuralBeat,
)

# 命中即停。靠前的类型优先，避免一句文案同时像故事又像清单时摇摆。
_HOOK_RULES: tuple[tuple[HookType, tuple[str, ...]], ...] = (
    (HookType.pain, ("痛点", "踩坑", "吃亏", "害怕", "怕买")),
    (HookType.story, ("故事", "经历", "代入", "我去年")),
    (HookType.number, ("清单", "三条", "三个", "几个", "数字")),
    (HookType.contrast, ("反差", "对比", "别只看", "反过来")),
    (HookType.question, ("疑问", "为什么", "谁懂", "？", "?")),
)
_PROOF_TOKENS = ("证明", "证据", "清单", "展示", "干货", "proof")
_TURN_TOKENS = ("转折", "反转", "收束", "turn")


def infer_hook_type(video: ReferenceVideo) -> HookType:
    chunks = [video.title, video.why_viral or "", _first_sentence(video.transcript)]
    if video.rhythm_notes:
        first = video.rhythm_notes[0]
        chunks.extend((first.shot, first.purpose))
    corpus = "\n".join(chunks)
    for hook_type, words in _HOOK_RULES:
        if any(word in corpus for word in words):
            return hook_type
    return HookType.question


def extract_structure(
    video: ReferenceVideo, target_duration: float
) -> ReferenceStructure:
    if video.rhythm_notes:
        beats = _beats_from_notes(video, target_duration)
    else:
        beats = _synthesize_beats(target_duration)
    density = round(len(beats) * 10 / target_duration, 2)
    return ReferenceStructure(
        hook_type=video.hook_type or infer_hook_type(video),
        duration_seconds=round(float(target_duration), 2),
        beat_count=len(beats),
        shot_density_per_10s=density,
        beats=beats,
    )


def _first_sentence(text: str) -> str:
    for index, char in enumerate(text):
        if char in "。！？!?":
            return text[:index]
    return text[:80]


def _role_for(purpose: str, index: int, total: int) -> BeatRole:
    if index == 0:
        return BeatRole.hook
    if index == total - 1:
        return BeatRole.cta
    if any(token in purpose.lower() for token in _PROOF_TOKENS):
        return BeatRole.proof
    if any(token in purpose.lower() for token in _TURN_TOKENS):
        return BeatRole.turn
    return BeatRole.build


def _beats_from_notes(
    video: ReferenceVideo, target_duration: float
) -> list[StructuralBeat]:
    source_duration = video.duration_seconds
    if source_duration is None:
        raise AgentError("参考视频缺少时长")
    scale = target_duration / source_duration
    total = len(video.rhythm_notes)
    raw: list[tuple[float, BeatRole]] = []
    for index, note in enumerate(video.rhythm_notes):
        raw.append((note.end_seconds * scale, _role_for(note.purpose, index, total)))
    return _chain_beats(raw, target_duration)


def _synthesize_beats(duration: float) -> list[StructuralBeat]:
    count = max(3, min(8, round(duration / 5)))
    target = round(float(duration), 2)
    edges = [round(target * index / count, 2) for index in range(count + 1)]
    edges[0] = 0.0
    edges[-1] = target
    for index in range(1, len(edges)):
        if edges[index] <= edges[index - 1]:
            edges[index] = round(edges[index - 1] + 0.01, 2)
    edges[-1] = target
    if edges[-1] <= edges[-2]:
        raise AgentError("目标时长过短，无法拆出开场和结尾")
    roles = [BeatRole.hook]
    cycle = (BeatRole.build, BeatRole.proof, BeatRole.turn)
    for index in range(1, count - 1):
        roles.append(cycle[(index - 1) % len(cycle)])
    roles.append(BeatRole.cta)
    return [
        StructuralBeat(
            start_seconds=edges[index], end_seconds=edges[index + 1], role=roles[index]
        )
        for index in range(count)
    ]


def _chain_beats(
    raw_ends: list[tuple[float, BeatRole]], target_duration: float
) -> list[StructuralBeat]:
    target = round(float(target_duration), 2)
    beats: list[StructuralBeat] = []
    cursor = 0.0
    last = len(raw_ends) - 1
    for index, (end, role) in enumerate(raw_ends):
        end_at = target if index == last else round(end, 2)
        if end_at <= cursor:
            raise AgentError("节拍时长被缩成 0，请减少节奏要点或增加目标时长")
        beats.append(
            StructuralBeat(start_seconds=cursor, end_seconds=end_at, role=role)
        )
        cursor = end_at
    return beats
