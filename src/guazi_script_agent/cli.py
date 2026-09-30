"""命令行入口。默认使用 mock，不访问外部模型。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from guazi_script_agent.agent import generate_script
from guazi_script_agent.errors import AgentError
from guazi_script_agent.llm import (
    create_client,
    create_video_client,
    create_video_generation_client,
)
from guazi_script_agent.render import render_json, render_markdown
from guazi_script_agent.schemas import ScriptRequest, ValuePointSet
from guazi_script_agent.understanding import needs_video_understanding
from guazi_script_agent.video_gen import submit_script_video
from guazi_script_agent.video_source import load_reference


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="guazi-script",
        description="根据热点参考视频的结构和瓜子价值点，生成原创短视频脚本。",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    generate = subcommands.add_parser("generate", help="生成脚本 JSON 和 Markdown")
    generate.add_argument(
        "--reference",
        required=True,
        help="参考视频 JSON 文件，或 http(s) MP4 直链",
    )
    generate.add_argument(
        "--value-points", required=True, type=Path, help="价值点 JSON"
    )
    generate.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="输出目录，写入 script.json 和 script.md",
    )
    generate.add_argument(
        "--provider",
        choices=("mock", "openai", "ark"),
        default="mock",
        help="默认 mock。ark 使用豆包：文本、视频理解、视频生成各绑定一个模型",
    )
    generate.add_argument(
        "--duration", type=float, default=None, help="目标时长（秒），覆盖文件中的设置"
    )
    generate.add_argument(
        "--model",
        default=None,
        help="openai 的模型名，或豆包文本模型，覆盖 ARK_SCRIPT_MODEL",
    )
    generate.add_argument(
        "--video-model",
        default=None,
        help="豆包视频理解模型，覆盖 ARK_VIDEO_MODEL",
    )
    generate.add_argument(
        "--video-gen-model",
        default=None,
        help="视频生成模型，覆盖 ARK_VIDEO_GEN_MODEL",
    )
    generate.add_argument(
        "--render-video",
        action="store_true",
        help="用 Seedance 2.0 提交成片任务，并写入 video_task.json",
    )
    generate.add_argument(
        "--base-url",
        default=None,
        help="openai 或豆包的接口根路径",
    )
    generate.set_defaults(handler=_generate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (AgentError, ValidationError, OSError, json.JSONDecodeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


def load_request(
    reference: str, value_points_path: Path, duration: float | None
) -> ScriptRequest:
    video = load_reference(reference)
    points = ValuePointSet.model_validate_json(
        value_points_path.read_text(encoding="utf-8")
    )
    return ScriptRequest(
        reference=video, value_points=points, target_duration_seconds=duration
    )


def _generate(args: argparse.Namespace) -> int:
    if args.render_video and args.provider != "ark":
        raise AgentError("视频生成只在 --provider ark 下调用 Seedance 2.0。")
    request = load_request(args.reference, args.value_points, args.duration)
    understander = None
    if args.provider == "ark" and needs_video_understanding(request.reference):
        understander = create_video_client(
            "ark", model=args.video_model, base_url=args.base_url
        )
    client = create_client(args.provider, model=args.model, base_url=args.base_url)
    script = generate_script(request, llm=client, understander=understander)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "script.json"
    markdown_path = args.output_dir / "script.md"
    json_path.write_text(render_json(script), encoding="utf-8")
    markdown_path.write_text(render_markdown(script), encoding="utf-8")
    print(f"已生成：{json_path}")
    print(f"已生成：{markdown_path}")
    print(f"标题：{script.title}")
    print(f"节拍：{len(script.beats)}，合规备注：{len(script.compliance_notes)}")
    if args.render_video:
        generator = create_video_generation_client(
            "ark", model=args.video_gen_model, base_url=args.base_url
        )
        task = submit_script_video(script, generator)
        task_path = args.output_dir / "video_task.json"
        task_path.write_text(
            task.model_dump_json(indent=2, exclude_none=True) + "\n",
            encoding="utf-8",
        )
        print(f"已提交视频任务：{task_path}")
        print(f"任务编号：{task.task_id}")
    return 0
