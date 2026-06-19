"""端到端 smoke test: 直接调 FoodAgent.run 走完整 master → tool → master 链路."""
import sys

from food_agent.master import FoodAgent

print("=" * 60)
print("Food Agent E2E smoke test")
print("=" * 60)

agent = FoodAgent()
print(f"\nagent: {agent!r}")
print(f"tools: {[t.name for t in agent.tools]}\n")

try:
    response = agent.run("我想吃辣的, 一个人, 预算 100")
    print("\n" + "=" * 60)
    print("✅ SUCCESS — master → tool → master 全链路跑通!")
    print("=" * 60)
    print(response)
    sys.exit(0)
except Exception as e:
    print("\n" + "=" * 60)
    print(f"❌ FAILED: {type(e).__name__}: {e}")
    print("=" * 60)
    sys.exit(1)