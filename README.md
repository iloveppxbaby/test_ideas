# 瓜子视频脚本生成 Agent

根据热点参考视频的**结构和节奏**，以及瓜子二手车的**价值点**，生成一条新的短视频脚本。成稿是原创口播，不照搬参考视频文案。

瓜子在这里指瓜子二手车。价值点是品牌或车源卖点（要讲什么），不是吃瓜段子。参考视频只回答「怎么讲」：钩子类型、节拍时长、镜头密度。

## 假设

1. 热点视频可以是结构化 JSON，也可以是 http(s) 的 MP4 直链。直链会按 Range 读取容器时长（单文件不超过 80MB，时长 3 到 600 秒）。`mock` 不做语音识别和画面理解，只按时长拆节拍。`--provider ark` 才会把直链交给豆包做视频理解。
2. 默认生成器是确定性的 `mock`，不调用付费 API，没有密钥也能跑通。`--provider openai` 和 `--provider ark` 都读取 `GUAZI_LLM_API_KEY`，没有这个变量就拒绝外呼。`ark` 在火山方舟上按任务各建一个实例：文本理解与脚本生成默认 `doubao-seed-2-0-lite-260428`，视频理解默认 `doubao-seed-2-1-pro`，视频生成默认 Seedance 2.0（`doubao-seedance-2-0-260128`）。可用环境变量或命令行覆盖。
3. 送给模型的提示词（当前 `v1`）只包含钩子类型、节拍时间与角色、平台和价值点。参考视频的标题、转写、分镜原文和「为什么火」原文不进入提示词，只在本地用来推断结构、做原创性校验。
4. 钩子类型按关键词优先级推断，命中即停：`pain` → `story` → `number` → `contrast` → `question`。比较范围是标题、「为什么火」、第一条节奏要点，以及转写的第一句。
5. 提供了节奏要点时，第一条视为开场，最后一条视为行动号召，中间按关键词映射为 `build` / `proof` / `turn`。目标时长和参考时长不同时，时间轴等比缩放。没提供节奏要点时，大约每 5 秒一镜，至少 3 镜、最多 8 镜。
6. 目标时长优先级：命令行 `--duration` > 价值点文件里的 `target_duration_seconds` > 参考视频时长。允许范围是 3 到 600 秒。节奏要点 2 到 12 条，价值点 1 到 8 条。JSON 不能带未定义字段。
7. 合规不依赖模型自觉。没有 `evidence` 的卖点标为待核实；有证据时只要求表述停在调用方给的事实里，本工具不核验事实真伪。禁用表述会从标题、钩子、口播、画面、字幕和行动号召里删除。成稿始终附带「避免虚假承诺」备注。
8. 观众可见文案（含合规备注）与参考标题、转写、分镜、「为什么火」在去掉空白和标点后，不得共享连续 12 个字。原文不足 12 字但不少于 8 字时，按整段比对。价值点自己如果照搬了参考文案，生成会失败。
9. `mock` 用克制口吻写口播，大约按每秒不超过 8 个汉字裁进节拍。`tone` 会进入提示词，但不会被当句子念出来。换上真实模型后，应由模型按 `tone` 调整措辞。
10. 示例里的证据带有「示例」字样，是演示数据，不是瓜子二手车的官方口径。
11. 模型输出不合格时最多自动再请求一次。外部接口需兼容 `POST /chat/completions`，并接受 `response_format=json_object`。

## 环境

Python 3.11 及以上。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 怎么跑

```bash
guazi-script generate \
  --reference examples/reference_video.json \
  --value-points examples/value_points.json \
  --output-dir out
```

未安装命令时：

```bash
PYTHONPATH=src python -m guazi_script_agent generate \
  --reference examples/reference_video.json \
  --value-points examples/value_points.json \
  --output-dir out
```

输出：

- `out/script.json`：结构化脚本
- `out/script.md`：给编导看的文稿

已提交的示例输出在 `examples/sample_output.json` 和 `examples/sample_script.md`，由默认 `mock` 生成。测试会核对它们和当前生成器一致。

