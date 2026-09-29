"""离线生成器。解析 v1 提示词里的结构数据，不读取参考文案。"""

from __future__ import annotations

import json

from guazi_script_agent.errors import OutputError
from guazi_script_agent.prompts import parse_generation_context
from guazi_script_agent.writing import write_draft


class MockLLMClient:
    name = "mock"

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        if "禁止照搬" not in system_prompt:
            raise OutputError("系统提示缺少原创约束")
        context = parse_generation_context(user_prompt)
        draft = write_draft(context)
        return json.dumps(draft.model_dump(mode="json"), ensure_ascii=False)
