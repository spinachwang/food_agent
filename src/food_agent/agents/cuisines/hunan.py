"""湘菜专家 (HunanAgent).

湘菜特点: 辣得纯正, 酸辣、香辣、腊辣, 与川菜"麻辣"区别明显. 重油重色, 嗜辣者的圣地.
代表: 剁椒鱼头、毛氏红烧肉、辣椒炒肉、口味虾、臭豆腐、腊味合蒸.

Phase 2.3: system_prompt 和 knowledge 从 .md 文件加载, 便于版本管理.
"""
from __future__ import annotations

from food_agent.agents.base import BaseCuisineAgent


class HunanAgent(BaseCuisineAgent):
    """湘菜专家 - 酸辣醇厚, 嗜辣者终极归宿.

    prompt 模板: src/food_agent/config/prompts/hunan_v1.md
    知识库:      src/food_agent/data/cuisines/hunan.md
    """

    cuisine_id = "hunan"
    cuisine_name = "湘菜"

    # Phase 2.3: 从文件加载 (优先级: 显式 > 文件 > 内联)
    prompt_file = "hunan_v1.md"
    knowledge_file = "hunan.md"

    def describe(self) -> str:
        return (
            "湘菜专家, 适合: 嗜辣者/想吃纯辣非麻辣/重口味/夜宵/湖南湖北本地. "
            "代表菜: 剁椒鱼头、毛氏红烧肉、辣椒炒肉、口味虾. "
            "慎选: 不能吃辣/肠胃敏感/孕期/小孩/口腔溃疡/痔疮发作."
        )
