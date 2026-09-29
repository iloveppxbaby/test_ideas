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
