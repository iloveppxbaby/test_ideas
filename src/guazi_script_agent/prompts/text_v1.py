"""文本理解提示词 text-v1。

有转写、但还没有节奏时，用文本模型补结构。转写不会进入脚本提示词。
"""

from __future__ import annotations

from guazi_script_agent.schemas import ReferenceVideo

TEXT_PROMPT_VERSION = "text-v1"

TEXT_INSTRUCTION = """请根据给出的口播转写，整理这条短视频的讲法。只返回一个 JSON 对象，不要 Markdown。

字段：
- duration_seconds：视频时长（秒）。如果用户给了时长，就用那个时长
- hook_type：question、contrast、number、pain、story 之一
- rhythm_notes：2 到 12 条，从 0 秒覆盖到整段时长且首尾相接。每条含 start_seconds、end_seconds、shot、purpose
- transcript：原样回传用户给的转写，不要改写
- why_viral：用一句话说明手法，不要摘抄原句

规则：
1. shot 只写镜头功能，例如「近景提问」「快切证据」，禁止逐字引用口播。
2. purpose 用「开场钩子」「展开」「证明」「转折」「引导互动」这类词。
3. 不要评价瓜子，不要写新脚本。
"""


def render_text_prompt(video: ReferenceVideo) -> str:
    duration = (
        f"{video.duration_seconds:g}" if video.duration_seconds is not None else "未知"
    )
    return "\n".join(
        (
            f"时长：{duration} 秒",
            f"标题：{video.title}",
            "转写：",
            video.transcript.strip(),
            "只返回 JSON。",
        )
    )
