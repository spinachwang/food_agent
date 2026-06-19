"""小吃专家 (SnackAgent).

小吃特点: 街边摊 + 早餐 + 夜宵 + 地域特色, 场景分散但文化密度极高.
代表: 包子、煎饼、肉夹馍、凉皮、麻辣烫、烧烤、各地特色小吃.

Phase 2.3: system_prompt 和 knowledge 从 .md 文件加载, 便于版本管理.
"""
from __future__ import annotations

from food_agent.agents.base import BaseCuisineAgent


class SnackAgent(BaseCuisineAgent):
    """小吃专家 - 老饕中的夜行者, 凌晨 2 点的烧烤摊老板都认识.

    prompt 模板: src/food_agent/config/prompts/snack_v1.md
    知识库:      src/food_agent/data/cuisines/snack.md
    """

    cuisine_id = "snack"
    cuisine_name = "小吃"

    # Phase 2.3: 从文件加载 (优先级: 显式 > 文件 > 内联)
    prompt_file = "snack_v1.md"
    knowledge_file = "snack.md"

    def describe(self) -> str:
        return (
            "小吃专家, 适合: 夜宵/早餐/赶时间/解馋/地域体验/想尝鲜. "
            "代表: 各地特色小吃（西安肉夹馍、上海生煎、广州肠粉、长沙臭豆腐、成都钵钵鸡、北京卤煮）. "
            "慎选: 正式商务宴请、对环境要求高、不能吃辣、大量用餐（小吃分量小）."
        )
