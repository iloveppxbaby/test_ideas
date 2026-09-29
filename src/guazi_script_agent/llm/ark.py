"""火山方舟（豆包）客户端。每个 Ark 实例只绑定一个 model。"""

from __future__ import annotations

import os
from typing import Any

from guazi_script_agent.errors import AgentError

ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_TEXT_MODEL = "doubao-seed-2-0-lite-260428"
DEFAULT_VIDEO_UNDERSTANDING_MODEL = "doubao-seed-2-1-pro"
DEFAULT_VIDEO_GENERATION_MODEL = "doubao-seedance-2-0-260128"
_VIDEO_FPS = 1


class ArkBoundClient:
    """一个实例对应一个模型。文本理解与脚本生成可以共用同一个文本模型实例。"""

    name = "ark"

    def __init__(self, *, model: str, sdk: Any) -> None:
        self.model = model
        self._sdk = sdk

    def __repr__(self) -> str:
        return f"ArkBoundClient(model={self.model!r})"

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self._create(messages, temperature=0.2)

    def understand(self, video_url: str, instruction: str) -> str:
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "video_url",
                        "video_url": {"url": video_url, "fps": _VIDEO_FPS},
                    },
                    {"type": "text", "text": instruction},
                ],
            }
        ]
        return self._create(messages, temperature=0.1)

    def _create(self, messages: list[dict[str, Any]], *, temperature: float) -> str:
        try:
            response = self._sdk.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
            )
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError(f"豆包请求失败：{exc.__class__.__name__}") from exc
        return _message_text(response)


class ArkVideoGenerationClient:
    """Seedance 2.0。这个实例只提交视频生成任务，不负责理解和写脚本。"""

    name = "ark-seedance"

    def __init__(self, *, model: str, sdk: Any) -> None:
        self.model = model
        self._sdk = sdk

    def __repr__(self) -> str:
        return f"ArkVideoGenerationClient(model={self.model!r})"

    def submit(
        self, *, prompt: str, duration: int, ratio: str
    ) -> tuple[str, str | None]:
        try:
            response = self._sdk.content_generation.tasks.create(
                model=self.model,
                content=[{"type": "text", "text": prompt}],
                ratio=ratio,
                duration=duration,
                resolution="720p",
                watermark=False,
            )
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError(f"Seedance 请求失败：{exc.__class__.__name__}") from exc
        task_id = getattr(response, "id", None)
        if task_id is None and isinstance(response, dict):
            task_id = response.get("id")
        if not task_id:
            raise AgentError("Seedance 没有返回任务编号")
        status = getattr(response, "status", None)
        if status is None and isinstance(response, dict):
            status = response.get("status")
        return str(task_id), None if status is None else str(status)


def create_ark_script_client(
    *,
    model: str | None = None,
    base_url: str | None = None,
    sdk: Any | None = None,
) -> ArkBoundClient:
    resolved = _resolve_model(model, "ARK_SCRIPT_MODEL", DEFAULT_TEXT_MODEL)
    return ArkBoundClient(model=resolved, sdk=sdk or _load_sdk(base_url))


def create_ark_video_client(
    *,
    model: str | None = None,
    base_url: str | None = None,
    sdk: Any | None = None,
) -> ArkBoundClient:
    resolved = _resolve_model(
        model, "ARK_VIDEO_MODEL", DEFAULT_VIDEO_UNDERSTANDING_MODEL
    )
    return ArkBoundClient(model=resolved, sdk=sdk or _load_sdk(base_url))


def create_ark_video_generation_client(
    *,
    model: str | None = None,
    base_url: str | None = None,
    sdk: Any | None = None,
) -> ArkVideoGenerationClient:
    resolved = _resolve_model(
        model, "ARK_VIDEO_GEN_MODEL", DEFAULT_VIDEO_GENERATION_MODEL
    )
    return ArkVideoGenerationClient(model=resolved, sdk=sdk or _load_sdk(base_url))


def _resolve_model(model: str | None, env_name: str, default: str) -> str:
    _require_api_key()
    resolved = (model or os.environ.get(env_name, "")).strip()
    return resolved or default


def _require_api_key() -> str:
    api_key = os.environ.get("GUAZI_LLM_API_KEY", "").strip()
    if not api_key:
        raise AgentError("未设置环境变量 GUAZI_LLM_API_KEY，已拒绝调用豆包。")
    return api_key


def _load_sdk(base_url: str | None) -> Any:
    api_key = _require_api_key()
    resolved_url = (base_url or os.environ.get("ARK_BASE_URL", ARK_BASE_URL)).rstrip(
        "/"
    )
    try:
        from volcenginesdkarkruntime import Ark
    except ImportError as exc:
        raise AgentError(
            "未安装火山方舟 SDK。请执行 pip install 'volcengine-python-sdk[ark]'。"
        ) from exc
    return Ark(base_url=resolved_url, api_key=api_key)


def _message_text(response: Any) -> str:
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as exc:
        raise AgentError("豆包响应里没有可用的消息正文") from exc
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        texts: list[str] = []
        for part in content:
            if isinstance(part, str):
                texts.append(part)
            elif isinstance(part, dict) and part.get("text"):
                texts.append(str(part["text"]))
            else:
                text = getattr(part, "text", None)
                if text:
                    texts.append(str(text))
        joined = "".join(texts).strip()
        if joined:
            return joined
    raise AgentError("豆包返回了空正文")
