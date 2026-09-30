"""把成稿渲染成 JSON 和给编导看的 Markdown。"""

from __future__ import annotations

import json

from guazi_script_agent.schemas import VideoScript


def render_json(script: VideoScript) -> str:
    payload = script.model_dump(mode="json", exclude_none=True)
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def render_markdown(script: VideoScript) -> str:
    borrowed = script.structure_borrowed
    lines = [
        f"# {script.title}",
        "",
        f"- 目标时长：{format_seconds(script.target_duration_seconds)} 秒",
        f"- 开场钩子：{script.opening_hook}",
        (
            f"- 借用结构：{borrowed.hook_type.value}，{borrowed.beat_count} 个节拍，"
            f"每 10 秒约 {format_seconds(borrowed.shot_density_per_10s)} 个镜头"
        ),
        f"- 提示词版本：{script.prompt_version}",
        f"- 生成器：{script.provider}",
        *([f"- 参考视频：{script.source_url}"] if script.source_url else []),
        "",
        "## 分镜",
        "",
    ]
    for beat in script.beats:
        identifiers = "、".join(beat.value_point_ids) if beat.value_point_ids else "无"
        lines.extend(
            (
                f"### {beat.index}. {format_seconds(beat.start_seconds)}–{format_seconds(beat.end_seconds)} 秒 · {beat.role.value}",
                "",
                f"- 口播：{beat.voiceover}",
                f"- 画面：{beat.visual}",
                f"- 字幕：{beat.subtitle}",
                f"- 价值点：{identifiers}",
                "",
            )
        )
    lines.extend(("## 行动号召", "", script.cta, "", "## 合规备注", ""))
    for note in script.compliance_notes:
        lines.append(f"- [{note.kind.value}] {note.message}")
    lines.append("")
    return "\n".join(lines)


def format_seconds(value: float) -> str:
    rounded = round(float(value), 2)
    return f"{rounded:.2f}".rstrip("0").rstrip(".")
