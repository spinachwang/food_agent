"""analyze_dietary: 提取硬约束 (过敏/宗教/医学) + 软偏好.

Phase 3.2 精简版 3 维分析器之一 (安全关键).

设计:
- 硬约束: 100% 排除 (过敏是医学问题, 不能 LLM 推测)
- 软偏好: 建议避开
- 整合 long_term: 已知偏好自动加载
"""
from __future__ import annotations

import logging
import re
from typing import Any

from food_agent.agents.analyzers.base import _AnalyzerToolBase

logger = logging.getLogger(__name__)

# 硬约束: 过敏
ALLERGY_KEYWORDS = [
    "花生", "坚果", "腰果", "杏仁", "核桃",
    "海鲜", "虾", "蟹", "螃蟹", "龙虾", "贝类", "牡蛎", "生蚝", "海鱼",
    "牛奶", "乳糖", "奶制品", "酸奶", "奶酪",
    "鸡蛋", "蛋类",
    "麸质", "面筋", "小麦",
    "大豆", "黄豆", "豆腐",
    "芝麻",
]
# 硬约束: 宗教 / 素食
RELIGION_KEYWORDS = {
    "清真": "halal",
    "halal": "halal",
    "穆斯林": "halal",
    "素食": "vegetarian",
    "素": "vegetarian",
    "vegan": "vegan",
    "纯素": "vegan",
    "佛教": "buddhist_vegetarian",
    "全素": "vegan",
    "印度教": "hindu_vegetarian",
    "犹太": "kosher",
    "kosher": "kosher",
}
# 软偏好: 关键词 (food_name). 用 regex 匹配 "不(?:吃|爱|喜欢)?X" / "不吃X" 等模式.
SOFT_AVOID_KEYWORDS = [
    "香菜", "葱", "蒜", "苦瓜", "内脏",
    "肥肉", "皮", "骨头",
]
# 软偏好否定模式: "不爱吃 X" / "不吃 X" / "讨厌 X" / "嫌 X"
_SOFT_AVOID_PATTERN = re.compile(
    r"(不爱吃|不喜欢|不爱|不吃|不要|讨厌|嫌|拒绝)"
    r"\s*(" + "|".join(re.escape(k) for k in SOFT_AVOID_KEYWORDS) + r")"
)


class DietaryAnalyzerTool(_AnalyzerToolBase):
    """提取用户饮食限制 (硬约束 + 软偏好).

    用法:
        analyze_dietary(user_msg="我对花生过敏, 不爱吃香菜", context={"user_id": "alice"})
    """

    name = "analyze_dietary"
    description = (
        "提取用户的饮食限制. "
        "硬约束 (must_exclude=true) 必须 100% 排除: 过敏 (花生/海鲜/牛奶/...), "
        "宗教 (清真/素食/犹太), 医学 (糖尿病免糖/痛风免内脏). "
        "软偏好 (should_avoid=true) 建议避开: 不爱吃香菜/葱/内脏. "
        "返回 {hard_constraints, soft_preferences, has_restrictions, confidence}."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "user_msg": {
                "type": "string",
                "description": "用户消息, 含饮食限制描述",
            },
            "user_id": {
                "type": "string",
                "description": "可选, 用户 ID (查长期记忆中的已知偏好)",
            },
        },
        "required": [],
    }

    def __init__(self, long_term: Any = None, **kwargs: Any) -> None:
        """初始化.

        Args:
            long_term: LongTermMemory 实例 (Phase 2.6). None 时只用 user_msg 抽取.
            **kwargs: 透传给 BaseTool.
        """
        super().__init__(**kwargs)
        self._long_term = long_term

    def analyze(self, user_msg: str, context: dict | None = None) -> dict[str, Any]:
        ctx = context or {}
        msg_lc = (user_msg or "").lower()
        hard: list[dict[str, Any]] = []
        soft: list[dict[str, Any]] = []

        # 1. 硬约束: 过敏
        for kw in ALLERGY_KEYWORDS:
            if kw in (user_msg or ""):
                hard.append({
                    "type": "allergy",
                    "value": kw,
                    "must_exclude": True,
                    "source": "msg",
                })

        # 2. 硬约束: 宗教
        for kw, code in RELIGION_KEYWORDS.items():
            if kw.lower() in msg_lc:
                # 避免重复
                if not any(h.get("value") == code for h in hard):
                    hard.append({
                        "type": "religion",
                        "value": code,
                        "must_exclude": True,
                        "source": "msg",
                    })

        # 3. 软偏好: regex 匹配 "不爱 X" / "不吃 X" 等
        for m in _SOFT_AVOID_PATTERN.finditer(user_msg or ""):
            verb, food = m.group(1), m.group(2)
            soft.append({
                "type": "avoid",
                "value": food,
                "verb": verb,  # "不爱" / "不吃" 等
                "should_avoid": True,
                "source": "msg",
            })

        # 4. 长期记忆整合
        user_id = ctx.get("user_id")
        if user_id and self._long_term is not None:
            try:
                prefs = self._long_term.get_preferences(user_id, min_confidence=0.5)
            except Exception as e:
                logger.warning("dietary: get_preferences failed: %s", e)
                prefs = []
            for p in prefs:
                # 约定: key 以 "allergy_" / "no_" / "religion_" 开头视为硬约束
                if p.key.startswith(("allergy_", "no_", "religion_")):
                    hard.append({
                        "type": "from_memory",
                        "key": p.key,
                        "value": p.value,
                        "must_exclude": True,
                        "source": "long_term",
                        "confidence": p.confidence,
                    })
                elif p.key.startswith("avoid_"):
                    soft.append({
                        "type": "avoid",
                        "key": p.key,
                        "value": p.value,
                        "should_avoid": True,
                        "source": "long_term",
                        "confidence": p.confidence,
                    })

        has_restrictions = bool(hard or soft)
        return {
            "hard_constraints": hard,
            "soft_preferences": soft,
            "has_restrictions": has_restrictions,
            "confidence": 0.9 if hard else 0.7 if soft else 0.5,
        }


__all__ = ["DietaryAnalyzerTool"]