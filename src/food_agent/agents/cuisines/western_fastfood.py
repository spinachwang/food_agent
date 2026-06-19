"""西式快餐专家 (WesternFastfoodAgent).

西式快餐特点: 标准化、连锁化、效率优先, 主打"快+平+稳".
代表: 麦当劳、肯德基、汉堡王、必胜客、达美乐、赛百味、塔可贝尔.

Phase 2.3: system_prompt 和 knowledge 从 .md 文件加载, 便于版本管理.
"""
from __future__ import annotations

from food_agent.agents.base import BaseCuisineAgent


class WesternFastfoodAgent(BaseCuisineAgent):
    """西式快餐专家 - 全球连锁餐饮观察家, 横扫洋快餐隐藏菜单.

    prompt 模板: src/food_agent/config/prompts/western_fastfood_v1.md
    知识库:      src/food_agent/data/cuisines/western_fastfood.md
    """

    cuisine_id = "western_fastfood"
    cuisine_name = "西式快餐"

    # Phase 2.3: 从文件加载 (优先级: 显式 > 文件 > 内联)
    prompt_file = "western_fastfood_v1.md"
    knowledge_file = "western_fastfood.md"

    def describe(self) -> str:
        return (
            "西式快餐专家, 适合: 赶时间/一人食/带小孩/平价聚餐/深夜觅食. "
            "代表: 麦当劳巨无霸、肯德基吮指原味鸡、必胜客披萨、汉堡王皇堡. "
            "慎选: 商务宴请、对食材品质要求高、追求仪式感."
        )
