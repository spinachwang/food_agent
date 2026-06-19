"""闽菜专家 (FujianAgent).

闽菜特点: 汤汤水水, 讲究"原汤原味"和"红糟"调味. 福州菜、闽南菜、客家菜三大分支.
代表: 佛跳墙、荔枝肉、沙茶面、海蛎煎、土笋冻、福州鱼丸.

Phase 2.3: system_prompt 和 knowledge 从 .md 文件加载, 便于版本管理.
"""
from __future__ import annotations

from food_agent.agents.base import BaseCuisineAgent


class FujianAgent(BaseCuisineAgent):
    """闽菜专家 - 鲜汤海鲜, 山海协作.

    prompt 模板: src/food_agent/config/prompts/fujian_v1.md
    知识库:      src/food_agent/data/cuisines/fujian.md
    """

    cuisine_id = "fujian"
    cuisine_name = "闽菜"

    # Phase 2.3: 从文件加载 (优先级: 显式 > 文件 > 内联)
    prompt_file = "fujian_v1.md"
    knowledge_file = "fujian.md"

    def describe(self) -> str:
        return (
            "闽菜专家, 适合: 海鲜爱好者/想喝汤/清淡养生/福建本地/春夏尝鲜. "
            "代表菜: 佛跳墙、荔枝肉、沙茶面、海蛎煎、土笋冻. "
            "慎选: 重口味嗜辣者/痛风患者(海鲜高嘌呤)/北方干冷冬天想吃暖辣."
        )
