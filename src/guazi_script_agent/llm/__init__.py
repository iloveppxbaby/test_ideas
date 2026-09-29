"""生成器工厂。默认 mock，openai 只有在显式选择且配置了密钥时才会创建。"""

from __future__ import annotations

import os

from guazi_script_agent.errors import AgentError
from guazi_script_agent.llm.base import LLMClient
from guazi_script_agent.llm.mock import MockLLMClient
from guazi_script_agent.llm.openai_compatible import OpenAICompatibleClient

__all__ = ["LLMClient", "create_client"]


def create_client(
    provider: str, *, model: str | None = None, base_url: str | None = None
) -> LLMClient:
    if provider == "mock":
        return MockLLMClient()
    if provider == "openai":
        api_key = os.environ.get("GUAZI_LLM_API_KEY", "").strip()
        if not api_key:
            raise AgentError("未设置环境变量 GUAZI_LLM_API_KEY，已拒绝调用外部模型。")
        resolved_model = model or os.environ.get("GUAZI_LLM_MODEL", "gpt-4o-mini")
        resolved_url = base_url or os.environ.get(
            "GUAZI_LLM_BASE_URL", "https://api.openai.com/v1"
        )
        return OpenAICompatibleClient(
            api_key=api_key, model=resolved_model, base_url=resolved_url
        )
    raise AgentError(f"未知生成器：{provider}")
