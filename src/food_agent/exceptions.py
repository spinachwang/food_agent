"""自定义异常体系.

所有 Food Agent 内部抛出的异常都继承自 FoodAgentError,便于上层 catch.
"""


class FoodAgentError(Exception):
    """所有 Food Agent 异常的基类."""


# ---- 配置相关 ---------------------------------------------------------------
class ConfigurationError(FoodAgentError):
    """配置错误: 缺少 API key / yaml 格式错 / 模型名错."""


# ---- LLM / 工具调用 ---------------------------------------------------------
class LLMError(FoodAgentError):
    """LLM 调用失败."""


class ToolCallError(FoodAgentError):
    """工具调用失败 (含可重试和不可重试)."""


class RetryableToolCallError(ToolCallError):
    """可重试的工具调用错误 (网络/超时/限流/5xx)."""


class NonRetryableToolCallError(ToolCallError):
    """不可重试的工具调用错误 (参数错/权限错/404)."""


class ToolTimeoutError(RetryableToolCallError):
    """工具调用超时."""


class ToolUnavailableError(ToolCallError):
    """工具熔断中或未注册."""


# ---- Agent 编排 -------------------------------------------------------------
class AgentError(FoodAgentError):
    """子 Agent 失败."""


class MaxRoundsExceededError(AgentError):
    """多 Agent 调度轮数超限, 防止死循环."""


# ---- 数据 / 记忆 ------------------------------------------------------------
class MemoryStoreError(FoodAgentError):
    """记忆系统错误 (SQLite 读写 / 序列化失败)."""


# ---- MCP --------------------------------------------------------------------
class MCPError(FoodAgentError):
    """MCP Server 错误."""


# ---- Guardrails -------------------------------------------------------------
class GuardrailViolationError(FoodAgentError):
    """输入/输出违反安全规则."""


# ---- 成本 / 配额 ------------------------------------------------------------
class BudgetExceededError(FoodAgentError):
    """单次推荐超过 token 预算."""
