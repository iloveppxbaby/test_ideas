"""共用夹具。测试期间禁止真正打开网络。"""

from __future__ import annotations

import urllib.request
from pathlib import Path

import pytest

from guazi_script_agent.schemas import ReferenceVideo, ScriptRequest, ValuePointSet

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("测试禁止访问网络")

    monkeypatch.setattr(urllib.request, "urlopen", explode)


@pytest.fixture
def example_request() -> ScriptRequest:
    reference = ReferenceVideo.model_validate_json(
        (ROOT / "examples/reference_video.json").read_text(encoding="utf-8")
    )
    points = ValuePointSet.model_validate_json(
        (ROOT / "examples/value_points.json").read_text(encoding="utf-8")
    )
    return ScriptRequest(reference=reference, value_points=points)
