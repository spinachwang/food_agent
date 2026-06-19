"""粤菜专家 (CantoneseAgent).

粤菜特点: 清淡鲜嫩, 讲究"生猛海鲜"和"老火靓汤". 擅长煲、蒸、炒.
代表: 白切鸡、烧鹅、清蒸石斑、老火汤、早茶虾饺、叉烧.

Phase 2.3: system_prompt 和 knowledge 从 .md 文件加载, 便于版本管理.
"""
from __future__ import annotations

from food_agent.agents.base import BaseCuisineAgent


class CantoneseAgent(BaseCuisineAgent):
    """粤菜专家 - 清淡鲜美, 汤水养人.

    prompt 模板: src/food_agent/config/prompts/cantonese_v1.md
    知识库:      src/food_agent/data/cuisines/cantonese.md
    """

    cuisine_id = "cantonese"
    cuisine_name = "粤菜"

    # Phase 2.3: 从文件加载 (优先级: 显式 > 文件 > 内联)
    prompt_file = "cantonese_v1.md"
    knowledge_file = "cantonese.md"

    def describe(self) -> str:
        return (
            "粤菜专家, 适合: 想吃得清淡/养胃/家庭聚餐/早茶/带老人小孩/广东本地. "
            "代表菜: 白切鸡、烧鹅、老火汤、早茶点心. "
            "慎选: 重口味嗜辣者、北方干冷冬天想吃暖身、追求刺激口感."
        )
