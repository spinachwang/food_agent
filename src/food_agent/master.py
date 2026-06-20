"""Master Foodie Agent - 地球顶级美食家.

负责:
- 接收用户请求
- 调度菜系专家子 Agent (Phase 2: 从 cuisines.yaml 动态加载)
- 综合专家意见输出 Top 推荐

Phase 2 接入:
- 默认菜系从 cuisines.yaml 动态加载 (Phase 1 硬编码 SichuanAgent)
- 短期记忆 (session_id) - 多轮上下文保持
- 长期记忆 (long_term + user_id) - 偏好召回 + 推荐历史
- 行为兼容: 默认 fallback 文本与 Phase 1 一致
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from food_agent.agents.analyzers import list_analyzer_tools
from food_agent.agents.base import BaseCuisineAgent
from food_agent.exceptions import LLMError
from food_agent.llm import get_llm_cfg
from food_agent.mcp.amap_client import AmapClient
from food_agent.memory.long_term import LongTermMemory
from food_agent.memory.short_term import ShortTermMemory
from food_agent.tools.cuisine_consult import CuisineConsultTool
from food_agent.tools.location import (
    GeocodeTool,
    RegeocodeTool,
    RouteTool,
    SearchAroundTool,
    WeatherTool,
    set_amap_client as _set_amap_client,
)

logger = logging.getLogger(__name__)

# Master system prompt 路径
_PACKAGE_DIR = Path(__file__).resolve().parent
MASTER_PROMPT_PATH = _PACKAGE_DIR / "config" / "prompts" / "master_v1.md"

# Phase 1 兼容: 默认 fallback 文本 (与原 _default_cuisines 一致)
# Phase 3 计划: per-cuisine fallback (每个菜系自己定义)
_DEFAULT_FALLBACK_TEXT = "推荐通用川菜: 麻婆豆腐、回锅肉"


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
        long_term: LongTermMemory | None = None,
        amap_client: AmapClient | None = None,
        enable_analyzers: bool = True,
    ) -> None:
        """初始化.

        Args:
            llm: LLM 实例 / 配置. None 时用默认.
            cuisine_agents: 菜系 agent 列表. None 时从 cuisines.yaml 动态加载.
            system_prompt: 覆盖默认 master prompt.
            max_rounds: 最大调度轮数, 防止死循环.
            long_term: 长期记忆 (Phase 2.6). None 时无持久化.
            amap_client: 高德地图 MCP client (Phase 3.1). None 时无 location 工具.
            enable_analyzers: 是否启用 3 维分析器 (Phase 3.2). 默认 True.
        """
        self.llm = llm if llm is not None else get_llm_cfg()
        self.cuisine_agents: list[BaseCuisineAgent] = (
            cuisine_agents if cuisine_agents is not None else self._default_cuisines()
        )
        self.system_prompt = system_prompt or _load_master_prompt()
        self.max_rounds = max_rounds
        self._long_term = long_term
        self._amap_client = amap_client

        # 注册 amap client (location tools 通过 module-level 拿)
        if amap_client is not None:
            _set_amap_client(amap_client)

        # 每个菜系包成 tool
        self.tools: list[Any] = [
            CuisineConsultTool(agent) for agent in self.cuisine_agents
        ]

        # 加 5 个 location tools (如果 amap_client 存在)
        if amap_client is not None:
            self.tools.extend([
                GeocodeTool(),
                RegeocodeTool(),
                SearchAroundTool(),
                WeatherTool(),
                RouteTool(),
            ])

        # 加 3 维分析器 tools (Phase 3.2). dietary 注入 long_term 用于查已知偏好.
        if enable_analyzers:
            self.tools.extend(list_analyzer_tools(long_term=long_term))

        # 构造 qwen-agent Assistant
        self._assistant = self._build_assistant()

    def _default_cuisines(self) -> list[BaseCuisineAgent]:
        """从 cuisines.yaml 动态加载所有已实现菜系.

        yaml 里有但 .py 未实现的菜系 → 跳过 (strict=False).
        """
        from food_agent.registry import load_all_cuisines

        return load_all_cuisines(
            llm_cfg=self.llm,
            fallback_text=_DEFAULT_FALLBACK_TEXT,
        )

    def _build_assistant(self) -> Any:
        from qwen_agent.agents import Assistant

        return Assistant(
            llm=self.llm,
            system_message=self.system_prompt,
            function_list=self.tools,
            name="master_foodie",
            description="地球顶级美食家, 调度各菜系专家",
        )

    def _assistant_call_kwargs(self) -> dict[str, Any]:
        """给 FoodAgent.run 传给 assistant.run 的 kwargs.

        Note: MiniMax M3 的流式 tool_call 累积在 qwen-agent oai.py 中有 bug
        (function_call 字段会被错误合并/丢失), 所以强制 stream=False.
        详见: master.py 的 disable_stream flag.
        """
        return {"stream": False}

    def _get_or_create_stm(self, session_id: str) -> "ShortTermMemory":
        """懒加载 per-session 短期记忆."""
        if not hasattr(self, "_short_term_by_session"):
            self._short_term_by_session: dict[str, ShortTermMemory] = {}
        stm = self._short_term_by_session.get(session_id)
        if stm is None:
            stm = ShortTermMemory()
            self._short_term_by_session[session_id] = stm
        return stm

    def _recall_preferences_text(self, user_id: str, query: str) -> str:
        """召回用户偏好, 拼成 system message 文本. 失败 → ''"""
        if not self._long_term:
            return ""
        try:
            prefs = self._long_term.recall_for_query(user_id, query, top_k=3)
        except Exception as e:
            logger.warning("recall_for_query failed: %s", e)
            return ""
        if not prefs:
            return ""
        lines = [
            f"- {p.key}: {p.value} (confidence={p.confidence:.2f})"
            for p in prefs
        ]
        return "## 用户偏好 (从长期记忆召回)\n" + "\n".join(lines)

    def _persist_dietary_preferences(self, user_id: str, user_msg: str) -> None:
        """从 user_msg 抽取饮食限制并自动写入 long_term (Phase B).

        调用 DietaryAnalyzerTool.analyze() (纯函数, 无 LLM 调用), 把
        source == "msg" 的项写到 long_term. key 约定:
        - 硬约束 (allergy/religion): key = "allergy_<value>" / "religion_<code>"
        - 软偏好 (avoid): key = "avoid_<value>"

        fail-soft: 任何异常 logger.warning + return, 不挂上层.
        """
        if not self._long_term:
            return
        try:
            from food_agent.agents.analyzers.dietary import DietaryAnalyzerTool
            result = DietaryAnalyzerTool(long_term=self._long_term).analyze(
                user_msg, context={"user_id": user_id}
            )
        except Exception as e:
            logger.warning("dietary auto-save: analyze failed: %s", e)
            return

        try:
            for h in result.get("hard_constraints", []):
                if h.get("source") != "msg":
                    continue  # 跳过从 long_term 召回的, 不重复写
                prefix = "allergy" if h.get("type") == "allergy" else "religion"
                self._long_term.save_preference(
                    user_id, f"{prefix}_{h['value']}", h["value"],
                    confidence=0.9, source="explicit",
                )
            for s in result.get("soft_preferences", []):
                if s.get("source") != "msg":
                    continue
                self._long_term.save_preference(
                    user_id, f"avoid_{s['value']}", s["value"],
                    confidence=0.7, source="explicit",
                )
        except Exception as e:
            logger.warning("dietary auto-save: save_preference failed: %s", e)

    def run(
        self,
        user_msg: str,
        session_id: str | None = None,
        user_id: str = "default",
        history: list[dict] | None = None,
    ) -> str:
        """运行主流程.

        Args:
            user_msg: 用户消息.
            session_id: 会话 ID (Phase 2.5 短期记忆). 传 None 则无记忆 (Phase 1 行为).
            user_id: 用户 ID (Phase 2.6 长期记忆偏好召回/记录). 默认 "default".
            history: 显式历史消息 (可选, 优先级高于 session_id).

        Returns:
            Assistant 的最终回复.
        """
        if not user_msg or not user_msg.strip():
            return "（老饕听着呢, 你想吃啥？）"

        # 决定消息列表来源
        messages: list[dict] = []

        # 1. 长期记忆偏好召回 (作为 system message 注入到 messages 最前)
        if self._long_term and history is None:
            prefs_text = self._recall_preferences_text(user_id, user_msg)
            if prefs_text:
                messages.append({"role": "system", "content": prefs_text})

        # 2. 短期记忆 history (summary + 最近消息)
        if history is not None:
            messages.extend(list(history))
        elif session_id:
            stm = self._get_or_create_stm(session_id)
            messages.extend(stm.get_messages())

        # 3. 用户消息
        messages.append({"role": "user", "content": user_msg})

        try:
            responses = list(self._assistant.run(messages, **self._assistant_call_kwargs()))
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
        response = ""
        for msg in reversed(last_batch):
            content = self._extract_content(msg)
            if content and content.strip():
                response = content
                break
        if not response:
            return self._fallback_response()

        # 写回短期记忆
        if session_id and history is None:
            stm.add({"role": "user", "content": user_msg})
            stm.add({"role": "assistant", "content": response})
            if stm.should_summarize():
                try:
                    stm.summarize(self.llm)
                except Exception as e:  # 摘要失败不挂上层
                    logger.warning("summarize failed: %s", e)

        # 记录到长期记忆 (fail-soft)
        if self._long_term and history is None:
            try:
                self._long_term.record_recommendation(
                    session_id=session_id,
                    user_msg=user_msg,
                    result=response,
                )
            except Exception as e:
                logger.warning("record_recommendation failed: %s", e)
            # Phase B: 自动从 user_msg 抽饮食偏好并写入 long_term
            self._persist_dietary_preferences(user_id, user_msg)

        return response

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
