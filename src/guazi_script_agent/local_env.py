"""从本机环境读取密钥。进程里没有时，再看用户 Home 下的 ~/.bashrc。"""

from __future__ import annotations

import os
import re
from pathlib import Path

API_KEY_ENV = "GUAZI_LLM_API_KEY"
_ASSIGNED = re.compile(rf"^\s*(?:export\s+)?{API_KEY_ENV}\s*=\s*(?P<value>.*?)\s*$")


def ensure_local_api_key(bashrc: Path | None = None) -> str:
    """返回密钥。已在环境中则直接用；否则只解析 ~/.bashrc 里的赋值，不执行该文件。"""
    current = os.environ.get(API_KEY_ENV, "").strip()
    if current:
        return current
    # 测试要保持「没密钥就不外呼」。测试里请显式传入 bashrc。
    if bashrc is None and os.environ.get("PYTEST_CURRENT_TEST"):
        return ""
    path = bashrc if bashrc is not None else Path.home() / ".bashrc"
    found = read_api_key(path)
    if found:
        os.environ[API_KEY_ENV] = found
    return found


def read_api_key(path: Path) -> str:
    if not path.is_file():
        return ""
    found = ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        matched = _ASSIGNED.match(stripped)
        if matched is None:
            continue
        value = _unquote(matched.group("value"))
        if value:
            found = value
    return found


def _unquote(raw: str) -> str:
    text = raw.strip()
    if not text or text.startswith("#"):
        return ""
    if text[0] in {'"', "'"}:
        quote = text[0]
        end = text.find(quote, 1)
        if end == -1:
            return ""
        return text[1:end].strip()
    if " #" in text:
        text = text.split(" #", 1)[0]
    return text.strip()
