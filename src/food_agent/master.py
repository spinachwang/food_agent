"""Master Foodie Agent - 地球顶级美食家.

负责:
- 接收用户请求
- 调度菜系专家子 Agent (Phase 1: 只有川菜)
- 综合专家意见输出 Top 推荐

Phase 1 实现:
- 加载 cuisines.yaml (后续 Phase 2 完整化)
- 默认带 SichuanAgent
- 支持注入自定义菜系
- system prompt 从 config/prompts/master_v1.md 加载
- run(user_msg) 流式返回最终响应
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from food_agent.agents.base import BaseCuisineAgent
from food_agent.agents.cuisines.sichuan import SichuanAgent
from food_agent.exceptions import LLMError
from food_agent.llm import get_llm_cfg
from food_agent.tools.cuisine_consult import CuisineConsultTool

# Master system prompt 路径
_PACKAGE_DIR = Path(__file__).resolve().parent
MASTER_PROMPT_PATH = _PACKAGE_DIR / "config" / "prompts" / "master_v1.md"


def _load_master_prompt(path: Path | None = None) -> str:
    """加载 Master system prompt."""
    p = path or MASTER_PROMPT_PATH
    if not p.exists():
        # 降级: 内置简化版
        return "你是地球顶级美食家, 精通各菜系, 善于根据用户喜好推荐餐厅和菜品."
    return p.read_text(encoding="utf-8").strip()


class FoodAgent:
    """Master Foodie Agent.

    用法:
        >>> agent = FoodAgent()  # 使用默认配置
        >>> result = agent.run("今天下雨, 一个人, 想吃辣, 预算 100")
        >>> print(result)
    """

    def __init__(
        self,
        llm: Any | None = None,
        cuisine_agents: list[BaseCuisineAgent] | None = None,
        system_prompt: str | None = None,
        max_rounds: int = 10,
    ) -> None:
        """初始化.

        Args:
            llm: LLM 实例 / 配置. None 时用默认.
            cuisine_agents: 菜系 agent 列表. None 时加载 Phase 1 默认 (sichuan).
            system_prompt: 覆盖默认 master prompt.
            max_rounds: 最大调度轮数, 防止死循环.
        """
        self.llm = llm if llm is not None else get_llm_cfg()
        self.cuisine_agents: list[BaseCuisineAgent] = (
            cuisine_agents if cuisine_agents is not None else self._default_cuisines()
        )
        self.system_prompt = system_prompt or _load_master_prompt()
        self.max_rounds = max_rounds

        # 每个菜系包成 tool
        self.tools: list[CuisineConsultTool] = [
            CuisineConsultTool(agent) for agent in self.cuisine_agents
        ]

        # 构造 qwen-agent Assistant
        self._assistant = self._build_assistant()

    def _default_cuisines(self) -> list[BaseCuisineAgent]:
        """Phase 1 默认菜系: 川菜.

        Phase 2 会从 cuisines.yaml 动态加载全部 14 个.
        """
        return [SichuanAgent(llm=self.llm, fallback="推荐通用川菜: 麻婆豆腐、回锅肉")]

    def _build_assistant(self) -> Any:
        from qwen_agent.agents import Assistant

        return Assistant(
            llm=self.llm,
            system_message=self.system_prompt,
            function_list=self.tools,
            name="master_foodie",
            description="地球顶级美食家, 调度各菜系专家",
        )

    def run(self, user_msg: str, history: list[dict] | None = None) -> str:
        """运行主流程.

        Args:
            user_msg: 用户消息.
            history: 历史消息 (可选).

        Returns:
            Assistant 的最终回复.
        """
        if not user_msg or not user_msg.strip():
            return "（老饕听着呢, 你想吃啥？）"

        messages: list[dict] = list(history or [])
        messages.append({"role": "user", "content": user_msg})

        try:
            responses = list(self._assistant.run(messages))
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"master agent failed: {e}") from e

        if not responses:
            return self._fallback_response()

        # responses[-1] 是最后一批 assistant/tool 消息
        last_batch = responses[-1]
        if not last_batch:
            return self._fallback_response()

        # 取最后一条 assistant 消息
        for msg in reversed(last_batch):
            content = self._extract_content(msg)
            if content and content.strip():
                return content
        return self._fallback_response()

    @staticmethod
    def _extract_content(msg: Any) -> str:
        """从 qwen-agent 消息对象提取文本."""
        if isinstance(msg, str):
            return msg
        if isinstance(msg, dict):
            return msg.get("content", "") or ""
        content = getattr(msg, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    parts.append(item["text"])
                elif hasattr(item, "text"):
                    parts.append(item.text)
            return "".join(parts)
        return str(content)

    def _fallback_response(self) -> str:
        """assistant 没返回内容时的降级."""
        return "（老饕今天没灵感, 稍后再试. 或者换个说法？）"

    def __repr__(self) -> str:
        cuisines = [a.cuisine_id for a in self.cuisine_agents]
        return f"<FoodAgent cuisines={cuisines} max_rounds={self.max_rounds}>"
