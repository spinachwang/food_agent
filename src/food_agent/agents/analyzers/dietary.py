"""analyze_dietary: 抽取硬约束 (过敏/宗教/医学) + 软偏好 + 喜欢偏好.

Phase 3.2 精简版 3 维分析器之一 (安全关键).
Phase B-2 升级: LLM 抽取 (语义理解, 覆盖正向偏好/隐含偏好), keyword 抽取兜底.

设计:
- 硬约束: 100% 排除 (过敏是医学问题, 不能 LLM 推测, 但 LLM 抽更准)
- 软偏好: 建议避开
- 喜欢偏好: 用户喜欢/爱吃/偏好 (新增, LLM 抽才能识别)
- 整合 long_term: 已知偏好自动加载

抽取策略 (analyze()):
- 有 self._llm → _llm_extract (LLM 语义理解, 准)
- 无 self._llm → _keyword_extract (纯规则, 0 token)
- LLM 返回无效 JSON → 降级到 _keyword_extract (fail-soft)
"""
from __future__ import annotations

import json
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
    "糖",  # 糖尿病免糖 (description 已提到, keyword 漏掉 → Phase B 补)
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
    # 甜食系 (Phase B)
    "甜", "甜食", "甜点", "蛋糕", "冰淇淋", "奶茶", "糖水",
]
# 软偏好否定模式: "不爱吃 X" / "不吃 X" / "讨厌 X" / "嫌 X"
_SOFT_AVOID_PATTERN = re.compile(
    r"(不爱吃|不喜欢|不爱|不吃|不要|讨厌|嫌|拒绝)"
    r"\s*(" + "|".join(re.escape(k) for k in SOFT_AVOID_KEYWORDS) + r")"
)


# LLM 抽取的 prompt (Phase B-2)
_LLM_EXTRACT_PROMPT = """你是饮食偏好抽取助手. 从用户消息中提取结构化偏好.

返回严格 JSON (不要任何解释):
{{
  "hard_constraints": [
    {{"type": "allergy", "value": "花生", "must_exclude": true, "source": "msg"}}
  ],
  "soft_preferences": [
    {{"type": "avoid", "value": "香菜", "should_avoid": true, "source": "msg"}}
  ],
  "like_preferences": [
    {{"type": "like", "value": "辣", "should_prefer": true, "source": "msg"}}
  ],
  "has_restrictions": true,
  "confidence": 0.9
}}

字段说明:
- hard_constraints: 必须 100% 排除 (过敏/宗教/医学, type: allergy/religion)
- soft_preferences: 建议避开 (不爱吃/嫌/不要, type: avoid)
- like_preferences: 偏好 (喜欢/爱吃/最/尤其/偏好, type: like) - 这是新维度
- has_restrictions: true if hard 或 soft 不空
- confidence: 0-1, 默认 0.85
- source 永远填 "msg"

value 提取规则:
- 食物: 花生/海鲜/螃蟹/...
- 口味: 辣/酸/甜/咸/麻/苦/...
- 烹饪: 油炸/烧烤/蒸/凉拌/...
- 菜系: 川菜/粤菜/...
- 场景: 宵夜/下午茶/...

隐含偏好也识别:
- "减脂" → soft_preferences: ["油炸", "甜食", "高糖"]
- "重口" → like_preferences: ["重口"] (用户喜欢重的)
- "清淡" → soft_preferences: ["重口"] OR like_preferences: ["清淡"] 看语境

用户消息: {user_msg}"""


