"""从 MP4 直链读取容器时长。不调用模型，也不做语音识别。"""

from __future__ import annotations

import struct
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

from guazi_script_agent.errors import AgentError
from guazi_script_agent.schemas import (
    MAX_DURATION_SECONDS,
    MIN_DURATION_SECONDS,
    ReferenceVideo,
)

_MAX_BYTES = 80 * 1024 * 1024
_FIRST_BYTES = 1024 * 1024
_TAIL_BYTES = 2 * 1024 * 1024
_CONTAINERS = {
    b"moov",
    b"trak",
    b"mdia",
    b"minf",
    b"stbl",
    b"edts",
    b"moof",
    b"traf",
    b"mvex",
}
Opener = Callable[..., object]


def is_http_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def load_reference(spec: str, *, opener: Opener | None = None) -> ReferenceVideo:
    """JSON 文件，或一条 http(s) MP4 直链。直链会尽量只读文件头。"""
    text = spec.strip()
    if is_http_url(text):
        seconds = probe_mp4_duration(text, opener=opener)
        return ReferenceVideo(
            title="参考视频",
            platform="url",
            duration_seconds=seconds,
            transcript="",
            url=text,
        )
    path = Path(text)
    video = ReferenceVideo.model_validate_json(path.read_text(encoding="utf-8"))
    if video.duration_seconds is not None or not video.url:
        return video
    seconds = probe_mp4_duration(video.url, opener=opener)
    return video.model_copy(update={"duration_seconds": seconds})


def probe_mp4_duration(
    url: str, *, opener: Opener | None = None, timeout: float = 20
) -> float:
    if not is_http_url(url):
        raise AgentError("视频地址必须是 http 或 https 链接")
    data, total, content_type = _fetch_range(url, 0, _FIRST_BYTES - 1, opener, timeout)
    _reject_non_video(content_type)
    seconds = read_mp4_duration_seconds(data)
    if seconds is None and total is not None and total > len(data):
        if total > _MAX_BYTES:
            raise AgentError("参考视频超过 80MB，且文件头里没有时长")
        tail_start = max(0, total - _TAIL_BYTES)
        tail, _, _ = _fetch_range(url, tail_start, total - 1, opener, timeout)
        seconds = read_mp4_duration_seconds(tail)
    if seconds is None:
        raise AgentError(
            "没有读到 MP4 时长。请确认链接是 mp4，或改用带 duration_seconds 的 JSON。"
        )
    return _check_duration(seconds)


def read_mp4_duration_seconds(data: bytes) -> float | None:
    payload = _find_mvhd(data, 0, len(data))
    if payload is None:
        return None
    version = payload[0]
    try:
        if version == 0:
            timescale, units = struct.unpack_from(">II", payload, 12)
        elif version == 1:
            timescale, units = struct.unpack_from(">IQ", payload, 20)
        else:
            raise AgentError(f"不支持的 MP4 mvhd 版本：{version}")
    except struct.error as exc:
        raise AgentError("MP4 的 mvhd 不完整") from exc
    if timescale <= 0:
        raise AgentError("MP4 时间刻度无效")
    return units / timescale


def _check_duration(seconds: float) -> float:
    rounded = round(float(seconds), 2)
    if rounded < MIN_DURATION_SECONDS or rounded > MAX_DURATION_SECONDS:
        raise AgentError(
            f"参考视频时长为 {rounded} 秒，只支持 {MIN_DURATION_SECONDS} 到 {MAX_DURATION_SECONDS} 秒"
        )
    return rounded


def _find_mvhd(data: bytes, start: int, end: int) -> bytes | None:
    for box_type, payload_start, payload_end in _iter_boxes(data, start, end):
        if box_type == b"mvhd":
            return data[payload_start:payload_end]
        if box_type in _CONTAINERS:
            found = _find_mvhd(data, payload_start, payload_end)
            if found is not None:
                return found
    return None


def _iter_boxes(data: bytes, start: int, end: int):
    offset = start
    while offset + 8 <= end:
        size = struct.unpack_from(">I", data, offset)[0]
        box_type = data[offset + 4 : offset + 8]
        header = 8
        if size == 1:
            if offset + 16 > end:
                break
            size = struct.unpack_from(">Q", data, offset + 8)[0]
            header = 16
        elif size == 0:
            size = end - offset
        if size < header or offset + size > end:
            break
        yield box_type, offset + header, offset + size
        offset += size


def _fetch_range(
    url: str,
    start: int,
    end: int,
    opener: Opener | None,
    timeout: float,
) -> tuple[bytes, int | None, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "guazi-script-agent/0.1",
            "Range": f"bytes={start}-{end}",
        },
        method="GET",
    )
    open_url = opener or urllib.request.urlopen
    try:
        response = open_url(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise AgentError(f"下载参考视频失败：HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise AgentError(f"下载参考视频失败：{exc.reason}") from exc
    with response:
        headers = getattr(response, "headers", {})
        content_type = _header(headers, "Content-Type")
        total = _total_length(headers)
        data = _read_capped(response, _MAX_BYTES)
    return data, total, content_type


def _header(headers: object, name: str) -> str:
    getter = getattr(headers, "get", None)
    if getter is None:
        return ""
    value = getter(name) or getter(name.lower()) or ""
    return str(value)


def _total_length(headers: object) -> int | None:
    content_range = _header(headers, "Content-Range")
    if "/" in content_range:
        total = content_range.rsplit("/", 1)[-1]
        if total.isdigit():
            return int(total)
    length = _header(headers, "Content-Length")
    if length.isdigit():
        return int(length)
    return None


def _read_capped(response: object, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    read = response.read
    while total <= limit:
        block = read(min(64 * 1024, limit + 1 - total))
        if not block:
            break
        chunks.append(block)
        total += len(block)
        if total > limit:
            raise AgentError("参考视频超过 80MB，已停止下载")
    return b"".join(chunks)


def _reject_non_video(content_type: str) -> None:
    media = content_type.split(";", 1)[0].strip().lower()
    if media.startswith("text/") or media in {"application/json", "application/xml"}:
        raise AgentError(f"链接返回的不是视频：{media or '未知类型'}")
