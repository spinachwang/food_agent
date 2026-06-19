"""苏菜专家 (JiangsuAgent).

苏菜特点: 清淡平和, 精致典雅. 淮扬菜主体, 刀工火候并重, 国宴常用.
代表: 松鼠鳜鱼、狮子头、蟹粉汤包、大煮干丝、文思豆腐、扬州炒饭.

Phase 2.3: system_prompt 和 knowledge 从 .md 文件加载, 便于版本管理.
"""
from __future__ import annotations

from food_agent.agents.base import BaseCuisineAgent


class JiangsuAgent(BaseCuisineAgent):
    """苏菜专家 - 精致淡雅, 文人菜与国宴代表.

    prompt 模板: src/food_agent/config/prompts/jiangsu_v1.md
    知识库:      src/food_agent/data/cuisines/jiangsu.md
    """

    cuisine_id = "jiangsu"
    cuisine_name = "苏菜"

    # Phase 2.3: 从文件加载 (优先级: 显式 > 文件 > 内联)
    prompt_file = "jiangsu_v1.md"
    knowledge_file = "jiangsu.md"

    def describe(self) -> str:
        return (
            "苏菜专家, 适合: 想吃清淡精致/商务宴请/带老人/尝国宴/江浙沪/春秋季. "
            "代表菜: 松鼠鳜鱼、蟹粉狮子头、大煮干丝、文思豆腐. "
            "慎选: 想吃辣/重口味/北方冬天想吃暖身硬菜."
        )
