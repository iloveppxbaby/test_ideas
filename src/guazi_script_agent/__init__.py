"""根据参考视频结构和瓜子价值点生成原创短视频脚本。"""

from guazi_script_agent.agent import generate_script
from guazi_script_agent.schemas import (
    ReferenceVideo,
    ScriptRequest,
    ValuePointSet,
    VideoScript,
)

__version__ = "0.1.0"
__all__ = [
    "ReferenceVideo",
    "ScriptRequest",
    "ValuePointSet",
    "VideoScript",
    "__version__",
    "generate_script",
]
