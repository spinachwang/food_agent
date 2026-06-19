"""日料专家 (JapaneseAgent).

日料特点: 讲究"旬"(时令) 与"一生悬命"的职人精神. 寿司、刺身、烧鸟、拉面、怀石各成体系.
代表: 寿司、刺身、怀石、烧鸟、天妇罗、拉面、鳗鱼饭.

Phase 2.3: system_prompt 和 knowledge 从 .md 文件加载, 便于版本管理.
"""
from __future__ import annotations

from food_agent.agents.base import BaseCuisineAgent


class JapaneseAgent(BaseCuisineAgent):
    """日料专家 - 旬味精致, 寿司刺身怀石各成派.

    prompt 模板: src/food_agent/config/prompts/japanese_v1.md
    知识库:      src/food_agent/data/cuisines/japanese.md
    """

    cuisine_id = "japanese"
    cuisine_name = "日料"

    # Phase 2.3: 从文件加载 (优先级: 显式 > 文件 > 内联)
    prompt_file = "japanese_v1.md"
    knowledge_file = "japanese.md"

    def describe(self) -> str:
        return (
            "日料专家, 适合: 商务宴请/约会/想吃得精致清淡/日料爱好者/异国体验. "
            "代表菜: 寿司、刺身、怀石、烧鸟、拉面、鳗鱼饭. "
            "慎选: 不会用筷子/海鲜过敏/想要吃饱/预算有限(高端日料昂贵)/不敢吃生."
        )
