"""Smoke: FoodAgent 完整流程 (mock LLM + 真 amap)."""
import os
# 强制真 amap
os.environ["AMAP_USE_MOCK"] = "false"

from food_agent.mcp.amap_client import AmapClient
from food_agent.master import FoodAgent

# 真 amap client
amap = AmapClient(use_mock=False)
print("Amap 工具数:", len(amap.list_tools()))

# FoodAgent 带 amap
agent = FoodAgent(
    llm={"model": "fake", "model_server": "http://x", "api_key": "fake",
         "generate_cfg": {"use_raw_api": True}},  # 模拟 llm
    amap_client=amap,
)
print(f"FoodAgent 工具数: {len(agent.tools)} (含 {sum(1 for t in agent.tools if 'geocode' in (getattr(t, 'name', '') or '') or 'search' in (getattr(t, 'name', '') or '') or 'weather' in (getattr(t, 'name', '') or '') or 'route' in (getattr(t, 'name', '') or ''))} 个 location tool)")

# 直接用 location tools 模拟一次"我在北京, 找川菜"
print("\n--- 模拟用户: 我在北京海淀, 找附近 2km 川菜 ---")
geo = agent.tools[[getattr(t, "name", "") for t in agent.tools].index("geocode")].call('{"address": "北京海淀中关村"}')
print("geocode →", geo[:150])

pois = agent.tools[[getattr(t, "name", "") for t in agent.tools].index("search_around")].call(
    '{"lng": 116.31862, "lat": 39.980047, "keywords": "川菜", "radius": 2000}'
)
print("search_around →", pois[:200])

print("\nOK")
amap.close()