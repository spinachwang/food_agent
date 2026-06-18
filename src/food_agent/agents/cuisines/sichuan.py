"""川菜专家 (SichuanAgent).

川菜特点: 一菜一格, 百菜百味. 麻辣为主, 兼有鱼香、怪味、家常等.
代表: 麻婆豆腐、回锅肉、水煮鱼、夫妻肺片、担担面、钟水饺.

Phase 2.3: system_prompt 和 knowledge 从 .md 文件加载, 便于版本管理.
"""
from __future__ import annotations

from food_agent.agents.base import BaseCuisineAgent


class SichuanAgent(BaseCuisineAgent):
    """川菜专家 - 麻辣鲜香, 重口味之王.

    prompt 模板: src/food_agent/config/prompts/sichuan_v1.md
    知识库:      src/food_agent/data/cuisines/sichuan.md
    """

    cuisine_id = "sichuan"
    cuisine_name = "川菜"

    # Phase 2.3: 从文件加载 (优先级: 显式 > 文件 > 内联)
    prompt_file = "sichuan_v1.md"
    knowledge_file = "sichuan.md"

    def describe(self) -> str:
        return (
            "川菜专家, 适合: 想吃辣/重口味/聚餐/夜宵/天气冷. "
            "代表菜: 麻婆豆腐、回锅肉、火锅. "
            "慎选: 不能吃辣、肠胃敏感、孕期/哺乳期."
        )