"""Analyzer 工具基类.

3 个 analyzer (weather / location / dietary) 都继承 _AnalyzerToolBase,
共享参数解析 + 错误处理 + JSON 序列化的模式.

设计参考: src/food_agent/tools/location.py 的 _AmapToolBase.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from qwen_agent.tools.base import BaseTool

logger = logging.getLogger(__name__)


class BaseAnalyzer(ABC):
    """概念类: 所有 analyzer 实现这个接口.

    不是 BaseTool 子类, 仅做类型提示和文档用.
    真正的 tool 类 (_AnalyzerToolBase 子类) 同时实现本类的 analyze().
    """

    analyzer_id: str = ""
    description: str = ""

    @abstractmethod
    def analyze(self, user_msg: str, context: dict | None = None) -> dict[str, Any]:
        """分析用户消息 + 上下文, 返回结构化结果.

        Args:
            user_msg: 用户原始消息.
            context: 上下文 (含 user_id, client_ip, city 等).

        Returns:
            结构化 dict, 必含 'confidence' 字段 (0-1).
            失败/无法分析 → {"confidence": 0.0, "error": "..."}.
        """


class _AnalyzerToolBase(BaseTool, BaseAnalyzer):
    """所有 analyzer tool 的共同行为.

    - 解析 params (JSON 字符串)
    - 调 self.analyze(user_msg, context)
    - 返回 JSON 字符串结果
    - 失败 → error JSON, 不抛
    """

    def call(self, params: str, **kwargs: Any) -> str:
        client = get_amap_client_or_none()  # noqa: F821 (compatibility placeholder)
        # 解析 params
        if not params or not params.strip():
            return json.dumps({"error": "params 为空"}, ensure_ascii=False)
        try:
            args = json.loads(params)
        except json.JSONDecodeError as e:
            return json.dumps(
                {"error": f"params 不是合法 JSON: {e}"}, ensure_ascii=False,
            )
        if not isinstance(args, dict):
            return json.dumps(
                {"error": f"params 必须是 JSON object, 收到 {type(args).__name__}"},
                ensure_ascii=False,
            )

        # 抽 user_msg / context
        user_msg = args.get("user_msg", args.get("query", ""))
        context = {
            k: v
            for k, v in args.items()
            if k not in ("user_msg", "query")
        }

        # 调 analyze
        try:
            result = self.analyze(user_msg, context=context)
        except Exception as e:
            logger.warning("%s.analyze failed: %s", self.__class__.__name__, e)
            return json.dumps(
                {"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False,
            )

        if result is None:
            result = {"confidence": 0.0, "error": "analyze returned None"}

        return json.dumps(result, ensure_ascii=False)


# 占位: 实际位置工具 import 由 location.py 决定, 这里只是 stub
def get_amap_client_or_none():
    """lazy import, 避免循环依赖."""
    from food_agent.tools.location import get_amap_client
    return get_amap_client()


__all__ = ["BaseAnalyzer", "_AnalyzerToolBase"]