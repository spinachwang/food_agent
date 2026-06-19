"""浙菜专家 (ZhejiangAgent).

浙菜特点: 鲜嫩软滑, 江南鱼米之乡. 选料讲究, "鲜"字当头.
代表: 西湖醋鱼、龙井虾仁、东坡肉、宋嫂鱼羹、叫花鸡、清汤越鸡.

Phase 2.3: system_prompt 和 knowledge 从 .md 文件加载, 便于版本管理.
"""
from __future__ import annotations

from food_agent.agents.base import BaseCuisineAgent


class ZhejiangAgent(BaseCuisineAgent):
    """浙菜专家 - 江南鱼米之乡, 鲜嫩软滑.

    prompt 模板: src/food_agent/config/prompts/zhejiang_v1.md
    知识库:      src/food_agent/data/cuisines/zhejiang.md
    """

    cuisine_id = "zhejiang"
    cuisine_name = "浙菜"

    # Phase 2.3: 从文件加载 (优先级: 显式 > 文件 > 内联)
    prompt_file = "zhejiang_v1.md"
    knowledge_file = "zhejiang.md"

    def describe(self) -> str:
        return (
            "浙菜专家, 适合: 江南/春秋季/尝鲜/清淡偏好/带老人小孩/文人主题. "
            "代表菜: 西湖醋鱼、龙井虾仁、东坡肉、宋嫂鱼羹. "
            "慎选: 想吃辣/北方冬天想吃硬菜/海鲜过敏（部分菜）."
        )