指定时长：

```bash
guazi-script generate \
  --reference examples/reference_video.json \
  --value-points examples/value_points.json \
  --output-dir out \
  --duration 12
```

真实模型（本仓库的测试不会走这条路径）：

```bash
export GUAZI_LLM_API_KEY="..."          # 不要写入仓库
export GUAZI_LLM_BASE_URL="https://api.openai.com/v1"   # 可选
export GUAZI_LLM_MODEL="gpt-4o-mini"    # 可选，也可用 --model
guazi-script generate \
  --reference examples/reference_video.json \
  --value-points examples/value_points.json \
  --output-dir out \
  --provider openai
```

豆包（文本理解、视频理解、脚本生成，需要时再生成成片）：

```bash
pip install -e ".[ark]"
export GUAZI_LLM_API_KEY="..."           # 不要写入仓库。方舟和 openai 都读这个变量
# 可选覆盖，不设就用下面的默认模型：
# export ARK_SCRIPT_MODEL="doubao-seed-2-0-lite-260428"      # 文本理解与脚本
# export ARK_VIDEO_MODEL="doubao-seed-2-1-pro"               # 视频理解
# export ARK_VIDEO_GEN_MODEL="doubao-seedance-2-0-260128"    # Seedance 2.0
# export ARK_BASE_URL="https://ark.cn-beijing.volces.com/api/v3"
guazi-script generate \
  --reference "https://image-public.guazistatic.com/qnbdp1066x7663b97e86e74da7a2c2a1573267fef41788427623.mp4" \
  --value-points examples/value_points.json \
  --output-dir out \
  --provider ark
```

加上 `--render-video` 时，会用 Seedance 2.0 再提交一条竖屏成片任务，并把任务编号写到 `out/video_task.json`。成片时长限制在 4 到 15 秒，更长的脚本会被裁到 15 秒。任务是异步的，本工具不下载成片。

同一条直链如果仍用默认 `mock`，只会读取 MP4 时长并自动拆节拍，不会请求豆包。没有转写的直链才会调用视频理解模型。已经有转写、但没有节奏要点时，改用文本模型。转写和节奏都齐了，就只调用脚本文本模型。

库调用：

```python
from pathlib import Path

from guazi_script_agent import ScriptRequest, generate_script
from guazi_script_agent.schemas import ReferenceVideo, ValuePointSet

reference = ReferenceVideo.model_validate_json(
    Path("examples/reference_video.json").read_text(encoding="utf-8")
)
points = ValuePointSet.model_validate_json(
    Path("examples/value_points.json").read_text(encoding="utf-8")
)
script = generate_script(ScriptRequest(reference=reference, value_points=points))
print(script.title)
```

## 测试

```bash
pytest
```

不需要 API key。测试会挡住 `urllib.request.urlopen`，误访问网络会直接失败。

## 输入字段

参考视频 JSON：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `title` | 否 | 参考视频标题。缺省为「参考视频」。只参与本地分析 |
| `platform` | 否 | 平台，例如 `douyin`。直链缺省为 `url` |
| `duration_seconds` | 否 | 时长，3 到 600 秒。缺省且提供了 `url` 时从 MP4 容器读取 |
| `transcript` | 否 | 口播或字幕转写。直链交给豆包理解时，由模型补上，且只用于查重 |
| `rhythm_notes` | 否 | 分镜或节奏要点，2 到 12 条，时间轴从 0 覆盖到整段时长 |
| `why_viral` | 否 | 这条为什么火。可缺省 |
| `url` | 否 | http(s) MP4 直链。和 JSON 二选一，也可以写进 JSON |
| `hook_type` | 否 | `question` / `contrast` / `number` / `pain` / `story`。通常由视频理解填写 |

命令行也可以不写 JSON，直接把直链传给 `--reference`。没有转写时，`mock` 按时长拆节拍；`ark` 调用视频理解模型。已有转写但没有节奏时，`ark` 调用文本模型。

