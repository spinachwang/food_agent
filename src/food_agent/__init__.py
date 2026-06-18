"""food-agent: 多 Agent 美食推荐系统.

由"地球顶级美食家"主 Agent 调度 14 个菜系专家子 Agent，根据 8 维分析
(价格/口味/天气/心情/场景/时段/位置/饮食限制)综合推荐。

Example:
    >>> from food_agent.master import FoodAgent  # noqa: F401  (Phase 1)
"""

from food_agent.exceptions import (
    ConfigurationError,
    FoodAgentError,
    LLMError,
    ToolCallError,
)

__version__ = "0.1.0"
__all__ = [
    "ConfigurationError",
    "FoodAgentError",
    "LLMError",
    "ToolCallError",
]
