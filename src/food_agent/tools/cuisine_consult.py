"""CuisineConsultTool: 把菜系专家包装为 Master 可调用的 Tool.

每个菜系 agent 都包成 BaseTool, 这样 Master Foodie Agent 可以:
1. 看到所有菜系工具的 name/description/parameters
2. 在 function calling 中选合适的工具
3. 把用户问题 + 上下文传给工具
4. 工具内部用 RobustToolCaller 做容错
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from qwen_agent.tools.base import BaseTool

from food_agent.agents.base import BaseCuisineAgent
from food_agent.tools.base import RobustToolCaller


class CuisineConsultTool(BaseTool):
    """把菜系专家包装为可调用 Tool (继承 BaseTool).

    name/description 在 __init__ 动态设置, qwen-agent 会在调用 .call() 时
    通过 self.function schema 暴露给 LLM.
    """

    # 类属性默认值, 实际在 __init__ 中覆盖
    name: str = "consult_cuisine"
    description: str = "咨询菜系专家"
    parameters: list[dict[str, Any]] = [
        {
            "name": "user_query",
            "type": "string",
            "description": "用户想了解的内容",
            "required": True,
        },
        {
            "name": "context",
            "type": "string",
            "description": "8 维分析器产出的约束 (JSON 文本)",
            "required": False,
        },
    ]

    def __init__(
        self,
        agent: BaseCuisineAgent,
        max_retries: int = 2,
        base_delay: float = 1.0,
        max_delay: float = 10.0,
        fallback: Callable[..., str] | None = None,
    ) -> None:
        """初始化.

        Args:
            agent: 被包装的菜系 agent.
            max_retries: RobustToolCaller 重试次数.
            base_delay: 重试基础延迟 (秒).
            max_delay: 重试最大延迟.
            fallback: 主调用失败时的降级函数, 签名 (user_query, context) -> str.

        Raises:
            ValueError: 如果 BaseTool 校验不通过.
        """
        # 必须先设置 name/description 再调 super().__init__()
        self._cuisine_id = agent.cuisine_id
        self._cuisine_name = agent.cuisine_name
        self.agent = agent
        self.caller = RobustToolCaller(
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
        )
        self._fallback = fallback

        # 动态设置 (BaseTool 校验需要在 super().__init__ 之前)
        self.name = f"consult_{agent.cuisine_id}"
        self.description = (
            f"向【{agent.cuisine_name}】专家咨询. {agent.describe()} "
            f"调用时传入 user_query (用户问题) 和 context (8 维分析约束 JSON)."
        )

        # BaseTool 校验
        super().__init__()

    def call(self, params: str | dict, **kwargs: Any) -> str:
        """执行菜系咨询.

        Args:
            params: 工具参数 (dict 或 JSON str).
            **kwargs: qwen-agent 透传.

        Returns:
            菜系专家的推荐文本.
        """
        # 解析 params
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                # 兼容: 整个字符串当 user_query
                params = {"user_query": params}

        if not isinstance(params, dict):
            raise ValueError(f"tool params must be dict, got {type(params)}")

        user_query = params.get("user_query", "")
        context = params.get("context", "")

        if not user_query:
            return "（请告诉我想咨询什么）"

        def _primary() -> str:
            return self.agent.recommend(user_query, context=context)

        def _fallback_fn(*_args: Any, **_kwargs: Any) -> str:
            if self._fallback is not None:
                return self._fallback(user_query, context)
            return f"（{self._cuisine_name}专家暂时不可用, 请稍后再试）"

        return self.caller.call(_primary, fallback=_fallback_fn)

    def __repr__(self) -> str:
        return f"<CuisineConsultTool name={self.name!r} agent={self.agent!r}>"
