"""生成器工厂。默认 mock。openai 与豆包都要显式选择，且没有密钥就拒绝。"""

from __future__ import annotations

import os

from guazi_script_agent.errors import AgentError
from guazi_script_agent.llm.ark import (
    create_ark_script_client,
    create_ark_video_client,
    create_ark_video_generation_client,
)
from guazi_script_agent.llm.base import LLMClient
from guazi_script_agent.llm.mock import MockLLMClient
from guazi_script_agent.llm.openai_compatible import OpenAICompatibleClient
from guazi_script_agent.local_env import ensure_local_api_key

__all__ = [
    "LLMClient",
    "create_client",
    "create_video_client",
    "create_video_generation_client",
]


def create_client(
    provider: str, *, model: str | None = None, base_url: str | None = None
) -> LLMClient:
    if provider == "mock":
        return MockLLMClient()
    if provider == "openai":
        api_key = ensure_local_api_key()
        if not api_key:
            raise AgentError(
                "未找到 GUAZI_LLM_API_KEY。请在本机 ~/.bashrc 写入 "
                'export GUAZI_LLM_API_KEY="..."，然后在本机终端运行。'
            )
        resolved_model = model or os.environ.get("GUAZI_LLM_MODEL", "gpt-4o-mini")
        resolved_url = base_url or os.environ.get(
            "GUAZI_LLM_BASE_URL", "https://api.openai.com/v1"
        )
        return OpenAICompatibleClient(
            api_key=api_key, model=resolved_model, base_url=resolved_url
        )
    if provider == "ark":
        return create_ark_script_client(model=model, base_url=base_url)
    raise AgentError(f"未知生成器：{provider}")


def create_video_client(
    provider: str, *, model: str | None = None, base_url: str | None = None
):
    if provider == "ark":
        return create_ark_video_client(model=model, base_url=base_url)
    raise AgentError("只有豆包提供方会调用视频理解模型。")


def create_video_generation_client(
    provider: str, *, model: str | None = None, base_url: str | None = None
):
    if provider == "ark":
        return create_ark_video_generation_client(model=model, base_url=base_url)
    raise AgentError("视频生成只使用豆包 Seedance 2.0。")
