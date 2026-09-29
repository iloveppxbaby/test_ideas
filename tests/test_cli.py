from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from guazi_script_agent.cli import main
from guazi_script_agent.schemas import VideoScript

ROOT = Path(__file__).resolve().parents[1]


def test_cli_writes_json_and_markdown(tmp_path) -> None:
    code = main(
        [
            "generate",
            "--reference",
            str(ROOT / "examples/reference_video.json"),
            "--value-points",
            str(ROOT / "examples/value_points.json"),
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert code == 0
    script = VideoScript.model_validate_json(
        (tmp_path / "script.json").read_text(encoding="utf-8")
    )
    assert script.provider == "mock"
    markdown = (tmp_path / "script.md").read_text(encoding="utf-8")
    assert "口播" in markdown
    assert "待核实" in markdown
    assert "避免虚假承诺" in markdown


def test_cli_duration_override(tmp_path) -> None:
    code = main(
        [
            "generate",
            "--reference",
            str(ROOT / "examples/reference_video.json"),
            "--value-points",
            str(ROOT / "examples/value_points.json"),
            "--output-dir",
            str(tmp_path),
            "--duration",
            "12",
        ]
    )
    assert code == 0
    script = VideoScript.model_validate_json(
        (tmp_path / "script.json").read_text(encoding="utf-8")
    )
    assert script.target_duration_seconds == 12


def test_cli_missing_file_exits_2(tmp_path) -> None:
    code = main(
        [
            "generate",
            "--reference",
            str(tmp_path / "missing.json"),
            "--value-points",
            str(ROOT / "examples/value_points.json"),
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert code == 2


def test_cli_mp4_url_uses_container_duration(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_video_source import EXAMPLE_URL, _mp4, _Response

    payload = _mp4()

    def urlopen(request, timeout=0):
        return _Response(
            payload,
            {
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes 0-{len(payload) - 1}/{len(payload)}",
            },
        )

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    code = main(
        [
            "generate",
            "--reference",
            EXAMPLE_URL,
            "--value-points",
            str(ROOT / "examples/value_points.json"),
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert code == 0
    script = VideoScript.model_validate_json(
        (tmp_path / "script.json").read_text(encoding="utf-8")
    )
    assert script.source_url == EXAMPLE_URL
    assert script.structure_borrowed.source_duration_seconds == 14.78
    assert script.provider == "mock"
    assert "参考视频" in (tmp_path / "script.md").read_text(encoding="utf-8")


def test_render_video_requires_ark(tmp_path) -> None:
    code = main(
        [
            "generate",
            "--reference",
            str(ROOT / "examples/reference_video.json"),
            "--value-points",
            str(ROOT / "examples/value_points.json"),
            "--output-dir",
            str(tmp_path),
            "--render-video",
        ]
    )
    assert code == 2
    assert not (tmp_path / "script.json").exists()


def test_ark_without_key_exits_2(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GUAZI_LLM_API_KEY", raising=False)
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    reference = tmp_path / "reference.json"
    reference.write_text(
        '{"url":"https://image-public.guazistatic.com/qnbdp1066x7663b97e86e74da7a2c2a1573267fef41788427623.mp4","duration_seconds":12,"transcript":""}',
        encoding="utf-8",
    )
    code = main(
        [
            "generate",
            "--reference",
            str(reference),
            "--value-points",
            str(ROOT / "examples/value_points.json"),
            "--output-dir",
            str(tmp_path / "out"),
            "--provider",
            "ark",
        ]
    )
    assert code == 2


def test_openai_without_key_exits_2(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GUAZI_LLM_API_KEY", raising=False)
    code = main(
        [
            "generate",
            "--reference",
            str(ROOT / "examples/reference_video.json"),
            "--value-points",
            str(ROOT / "examples/value_points.json"),
            "--output-dir",
            str(tmp_path),
            "--provider",
            "openai",
        ]
    )
    assert code == 2


def test_help_exits_0() -> None:
    with pytest.raises(SystemExit) as caught:
        main(["--help"])
    assert caught.value.code == 0


def test_module_help() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-m", "guazi_script_agent", "generate", "--help"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    assert "参考视频" in result.stdout
