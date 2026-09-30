"""视频理解提示词 video-v1。

只让模型交还结构和本地查重用的转写。转写不会进入脚本提示词。
"""

from __future__ import annotations

VIDEO_PROMPT_VERSION = "video-v1"

VIDEO_INSTRUCTION = """请理解这条短视频的讲法，只返回一个 JSON 对象，不要 Markdown。

字段：
- duration_seconds：视频时长（秒）
- hook_type：question、contrast、number、pain、story 之一
- rhythm_notes：2 到 12 条，从 0 秒覆盖到整段时长且首尾相接。每条含 start_seconds、end_seconds、shot、purpose
- transcript：口播或字幕的转写，只给本地查重，不会被写进新脚本
- why_viral：用一句话说明手法，不要摘抄原句

规则：
1. shot 只写镜头功能，例如「近景提问」「快切证据」，禁止逐字引用口播。
2. purpose 用「开场钩子」「展开」「证明」「转折」「引导互动」这类词。
3. 不要评价瓜子，不要写新脚本。
"""
