from __future__ import annotations

from pathlib import Path

import pytest

from guazi_script_agent.local_env import ensure_local_api_key, read_api_key


def test_reads_quoted_export_and_keeps_the_last_assignment(tmp_path: Path) -> None:
    path = tmp_path / ".bashrc"
    path.write_text(
        """\
# export GUAZI_LLM_API_KEY=commented
export GUAZI_LLM_API_KEY="first-key"
export GUAZI_LLM_API_KEY='second-key'  # 本地
echo hello
""",
        encoding="utf-8",
    )
    assert read_api_key(path) == "second-key"


def test_does_not_execute_command_substitution(tmp_path: Path) -> None:
    path = tmp_path / ".bashrc"
    path.write_text(
        'export GUAZI_LLM_API_KEY="$(printf leaked)"\n',
        encoding="utf-8",
    )
    assert read_api_key(path) == "$(printf leaked)"


def test_missing_file_is_empty(tmp_path: Path) -> None:
    assert read_api_key(tmp_path / "missing") == ""


def test_ensure_loads_bashrc_when_env_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GUAZI_LLM_API_KEY", raising=False)
    path = tmp_path / ".bashrc"
    path.write_text('export GUAZI_LLM_API_KEY="from-bashrc"\n', encoding="utf-8")
    assert ensure_local_api_key(path) == "from-bashrc"
    assert ensure_local_api_key(path) == "from-bashrc"
