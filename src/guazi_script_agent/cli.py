"""命令行入口。默认使用 mock，不访问外部模型。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from guazi_script_agent.agent import generate_script
from guazi_script_agent.errors import AgentError
from guazi_script_agent.llm import create_client
from guazi_script_agent.render import render_json, render_markdown
from guazi_script_agent.schemas import ReferenceVideo, ScriptRequest, ValuePointSet


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="guazi-script",
        description="根据热点参考视频的结构和瓜子价值点，生成原创短视频脚本。",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    generate = subcommands.add_parser("generate", help="生成脚本 JSON 和 Markdown")
    generate.add_argument("--reference", required=True, type=Path, help="参考视频 JSON")
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
        choices=("mock", "openai"),
        default="mock",
        help="默认 mock，不调用外部模型",
    )
    generate.add_argument(
        "--duration", type=float, default=None, help="目标时长（秒），覆盖文件中的设置"
    )
    generate.add_argument("--model", default=None, help="仅 openai：模型名")
    generate.add_argument("--base-url", default=None, help="仅 openai：兼容接口根路径")
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
    reference_path: Path, value_points_path: Path, duration: float | None
) -> ScriptRequest:
    reference = ReferenceVideo.model_validate_json(
        reference_path.read_text(encoding="utf-8")
    )
    points = ValuePointSet.model_validate_json(
        value_points_path.read_text(encoding="utf-8")
    )
    return ScriptRequest(
        reference=reference, value_points=points, target_duration_seconds=duration
    )


def _generate(args: argparse.Namespace) -> int:
    request = load_request(args.reference, args.value_points, args.duration)
    client = create_client(args.provider, model=args.model, base_url=args.base_url)
    script = generate_script(request, llm=client)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "script.json"
    markdown_path = args.output_dir / "script.md"
    json_path.write_text(render_json(script), encoding="utf-8")
    markdown_path.write_text(render_markdown(script), encoding="utf-8")
    print(f"已生成：{json_path}")
    print(f"已生成：{markdown_path}")
    print(f"标题：{script.title}")
    print(f"节拍：{len(script.beats)}，合规备注：{len(script.compliance_notes)}")
    return 0
