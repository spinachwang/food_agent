"""徽菜专家 (AnhuiAgent).

徽菜特点: 重油重色, 火腿炖菜与山珍野味结合. 臭鳜鱼是灵魂, 徽商带动全国传播.
代表: 臭鳜鱼、毛豆腐、火腿炖甲鱼、胡适一品锅、徽州毛峰豆腐干.

Phase 2.3: system_prompt 和 knowledge 从 .md 文件加载, 便于版本管理.
"""
from __future__ import annotations

from food_agent.agents.base import BaseCuisineAgent


class AnhuiAgent(BaseCuisineAgent):
    """徽菜专家 - 重油重色, 山珍火腿的徽商味道.

    prompt 模板: src/food_agent/config/prompts/anhui_v1.md
    知识库:      src/food_agent/data/cuisines/anhui.md
    """

    cuisine_id = "anhui"
    cuisine_name = "徽菜"

    # Phase 2.3: 从文件加载 (优先级: 显式 > 文件 > 内联)
    prompt_file = "anhui_v1.md"
    knowledge_file = "anhui.md"

    def describe(self) -> str:
        return (
            "徽菜专家, 适合: 想吃山珍野味/安徽本地/重油重色/秋冬滋补/商务宴请. "
            "代表菜: 臭鳜鱼、毛豆腐、火腿炖甲鱼、胡适一品锅. "
            "慎选: 怕臭/怕重油/清淡饮食/海鲜过敏(部分菜)/减脂期."
        )