`rhythm_notes` 的每一条：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `start_seconds` | 是 | 开始秒 |
| `end_seconds` | 是 | 结束秒 |
| `shot` | 是 | 画面或节奏描述 |
| `purpose` | 是 | 这一拍的作用。可用「证明 / 清单 / 转折」等词帮助映射角色 |

价值点 JSON：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `brand` | 否 | 默认「瓜子二手车」 |
| `target_duration_seconds` | 否 | 目标时长 |
| `value_points` | 是 | 1 到 8 条卖点 |

每条价值点：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 是 | 唯一，不能含空白 |
| `title` | 是 | 卖点标题 |
| `description` | 是 | 要讲什么 |
| `evidence` | 否 | 证据或事实。空着就会标成待核实 |
| `audience` | 是 | 目标人群 |
| `tone` | 是 | 语气，例如「直白、克制」 |
| `forbidden_phrases` | 否 | 禁用表述，每条 2 到 40 个字符 |

## 输出字段

`script.json`：

| 字段 | 说明 |
| --- | --- |
| `schema_version` | 固定 `1.0` |
| `prompt_version` | 脚本提示词 `v1`。视频理解为 `v1+video-v1`，文本理解为 `v1+text-v1` |
| `provider` | `mock`、`openai` 或 `ark` |
| `source_url` | 参考视频直链。没有则为空，JSON 里省略 |
| `title` | 原创标题 |
| `target_duration_seconds` | 目标时长 |
| `opening_hook` | 开场钩子 |
| `beats` | 分镜节拍 |
| `cta` | 行动号召 |
| `compliance_notes` | 合规备注 |
| `structure_borrowed` | 实际借用的钩子类型、节拍数、镜头密度、是否缩放过时间 |

每个分镜：

| 字段 | 说明 |
| --- | --- |
| `index` | 从 1 递增 |
| `start_seconds` / `end_seconds` | 时间，首尾相接，覆盖整段时长 |
| `role` | `hook`、`build`、`proof`、`turn`、`cta` |
| `voiceover` | 口播 |
| `visual` | 画面 |
| `subtitle` | 字幕 |
| `value_point_ids` | 这一拍对应的价值点。每条输入的价值点至少出现一次 |

合规备注：

| 字段 | 说明 |
| --- | --- |
| `kind` | `unverified_claim`（待核实）、`evidence_bound`（不得超出证据）、`forbidden_phrase`（删过禁用表述）、`no_false_promise`（避免虚假承诺） |
| `message` | 给人看的说明 |
| `related_value_point_ids` | 相关价值点，可空 |

## 生成策略

1. 从参考视频抽出钩子类型和节拍，丢掉原文。
2. 用版本化提示词把结构和价值点交给可替换的 LLM 接口。
3. `mock` 按节拍角色重写口播：开场用钩子类型，中间嵌入卖点，有证据才写依据，没证据就在口播里标待核实，最后一拍收成预约看车。
4. 代码再检查时间轴、价值点覆盖、禁用表述和连续重复。合规备注由代码写入，不交给模型填写。

提示词文件在 `src/guazi_script_agent/prompts/v1.py`。要改行为时新增版本文件，并切换 `prompts/__init__.py` 的导出。

## MVP 还没有做

- 本地 ASR 和镜头切分。直链的画面与口播理解交给豆包，不在本地完成
- 素材检索，以及把参考视频本身送给 Seedance 做复刻
- 人工改稿台、审核流、投放或车源系统对接
- 用外部数据源核对检测标准、价格和政策
- 真实大模型的效果评测（默认路径不发起付费请求）
- 轮询并下载 Seedance 成片、配音和字幕烧录

## 目录

```text
src/guazi_script_agent/    包：schema、结构提取、提示词、豆包客户端、合规与 CLI
examples/                  示例参考视频、价值点、mock 成稿
tests/                     无密钥测试，含 mock 与失败重试
```

许可证沿用仓库根目录的 GPL-2.0。
