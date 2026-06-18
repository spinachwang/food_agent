"""E2E smoke test: 真实 LLM 验证 'I want spicy' -> 川菜推荐.

运行方法 (需要 MINIMAX_API_KEY 环境变量):
    /c/Users/PC/miniconda3/envs/qwenagent-mcp/python.exe examples/e2e_real_llm.py

或者用 mock:
    /c/Users/PC/miniconda3/envs/qwenagent-mcp/python.exe examples/e2e_real_llm.py --mock
"""
from __future__ import annotations

import os
import sys
import time


def main() -> int:
    """真实 LLM E2E 测试入口."""
    if "--mock" in sys.argv:
        from tests.test_cuisine_agent import FakeLLM

        llm = FakeLLM([
            # 每个 query 一次响应, FakeLLM 自动循环
            "调用川菜专家: 推荐陈麻婆豆腐, 必点麻婆豆腐和夫妻肺片. "
            "中辣, 适合大多数能吃辣的人. 成都春熙路总店最正宗.",
            "天气冷, 推火锅或水煮鱼. 蜀九香、小龙坎都不错.",
            "川菜经典: 麻婆豆腐(中辣)、回锅肉、鱼香肉丝、水煮鱼.",
            "深秋适合羊肉汤配川味凉菜, 但你预算 100 的话, 推荐冒菜.",
        ])
        from food_agent.master import FoodAgent

        agent = FoodAgent(llm=llm)
    else:
        from food_agent.master import FoodAgent

        agent = FoodAgent()

    queries = [
        "我想吃辣的, 一个人, 预算 100",
        "今天下雨, 想吃点热乎的",
        "有什么川菜推荐?",
    ]

    print("=" * 60)
    print("Food Agent E2E (real LLM)")
    print("=" * 60)

    for q in queries:
        print(f"\n>>> 用户: {q}")
        start = time.time()
        try:
            result = agent.run(q)
            elapsed = time.time() - start
            print(f"\n<<< 老饕 ({elapsed:.1f}s):")
            print(result)
        except Exception as e:
            print(f"\n!!! 错误: {e}")
            if not os.environ.get("MINIMAX_API_KEY"):
                print("(未设置 MINIMAX_API_KEY, 改用 --mock 模式)")
                return 1
            return 1
        print("-" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())