class DietaryAnalyzerTool(_AnalyzerToolBase):
    """提取用户饮食限制 (硬约束 + 软偏好 + 喜欢偏好).

    用法:
        analyze_dietary(user_msg="我对花生过敏, 不爱吃香菜", context={"user_id": "alice"})
    """

    name = "analyze_dietary"
    description = (
        "提取用户的饮食限制. "
        "硬约束 (must_exclude=true) 必须 100% 排除: 过敏 (花生/海鲜/牛奶/...), "
        "宗教 (清真/素食/犹太), 医学 (糖尿病免糖/痛风免内脏). "
        "软偏好 (should_avoid=true) 建议避开: 不爱吃香菜/葱/内脏. "
        "喜欢偏好 (should_prefer=true): 用户喜欢/爱吃/最/尤其. "
        "返回 {hard_constraints, soft_preferences, like_preferences, has_restrictions, confidence}."
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

    def __init__(
        self,
        long_term: Any = None,
        llm: Any = None,
        **kwargs: Any,
    ) -> None:
        """初始化.

        Args:
            long_term: LongTermMemory 实例 (Phase 2.6). None 时只用 user_msg 抽取.
            llm: LLM 实例 (Phase B-2). None 时走 keyword 抽取. 有则优先 LLM, 失败降级.
            **kwargs: 透传给 BaseTool.
        """
        super().__init__(**kwargs)
        self._long_term = long_term
        self._llm = llm

    def analyze(self, user_msg: str, context: dict | None = None) -> dict[str, Any]:
        """分析用户饮食偏好.

        Phase B-2: 有 llm 时走 _llm_extract, 否则 _keyword_extract. LLM 失败降级.
        长期记忆 (long_term) 整合独立于抽取路径, 始终执行.
        """
        ctx = context or {}

        # Phase B-2: LLM 抽取 (有 self._llm 时)
        if self._llm is not None:
            try:
                extracted = self._llm_extract(user_msg or "")
            except Exception as e:
                logger.warning("dietary _llm_extract failed, fallback to keyword: %s", e)
                extracted = self._keyword_extract(user_msg or "")
        else:
            extracted = self._keyword_extract(user_msg or "")

        # 长期记忆整合 (无论 LLM 还是 keyword 都加这一步)
        lt = self._collect_long_term(ctx.get("user_id"))
        extracted["hard_constraints"].extend(lt["hard"])
        extracted["soft_preferences"].extend(lt["soft"])
        extracted["like_preferences"] = extracted.get("like_preferences", []) + lt.get("like", [])

        # 重新计算 has_restrictions (LLM 输出可能没含 long_term 加的)
        extracted["has_restrictions"] = bool(
            extracted["hard_constraints"] or extracted["soft_preferences"]
        )
        return extracted

    # =================================================================
    # Phase B-2: LLM 抽取
    # =================================================================

    def _llm_extract(self, user_msg: str) -> dict[str, Any]:
        """调 LLM 抽结构化偏好. 失败 → 抛异常让上层降级.

        返回 dict 必须含 hard_constraints / soft_preferences / like_preferences /
        has_restrictions / confidence 字段.
        """
        from qwen_agent.llm.schema import Message

        prompt = _LLM_EXTRACT_PROMPT.format(user_msg=user_msg)
        msgs = [Message(role="user", content=prompt)]
        # 注: MiniMax M3 (use_raw_api=True) 必须 stream=True, 否则抛
        # "use_raw_api only support full stream". dietary 是 fire-and-forget,
        # 不在乎返回时机, 用 stream=True 兼容所有 LLM.
        # 流式响应: thinking 增量 + 最终 JSON 在最后一个 batch
        responses = list(self._llm.chat(msgs, stream=True))
        if not responses:
            raise RuntimeError("LLM returned no responses")

        # 合并所有 batches 的 content (流式 thinking 拼接)
        # 实际: 最后一个 batch 含完整 think + JSON
        content = ""
        for batch in responses:
            if isinstance(batch, list) and batch:
                msg = batch[0]
                c = msg.content if hasattr(msg, "content") else str(msg)
                if c:
                    content = c  # 最后一个非空 batch 含最终内容
            elif hasattr(batch, "content"):
                c = batch.content
                if c:
                    content = c

        if not content or not content.strip():
            raise RuntimeError("LLM returned empty content")

        # 解析 JSON (可能被 LLM 包了 <think>...</think> + markdown ```json...```)
        content = content.strip()
        # 去掉 <think>...</think> block (MiniMax M3 deepseek 模式)
        if "</think>" in content:
            content = content.split("</think>", 1)[1].strip()
        if "<think>" in content:
            content = content.split("<think>", 1)[0].strip()
        # 去掉 markdown code fence
        if content.startswith("```"):
            lines = content.split("\n")
            if lines and lines[-1].strip().startswith("```"):
                content = "\n".join(lines[1:-1])
            else:
                content = "\n".join(lines[1:])
            content = content.strip()
            if content.startswith("json"):
                content = content[4:].strip()

        result = json.loads(content)
        # 兼容缺字段
        result.setdefault("hard_constraints", [])
        result.setdefault("soft_preferences", [])
        result.setdefault("like_preferences", [])
        result.setdefault(
            "has_restrictions",
            bool(result["hard_constraints"] or result["soft_preferences"]),
        )
        result.setdefault("confidence", 0.85)
        # 标准化 source
        for h in result["hard_constraints"]:
            h.setdefault("source", "msg")
        for s in result["soft_preferences"]:
            s.setdefault("source", "msg")
        for l in result["like_preferences"]:
            l.setdefault("source", "msg")
        return result

    # =================================================================
    # Phase 3.2: keyword 抽取 (Phase B-2 降级路径)
    # =================================================================

    def _keyword_extract(self, user_msg: str) -> dict[str, Any]:
        """纯 keyword + regex 抽取 (无 LLM 调用, 0 token)."""
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
                "verb": verb,
                "should_avoid": True,
                "source": "msg",
            })

        has_restrictions = bool(hard or soft)
        return {
            "hard_constraints": hard,
            "soft_preferences": soft,
            "like_preferences": [],  # keyword 抽不支持 like
            "has_restrictions": has_restrictions,
            "confidence": 0.9 if hard else 0.7 if soft else 0.5,
        }

    # =================================================================
    # 长期记忆整合 (公共)
    # =================================================================

    def _collect_long_term(self, user_id: str | None) -> dict[str, list]:
        """从 long_term 召回已知偏好. 失败 → 空 dict."""
        if not user_id or self._long_term is None:
            return {"hard": [], "soft": [], "like": []}
        try:
            prefs = self._long_term.get_preferences(user_id, min_confidence=0.5)
        except Exception as e:
            logger.warning("dietary: get_preferences failed: %s", e)
            return {"hard": [], "soft": [], "like": []}

        hard: list[dict[str, Any]] = []
        soft: list[dict[str, Any]] = []
        like: list[dict[str, Any]] = []
        for p in prefs:
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
            elif p.key.startswith("like_"):  # Phase B-2 新增
                like.append({
                    "type": "like",
                    "key": p.key,
                    "value": p.value,
                    "should_prefer": True,
                    "source": "long_term",
                    "confidence": p.confidence,
                })
        return {"hard": hard, "soft": soft, "like": like}


__all__ = ["DietaryAnalyzerTool"]