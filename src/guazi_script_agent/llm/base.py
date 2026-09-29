"""可替换的补全接口。实现只接收提示词，不接收参考视频原文。"""

from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    name: str

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        """返回 DraftScript 的 JSON 文本。"""
