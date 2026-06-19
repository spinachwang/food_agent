"""甜品饮品专家 (DessertDrinkAgent).

甜品饮品特点: 奶茶/咖啡/糖水/烘焙/冰淇淋, 主打"场景适配"+"解辣/解腻"+"下午茶".
代表: 喜茶、奈雪的茶、瑞幸、Manner、M Stand、星巴克、海底捞甜品站.

Phase 2.3: system_prompt 和 knowledge 从 .md 文件加载, 便于版本管理.
"""
from __future__ import annotations

from food_agent.agents.base import BaseCuisineAgent


class DessertDrinkAgent(BaseCuisineAgent):
    """甜品饮品专家 - 城市甜品地图绘制者, 哪家奶茶不排队、哪家咖啡适合办公.

    prompt 模板: src/food_agent/config/prompts/dessert_drink_v1.md
    知识库:      src/food_agent/data/cuisines/dessert_drink.md
    """

    cuisine_id = "dessert_drink"
    cuisine_name = "甜品饮品"

    # Phase 2.3: 从文件加载 (优先级: 显式 > 文件 > 内联)
    prompt_file = "dessert_drink_v1.md"
    knowledge_file = "dessert_drink.md"

    def describe(self) -> str:
        return (
            "甜品饮品专家, 适合: 下午茶/约会/工作提神/解辣解腻/餐后/逛街歇脚. "
            "代表: 奶茶（喜茶多肉葡萄）、咖啡（瑞幸生椰拿铁）、糖水（杨枝甘露）、烘焙（可颂/巴斯克）. "
            "慎选: 糖尿病/减脂期、对咖啡因敏感、商务正餐、商务宴请."
        )
