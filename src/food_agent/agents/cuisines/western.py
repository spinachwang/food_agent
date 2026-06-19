"""西餐专家 (WesternAgent).

西餐特点: 西式正餐（前菜-主菜-甜品）, 法/意/美/德分支分明. 牛排、意面、配酒为核心.
代表: 牛排、意面、鹅肝、生蚝、鞑靼牛肉、提拉米苏、可颂.

注意: 西餐 = 西式正餐. 必胜客、麦当劳、肯德基等快餐不算西餐.

Phase 2.3: system_prompt 和 knowledge 从 .md 文件加载, 便于版本管理.
"""
from __future__ import annotations

from food_agent.agents.base import BaseCuisineAgent


class WesternAgent(BaseCuisineAgent):
    """西餐专家 - 牛排意面, 西式正餐仪式感.

    prompt 模板: src/food_agent/config/prompts/western_v1.md
    知识库:      src/food_agent/data/cuisines/western.md
    """

    cuisine_id = "western"
    cuisine_name = "西餐"

    # Phase 2.3: 从文件加载 (优先级: 显式 > 文件 > 内联)
    prompt_file = "western_v1.md"
    knowledge_file = "western.md"

    def describe(self) -> str:
        return (
            "西餐专家, 适合: 商务宴请/约会/纪念日/异国体验/想喝酒/想尝试牛排意面. "
            "代表菜: 牛排、意面、鹅肝、生蚝、鞑靼牛肉、提拉米苏. "
            "慎选: 想要吃饱/预算紧张/不接受生食(鞑靼/medium 以下)/不会用刀叉/快节奏."
        )
