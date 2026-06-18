"""Agent 基类: BaseCuisineAgent.

菜系专家的共同行为:
1. 加载 system prompt + 知识库
2. 包装 qwen-agent.Assistant
3. 暴露 cuisine_id / cuisine_name / recommend()
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from food_agent.exceptions import LLMError
from food_agent.llm import get_llm_cfg


class BaseCuisineAgent(ABC):
    """菜系专家基类.

    子类必须定义:
        cuisine_id: str      - 唯一标识
        cuisine_name: str    - 显示名
        system_prompt: str   - 菜系专属 system prompt
        knowledge: str       - 菜系知识库 (可选)
    """

    cuisine_id: str = ""
    cuisine_name: str = ""
    system_prompt: str = ""
    knowledge: str = ""

    def __init__(
        self,
        llm: Any | None = None,
        fallback: str | None = None,
        **kwargs: Any,
    ) -> None:
        """初始化.

        Args:
            llm: LLM 实例 (dict 配置 或 BaseChatModel 实例).
                 None 时用默认 get_llm_cfg().
            fallback: LLM 失败时的降级文本.
            **kwargs: 透传给 Assistant.
        """
        self._fallback = fallback
        self._llm = llm if llm is not None else get_llm_cfg()
        self._assistant = self._build_assistant(**kwargs)

    def _build_assistant(self, **kwargs: Any) -> Any:
        """构造 qwen-agent.Assistant."""
        from qwen_agent.agents import Assistant

        full_system = self.system_prompt
        if self.knowledge:
            full_system = f"{self.system_prompt}\n\n## 知识库\n\n{self.knowledge}"

        # 默认 name/description, 但允许 kwargs 覆盖
        build_kwargs = {
            "llm": self._llm,
            "system_message": full_system,
            "name": f"cuisine_{self.cuisine_id}",
            "description": f"{self.cuisine_name}专家, 提供该菜系的餐厅和菜品推荐",
        }
        build_kwargs.update(kwargs)

        return Assistant(**build_kwargs)

    def recommend(self, user_msg: str, context: str = "") -> str:
        """根据用户消息 + 上下文给出菜系推荐.

        Args:
            user_msg: 用户消息.
            context: 8 维分析器产出的约束 (JSON 或文本).

        Returns:
            LLM 返回的推荐文本.
        """
        prompt = user_msg
        if context:
            prompt = f"上下文: {context}\n\n用户问题: {user_msg}"

        messages = [{"role": "user", "content": prompt}]

        try:
            responses = list(self._assistant.run(messages))
        except LLMError:
            return self._fallback_response()
        except Exception as e:
            # 真实运行中可能遇到网络/限流等
            if self._fallback is not None:
                return self._fallback
            raise LLMError(f"{self.cuisine_name} agent failed: {e}") from e

        if not responses:
            return self._fallback_response()

        # responses[-1] 是最后一批消息, 包含 assistant 的回复
        last_batch = responses[-1]
        if not last_batch:
            return self._fallback_response()

        return self._extract_content(last_batch[0])

    @staticmethod
    def _extract_content(msg: Any) -> str:
        """从 qwen-agent 消息对象提取文本内容."""
        if isinstance(msg, str):
            return msg
        if isinstance(msg, dict):
            return msg.get("content", "") or ""
        # Message 对象
        content = getattr(msg, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            # 多模态: 拼接所有 text
            parts = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    parts.append(item["text"])
                elif hasattr(item, "text"):
                    parts.append(item.text)
            return "".join(parts)
        return str(content)

    def _fallback_response(self) -> str:
        """LLM 失败时的降级响应."""
        if self._fallback is not None:
            return self._fallback
        return f"（{self.cuisine_name}专家暂时不可用, 请稍后再试）"

    @abstractmethod
    def describe(self) -> str:
        """描述本菜系特点, 供 Master Foodie 调度参考."""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.cuisine_id!r} name={self.cuisine_name!r}>"
