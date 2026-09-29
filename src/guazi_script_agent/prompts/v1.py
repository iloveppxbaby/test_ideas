"""v1 提示词。

行为变化时新增 v2 文件并切换 ``prompts/__init__.py`` 的导出，保留本文件。
提示词只携带结构与价值点，不携带参考视频原文。
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from guazi_script_agent.errors import OutputError
from guazi_script_agent.schemas import (
    DraftScript,
    GenerationContext,
    HookType,
    ReferenceStructure,
    ScriptRequest,
)

PROMPT_VERSION = "v1"
REQUEST_BEGIN = "<script-request-json>"
REQUEST_END = "</script-request-json>"

SYSTEM_PROMPT = """你是瓜子二手车的短视频脚本作者。参考视频只决定怎么讲：钩子类型、节拍时长和镜头密度。卖点决定讲什么。成稿必须是新的口播。

规则：
1. 禁止照搬参考视频的标题、口播、字幕、分镜措辞和爆火原因原文。本次用户消息故意不附带这些原文。
2. 价值点是品牌或车源卖点，不是社会新闻，也不是吃瓜段子。
3. 没有证据的卖点要说成待核实，不能写成已经生效的事实或承诺。
4. 有证据时只能复述证据里的事实，不能另加价格、事故结论或过户结果。
5. 不得使用价值点中列出的禁用表述，不做虚假承诺。
6. 用简体中文，口吻独立，句子要放进对应秒数。语气遵循价值点的 tone 字段，但不要把“语气”两个字念出来。
7. 只返回一个 JSON 对象，不要 Markdown。节拍的 index、起止时间和 role 必须与请求一致，每个价值点 id 至少出现一次。
"""

HOOK_GUIDE = {
    HookType.pain: "先点出购车顾虑，马上给一个可以核对的抓手。句子要新写。",
    HookType.story: "用一句新的选车场景开场，不要复述别人的经历。",
    HookType.number: "用条目感往下讲，不要照抄参考视频里的数字文案。",
    HookType.contrast: "先把只看价格的想法放下，再转到价值点。",
    HookType.question: "用一个新的判断题开场，下一句就落到价值点。",
}


def render_prompts(
    request: ScriptRequest, structure: ReferenceStructure
) -> tuple[str, str]:
    context = GenerationContext(
        prompt_version=PROMPT_VERSION,
        brand=request.value_points.brand,
        platform=request.reference.platform,
        target_duration_seconds=structure.duration_seconds,
        hook_type=structure.hook_type,
        shot_density_per_10s=structure.shot_density_per_10s,
        beats=structure.beats,
        value_points=request.value_points.value_points,
    )
    encoded = json.dumps(context.model_dump(mode="json"), ensure_ascii=False, indent=2)
    schema = json.dumps(DraftScript.model_json_schema(), ensure_ascii=False, indent=2)
    user = "\n".join(
        (
            "按下面的结构写一条原创口播。不要复述请求数据之外的参考文案；本次没有提供参考视频原文。",
            f"钩子写法：{HOOK_GUIDE[structure.hook_type]}",
            "请求数据：",
            REQUEST_BEGIN,
            encoded,
            REQUEST_END,
            "只输出一个 JSON 对象，字段遵循这个 JSON Schema：",
            schema,
        )
    )
    return SYSTEM_PROMPT, user


def parse_generation_context(user_prompt: str) -> GenerationContext:
    start = user_prompt.find(REQUEST_BEGIN)
    end = user_prompt.find(REQUEST_END)
    if start == -1 or end == -1 or end <= start:
        raise OutputError("提示词缺少脚本请求 JSON")
    payload = user_prompt[start + len(REQUEST_BEGIN) : end]
    try:
        return GenerationContext.model_validate_json(payload)
    except ValidationError as exc:
        raise OutputError(f"脚本请求 JSON 无法解析（{exc.error_count()} 处）") from exc
