"""鲁菜专家 (ShandongAgent).

鲁菜特点: 咸鲜为主, 讲究火候与吊汤. 北方菜系之首, 宫廷菜渊源.
代表: 糖醋鲤鱼、九转大肠、油爆海螺、葱烧海参、孔府菜.

Phase 2.3: system_prompt 和 knowledge 从 .md 文件加载, 便于版本管理.
"""
from __future__ import annotations

from food_agent.agents.base import BaseCuisineAgent


class ShandongAgent(BaseCuisineAgent):
    """鲁菜专家 - 咸鲜醇厚, 北方菜系之宗.

    prompt 模板: src/food_agent/config/prompts/shandong_v1.md
    知识库:      src/food_agent/data/cuisines/shandong.md
    """

    cuisine_id = "shandong"
    cuisine_name = "鲁菜"

    # Phase 2.3: 从文件加载 (优先级: 显式 > 文件 > 内联)
    prompt_file = "shandong_v1.md"
    knowledge_file = "shandong.md"

    def describe(self) -> str:
        return (
            "鲁菜专家, 适合: 想吃北方硬菜/商务宴请/重油重味/冬天暖身/山东/北京. "
            "代表菜: 糖醋鲤鱼、九转大肠、葱烧海参、孔府家宴. "
            "慎选: 想吃清淡/海鲜过敏（部分菜）/小孩/老人肠胃弱."
        )
