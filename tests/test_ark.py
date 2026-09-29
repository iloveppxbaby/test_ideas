from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from guazi_script_agent.agent import generate_script
from guazi_script_agent.errors import AgentError
from guazi_script_agent.llm.ark import (
    DEFAULT_TEXT_MODEL,
    DEFAULT_VIDEO_GENERATION_MODEL,
    DEFAULT_VIDEO_UNDERSTANDING_MODEL,
    ArkBoundClient,
    ArkVideoGenerationClient,
    create_ark_script_client,
    create_ark_video_client,
    create_ark_video_generation_client,
)
from guazi_script_agent.llm.mock import MockLLMClient
from guazi_script_agent.schemas import ReferenceVideo, ScriptRequest
from guazi_script_agent.video_gen import submit_script_video

EXAMPLE_URL = (
    "https://image-public.guazistatic.com/"
    "qnbdp1066x7663b97e86e74da7a2c2a1573267fef41788427623.mp4"
)
TRANSCRIPT = "这是只允许出现在查重里的模型转写句子甲乙丙丁戊己。"


class _Completions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, object]] = []

    def create(
        self, *, model: str, messages: list[dict[str, object]], temperature: float
    ):
        self.calls.append(
            {"model": model, "messages": messages, "temperature": temperature}
        )
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class _Sdk:
    def __init__(self, content: str) -> None:
        self.completions = _Completions(content)
        self.chat = self


def _understanding(duration: float = 12) -> str:
    scale = duration / 12
    notes = [
        (0, 3, "近景提问", "开场钩子"),
        (3, 9, "展示证据", "证明"),
        (9, 12, "指向行动", "引导互动"),
    ]
    return json.dumps(
        {
            "duration_seconds": duration,
            "hook_type": "pain",
            "rhythm_notes": [
                {
                    "start_seconds": round(start * scale, 2),
                    "end_seconds": round(end * scale, 2),
                    "shot": shot,
                    "purpose": purpose,
                }
                for start, end, shot, purpose in notes
            ],
            "transcript": TRANSCRIPT,
            "why_viral": "先点出顾虑再给抓手",
        },
        ensure_ascii=False,
    )


def test_video_client_sends_url_and_script_client_stays_text() -> None:
    video_sdk = _Sdk(_understanding())
    script_sdk = _Sdk("{}")
    video = ArkBoundClient(model="ep-video", sdk=video_sdk)
    script = ArkBoundClient(model="ep-script", sdk=script_sdk)
    assert video.model != script.model
    video.understand(EXAMPLE_URL, "只分析结构")
    script.complete(system_prompt="系统", user_prompt="写脚本")
    video_call = video_sdk.completions.calls[0]
    content = video_call["messages"][0]["content"]
    assert video_call["model"] == "ep-video"
    assert content[0]["type"] == "video_url"
    assert content[0]["video_url"] == {"url": EXAMPLE_URL, "fps": 1}
    assert content[1]["text"] == "只分析结构"
    script_call = script_sdk.completions.calls[0]
    assert script_call["model"] == "ep-script"
    assert script_call["messages"][1]["content"] == "写脚本"
    assert "video_url" not in json.dumps(script_call["messages"])


def test_understanding_transcript_never_enters_script_prompt(example_request) -> None:
    class Recorder:
        name = "mock"

        def __init__(self) -> None:
            self.inner = MockLLMClient()
            self.user = ""

        def complete(self, *, system_prompt: str, user_prompt: str) -> str:
            self.user = user_prompt
            return self.inner.complete(
                system_prompt=system_prompt, user_prompt=user_prompt
            )

    class Understander:
        def understand(self, video_url: str, instruction: str) -> str:
            assert video_url == EXAMPLE_URL
            assert "查重" in instruction
            return _understanding(24)

    reference = ReferenceVideo(
        url=EXAMPLE_URL,
        duration_seconds=12,
        transcript="",
        platform="url",
    )
    request = ScriptRequest(
        reference=reference, value_points=example_request.value_points
    )
    recorder = Recorder()
    script = generate_script(request, llm=recorder, understander=Understander())
    assert script.prompt_version == "v1+video-v1"
    assert script.source_url == EXAMPLE_URL
    assert script.structure_borrowed.hook_type.value == "pain"
    assert script.structure_borrowed.source_duration_seconds == 12
    assert script.beats[-1].end_seconds == 12
    assert TRANSCRIPT not in recorder.user
    assert EXAMPLE_URL not in recorder.user
    assert TRANSCRIPT not in script.opening_hook
    assert "ep-" not in script.model_dump_json()


