from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Self

import pytest

from guazi_script_agent.errors import AgentError
from guazi_script_agent.schemas import ReferenceVideo
from guazi_script_agent.video_source import (
    load_reference,
    probe_mp4_duration,
    read_mp4_duration_seconds,
)

EXAMPLE_URL = (
    "https://image-public.guazistatic.com/"
    "qnbdp1066x7663b97e86e74da7a2c2a1573267fef41788427623.mp4"
)


def _box(box_type: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", 8 + len(payload)) + box_type + payload


def _mvhd(timescale: int, duration: int, *, version: int = 0) -> bytes:
    # 版本号在首字节；后三字节是 flags。
    if version == 0:
        payload = bytes([0, 0, 0, 0]) + struct.pack(">II", 0, 0)
        payload += struct.pack(">II", timescale, duration)
    else:
        payload = bytes([1, 0, 0, 0]) + struct.pack(">QQ", 0, 0)
        payload += struct.pack(">IQ", timescale, duration)
    return _box(b"mvhd", payload + b"\x00" * 60)


def _mp4(timescale: int = 1000, duration: int = 14784) -> bytes:
    # mdat 里故意放一段 mvhd 字样，解析必须走盒子结构，不能按字节搜索。
    mdat = _box(b"mdat", b"xxxxmvhdyyyy")
    moov = _box(b"moov", _mvhd(timescale, duration))
    return mdat + _box(b"ftyp", b"isom") + moov


class _Response:
    def __init__(self, data: bytes, headers: dict[str, str]) -> None:
        self._data = data
        self.headers = headers

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = len(self._data)
        chunk = self._data[:size]
        self._data = self._data[size:]
        return chunk

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> bool:
        return False


def test_reads_duration_from_mvhd_not_from_media_bytes() -> None:
    assert read_mp4_duration_seconds(_mp4()) == pytest.approx(14.784)
    assert read_mp4_duration_seconds(
        _mp4(1000, 14784).replace(b"mvhd", b"free", 1)
    ) == pytest.approx(14.784)


def test_reads_version_1_mvhd() -> None:
    data = _box(b"moov", _mvhd(1000, 8000, version=1))
    assert read_mp4_duration_seconds(data) == pytest.approx(8)


def test_probe_uses_first_range_and_checks_duration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _mp4()
    calls: list[str] = []

    def opener(request, timeout: float = 0):
        calls.append(request.get_header("Range"))
        return _Response(
            payload,
            {
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes 0-{len(payload) - 1}/{len(payload)}",
            },
        )

    assert probe_mp4_duration(EXAMPLE_URL, opener=opener) == 14.78
    assert calls == ["bytes=0-1048575"]


def test_html_response_is_rejected() -> None:
    def opener(request, timeout: float = 0):
        return _Response(b"<html></html>", {"Content-Type": "text/html"})

    with pytest.raises(AgentError, match="不是视频"):
        probe_mp4_duration(EXAMPLE_URL, opener=opener)


def test_too_short_video_is_rejected() -> None:
    payload = _mp4(1000, 1000)

    def opener(request, timeout: float = 0):
        return _Response(payload, {"Content-Type": "video/mp4"})

    with pytest.raises(AgentError, match="只支持"):
        probe_mp4_duration(EXAMPLE_URL, opener=opener)


def test_json_with_duration_does_not_download(tmp_path: Path) -> None:
    path = tmp_path / "reference.json"
    path.write_text(
        json.dumps(
            {
                "url": EXAMPLE_URL,
                "duration_seconds": 12,
                "transcript": "已经写好的转写。",
                "title": "参考视频",
                "platform": "url",
            }
        ),
        encoding="utf-8",
    )

    def opener(request, timeout: float = 0):
        raise AssertionError("已有时长时不应下载视频")

    video = load_reference(str(path), opener=opener)
    assert video.duration_seconds == 12
    assert video.url == EXAMPLE_URL


def test_file_url_is_rejected() -> None:
    with pytest.raises(Exception, match="http"):
        ReferenceVideo.model_validate(
            {
                "duration_seconds": 10,
                "transcript": "一段中性转写。",
                "url": "file:///tmp/a.mp4",
            }
        )
