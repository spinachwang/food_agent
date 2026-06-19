"""中式快餐专家 (ChineseFastfoodAgent).

中式快餐特点: 工作日午餐场景的"15-30 元搞定一顿", 平价 + 高效 + 饱腹.
代表: 沙县小吃、兰州拉面、黄焖鸡米饭、桂林米粉、真功夫、吉野家、嘉和一品.

Phase 2.3: system_prompt 和 knowledge 从 .md 文件加载, 便于版本管理.
"""
from __future__ import annotations

from food_agent.agents.base import BaseCuisineAgent


class ChineseFastfoodAgent(BaseCuisineAgent):
    """中式快餐专家 - 全国县城到 CBD 的打工人饭搭子.

    prompt 模板: src/food_agent/config/prompts/chinese_fastfood_v1.md
    知识库:      src/food_agent/data/cuisines/chinese_fastfood.md
    """

    cuisine_id = "chinese_fastfood"
    cuisine_name = "中式快餐"

    # Phase 2.3: 从文件加载 (优先级: 显式 > 文件 > 内联)
    prompt_file = "chinese_fastfood_v1.md"
    knowledge_file = "chinese_fastfood.md"

    def describe(self) -> str:
        return (
            "中式快餐专家, 适合: 工作日午餐/赶时间/一人食/预算 15-30 元. "
            "代表: 沙县拌面蒸饺、兰州拉面、黄焖鸡米饭、桂林米粉、真功夫. "
            "慎选: 商务宴请、家庭聚餐、对环境有要求、追求地域特色."
        )