def test_explicit_hook_and_rhythm_stay_when_transcript_is_filled(
    example_request,
) -> None:
    reference = ReferenceVideo(
        url=EXAMPLE_URL,
        duration_seconds=12,
        transcript="",
        hook_type="question",
        rhythm_notes=[
            {
                "start_seconds": 0,
                "end_seconds": 6,
                "shot": "近景提问",
                "purpose": "开场钩子",
            },
            {
                "start_seconds": 6,
                "end_seconds": 12,
                "shot": "指向行动",
                "purpose": "引导互动",
            },
        ],
    )

    class Understander:
        def understand(self, video_url: str, instruction: str) -> str:
            return _understanding(24)

    script = generate_script(
        ScriptRequest(reference=reference, value_points=example_request.value_points),
        llm=MockLLMClient(),
        understander=Understander(),
    )
    assert script.structure_borrowed.hook_type.value == "question"
    assert script.structure_borrowed.beat_count == 2
    assert script.beats[-1].end_seconds == 12


def test_text_understanding_uses_transcript_and_keeps_it_out_of_script(
    example_request,
) -> None:
    class TextThenScript:
        name = "ark"

        def __init__(self) -> None:
            self.inner = MockLLMClient()
            self.prompts: list[str] = []

        def complete(self, *, system_prompt: str, user_prompt: str) -> str:
            self.prompts.append(user_prompt)
            if len(self.prompts) == 1:
                assert TRANSCRIPT in user_prompt
                return _understanding(12)
            return self.inner.complete(
                system_prompt=system_prompt, user_prompt=user_prompt
            )

    reference = ReferenceVideo(
        duration_seconds=12,
        transcript=TRANSCRIPT,
        platform="douyin",
        title="参考视频",
    )
    client = TextThenScript()
    script = generate_script(
        ScriptRequest(reference=reference, value_points=example_request.value_points),
        llm=client,
    )
    assert script.prompt_version == "v1+text-v1"
    assert script.structure_borrowed.hook_type.value == "pain"
    assert len(client.prompts) == 2
    assert TRANSCRIPT not in client.prompts[1]
    assert TRANSCRIPT not in script.opening_hook


def test_ark_reads_guazi_key_and_default_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GUAZI_LLM_API_KEY", raising=False)
    monkeypatch.setenv("ARK_API_KEY", "legacy-key")
    with pytest.raises(AgentError, match="GUAZI_LLM_API_KEY"):
        create_ark_script_client(sdk=_Sdk("{}"))
    monkeypatch.setenv("GUAZI_LLM_API_KEY", "test-key")
    for name in ("ARK_SCRIPT_MODEL", "ARK_VIDEO_MODEL", "ARK_VIDEO_GEN_MODEL"):
        monkeypatch.delenv(name, raising=False)
    sdk = _Sdk("{}")
    script = create_ark_script_client(sdk=sdk)
    video = create_ark_video_client(sdk=sdk)
    generation = create_ark_video_generation_client(sdk=sdk)
    assert script.model == DEFAULT_TEXT_MODEL
    assert video.model == DEFAULT_VIDEO_UNDERSTANDING_MODEL
    assert generation.model == DEFAULT_VIDEO_GENERATION_MODEL
    assert script.model != video.model != generation.model
    assert "test-key" not in repr(script)
    assert "legacy-key" not in repr(generation)
    monkeypatch.setenv("ARK_SCRIPT_MODEL", "ep-script")
    assert create_ark_script_client(sdk=sdk).model == "ep-script"


def test_seedance_submits_text_prompt(example_request) -> None:
    class _Tasks:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def create(self, **kwargs: object):
            self.calls.append(kwargs)
            return SimpleNamespace(id="cgt-1", status="queued")

    class _SdkGen:
        def __init__(self) -> None:
            self.content_generation = SimpleNamespace(tasks=_Tasks())

    sdk = _SdkGen()
    client = ArkVideoGenerationClient(model=DEFAULT_VIDEO_GENERATION_MODEL, sdk=sdk)
    script = generate_script(example_request)
    task = submit_script_video(script, client)
    call = sdk.content_generation.tasks.calls[0]
    assert task.task_id == "cgt-1"
    assert task.model == DEFAULT_VIDEO_GENERATION_MODEL
    assert task.duration_seconds == 15
    assert task.ratio == "9:16"
    assert call["model"] == DEFAULT_VIDEO_GENERATION_MODEL
    assert call["content"] == [{"type": "text", "text": task.prompt}]
    assert "video_url" not in json.dumps(call)
    assert example_request.reference.transcript not in task.prompt


def test_missing_sdk_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GUAZI_LLM_API_KEY", "test-key")
    monkeypatch.delenv("ARK_SCRIPT_MODEL", raising=False)
    real_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "volcenginesdkarkruntime":
            raise ImportError("nope")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)
    with pytest.raises(AgentError, match="未安装"):
        create_ark_script_client()
