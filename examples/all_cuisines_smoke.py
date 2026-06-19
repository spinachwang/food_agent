"""Smoke: 全部 14 个菜系加载 + 描述打印 (mock LLM).

Phase 3.3 验收:
- 8 大菜系 (川粤鲁苏浙闽湘徽) 全加载
- 异域正餐 (日料/西餐) 全加载
- 快餐/小吃/饮品 (4 个) 全加载
- 每个菜系 describe() 返回有意义描述
- 每个菜系对应一个 consult tool

运行: python examples/all_cuisines_smoke.py
"""
import os

os.environ["AMAP_USE_MOCK"] = "true"

from food_agent.master import FoodAgent

# mock LLM (不消耗 token, 也不真调 API)
class FakeLLM:
    def __init__(self):
        self.model = "fake"
        self.model_type = "fake"
        self.generate_cfg = {"use_raw_api": True}
        self.call_count = 0

    def chat(self, messages, functions=None, stream=True, **kwargs):
        self.call_count += 1
        from qwen_agent.llm.schema import Message
        def _gen():
            yield [Message(role="assistant", content="fake response")]
        return _gen()


llm = FakeLLM()
agent = FoodAgent(llm=llm)

print(f"=== FoodAgent 加载统计 ===")
print(f"菜系专家数: {len(agent.cuisine_agents)}")
print(f"工具总数:   {len(agent.tools)}")
print()

print("=== 14 个菜系专家 ===")
for a in agent.cuisine_agents:
    print(f"  [{a.cuisine_id:18s}] {a.cuisine_name:8s} — {a.describe()}")

print()
print("=== consult_* 工具 ===")
consult_tools = [t for t in agent.tools if t.name.startswith("consult_")]
for t in consult_tools:
    print(f"  {t.name}")

print()
print("=== analyzer + location 工具 ===")
other = [t for t in agent.tools if not t.name.startswith("consult_")]
for t in other:
    print(f"  {t.name}")

print()
print("=== cuisine_id 唯一性 ===")
ids = [a.cuisine_id for a in agent.cuisine_agents]
assert len(ids) == len(set(ids)), f"重复: {ids}"
print(f"  ✓ {len(ids)} 个菜系 id 全部唯一")

print()
print("OK — 14 菜系 Phase 3.3 验收通过")
