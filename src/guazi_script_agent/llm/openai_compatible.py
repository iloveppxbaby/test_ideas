"""OpenAI 兼容 Chat Completions 客户端。

测试和示例都不会实例化它。未设置密钥时工厂会直接拒绝。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from guazi_script_agent.errors import AgentError


class OpenAICompatibleClient:
    name = "openai"

    def __init__(
        self, *, api_key: str, model: str, base_url: str, timeout: float = 60
    ) -> None:
        self._api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def __repr__(self) -> str:
        return (
            f"OpenAICompatibleClient(model={self.model!r}, base_url={self.base_url!r})"
        )

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise AgentError(f"外部模型返回 HTTP {exc.code}：{detail}") from exc
        except urllib.error.URLError as exc:
            raise AgentError(f"外部模型请求失败：{exc.reason}") from exc
        try:
            content = json.loads(body)["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise AgentError("外部模型响应里没有可用的消息正文") from exc
        if not isinstance(content, str) or not content.strip():
            raise AgentError("外部模型返回了空正文")
        return content
