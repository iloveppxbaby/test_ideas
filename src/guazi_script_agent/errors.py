"""生成流程里调用方可以处理的错误。"""


class AgentError(Exception):
    """输入、配置或外部模型调用失败。"""


class OutputError(AgentError):
    """草稿未通过结构、覆盖或原创性校验，允许自动重试一次。"""
