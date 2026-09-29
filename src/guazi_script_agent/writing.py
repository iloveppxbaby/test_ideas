"""确定性口播草稿。

mock 提供方用它把结构换成瓜子自己的话。真实模型看到的是同一份提示词，不走这里。
语气字段留给模型；这里保持克制，不把 tone 原文念出来。
"""

from __future__ import annotations

import math

from guazi_script_agent.schemas import (
    BeatRole,
    DraftScript,
    GenerationContext,
    HookType,
    ShotBeat,
    StructuralBeat,
    ValuePoint,
)

_HOOK_LINES: dict[HookType, tuple[str, ...]] = {
    HookType.pain: ("怕车况不透明？先看{title}", "先看{title}", "{title}"),
    HookType.story: ("真要选车时，我先看{title}", "我先看{title}", "{title}"),
    HookType.number: ("看车先记一条：{title}", "先记{title}", "{title}"),
    HookType.contrast: ("价格先放一边，核对{title}", "先核对{title}", "{title}"),
    HookType.question: ("这台车还要不要看？先核对{title}", "先核对{title}", "{title}"),
}
_TITLE_LINES = {
    HookType.pain: "怕车况不透明，先看{title}",
    HookType.story: "选车时我先看{title}",
    HookType.number: "看车先记{title}",
    HookType.contrast: "别只比价格，先看{title}",
    HookType.question: "这台车看不看，先核对{title}",
}
_VISUALS = {
    BeatRole.hook: "竖屏近景，主播看镜头，字幕打出「{title}」。",
    BeatRole.build: "主播走到实车侧面，手势带出「{title}」。",
    BeatRole.proof: "手机特写车源详情，圈出与「{title}」相关的信息。",
    BeatRole.turn: "回到主播半身，语速放慢，一侧只留「{title}」。",
    BeatRole.cta: "主播指向底部，出现{brand}的预约看车按钮。",
}


def write_draft(context: GenerationContext) -> DraftScript:
    assignment = _assign(context.beats, context.value_points)
    beats: list[ShotBeat] = []
    for index, (spec, points) in enumerate(
        zip(context.beats, assignment, strict=True), start=1
    ):
        seconds = spec.end_seconds - spec.start_seconds
        beats.append(
            ShotBeat(
                index=index,
                start_seconds=spec.start_seconds,
                end_seconds=spec.end_seconds,
                role=spec.role,
                voiceover=_voiceover(
                    spec.role, context.hook_type, points, context.brand, seconds
                ),
                visual=_visual(spec.role, points, context.brand),
                subtitle=_subtitle(spec.role, points),
                value_point_ids=[point.id for point in points],
            )
        )
    primary = context.value_points[0]
    return DraftScript(
        title=_script_title(context.brand, context.hook_type, primary.title),
        target_duration_seconds=context.target_duration_seconds,
        opening_hook=beats[0].voiceover,
        beats=beats,
        cta=_cta_card(context.brand, context.value_points),
    )


def _assign(
    beats: list[StructuralBeat], points: list[ValuePoint]
) -> list[list[ValuePoint]]:
    buckets: list[list[ValuePoint]] = [[] for _ in beats]
    buckets[0].append(points[0])
    middle = list(range(1, len(beats) - 1))
    if not middle:
        buckets[0].extend(points[1:])
    else:
        ranked = sorted(
            middle,
            key=lambda index: beats[index].end_seconds - beats[index].start_seconds,
            reverse=True,
        )
        for index, point in enumerate(points):
            buckets[ranked[index % len(ranked)]].append(point)
        for slot in middle:
            if beats[slot].role == BeatRole.turn:
                buckets[slot] = list(points)
        for index, slot in enumerate(middle):
            if not buckets[slot]:
                buckets[slot].append(points[index % len(points)])
    buckets[-1] = list(points)
    return [_unique(bucket) for bucket in buckets]


def _voiceover(
    role: BeatRole,
    hook_type: HookType,
    points: list[ValuePoint],
    brand: str,
    seconds: float,
) -> str:
    limit = max(18, math.ceil(seconds * 8))
    if role == BeatRole.hook:
        title = points[0].title
        return _period(
            _fit([line.format(title=title) for line in _HOOK_LINES[hook_type]], limit)
        )
    if role == BeatRole.cta:
        return _period(
            _fit(
                (
                    f"打开{brand}，预约看车，试完再决定",
                    f"打开{brand}，预约看车再决定",
                    f"打开{brand}再看看",
                ),
                limit,
            )
        )
    if role == BeatRole.turn:
        titles = "、".join(point.title for point in points)
        return _period(_fit((f"下决定前再核对{titles}", points[0].title), limit))
    parts = [_period(_fit(_detail_lines(point), limit)) for point in points]
    if len(parts) == 1:
        return parts[0]
    joined = "".join(parts)
    if len(joined) <= limit:
        return joined
    return parts[0]


def _detail_lines(point: ValuePoint) -> tuple[str, ...]:
    if point.evidence:
        return (
            f"{point.title}，{point.description}。依据是{point.evidence}",
            f"{point.title}，{point.description}",
            point.title,
        )
    return (
        f"接着说{point.title}：{point.description}。发布前待核实",
        f"{point.title}：{point.description}",
        f"{point.title}。发布前待核实",
    )


def _cta_card(brand: str, points: list[ValuePoint]) -> str:
    audiences: list[str] = []
    for point in points:
        if point.audience not in audiences:
            audiences.append(point.audience)
    text = f"打开{brand}，面向「{'；'.join(audiences)}」筛选车源，预约看车，觉得不合适可以不买。"
    if len(text) <= 140:
        return text
    return f"打开{brand}，预约看车，觉得不合适可以不买。"


def _visual(role: BeatRole, points: list[ValuePoint], brand: str) -> str:
    title = _clip("、".join(point.title for point in points), 24)
    return _VISUALS[role].format(title=title, brand=brand)


def _subtitle(role: BeatRole, points: list[ValuePoint]) -> str:
    if role == BeatRole.cta:
        return "预约看车再决定"
    if len(points) == 1:
        return _clip(points[0].title, 16)
    joined = "、".join(point.title for point in points)
    if len(joined) <= 16:
        return joined
    return _clip(points[0].title, 16)


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _script_title(brand: str, hook_type: HookType, title: str) -> str:
    text = f"{brand}｜{_TITLE_LINES[hook_type].format(title=title)}"
    if len(text) <= 80:
        return text
    short = _TITLE_LINES[hook_type].format(title=title)
    if len(short) <= 80:
        return short
    return short[:79] + "…"


def _fit(options: tuple[str, ...] | list[str], limit: int) -> str:
    for option in options:
        if len(option) <= limit:
            return option
    return min(options, key=len)


def _period(text: str) -> str:
    stripped = text.strip().rstrip("，、；")
    if stripped.endswith(("。", "！", "？", "…")):
        return stripped
    return stripped + "。"


def _unique(points: list[ValuePoint]) -> list[ValuePoint]:
    result: list[ValuePoint] = []
    seen: set[str] = set()
    for point in points:
        if point.id in seen:
            continue
        seen.add(point.id)
        result.append(point)
    return result
