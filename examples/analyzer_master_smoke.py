"""Smoke: FoodAgent + 真 amap + analyzer tools 端到端 (mock LLM).

模拟用户: \"我对花生过敏, 今天想吃川菜\" →
1. analyze_dietary 抽 \"花生过敏\" 硬约束
2. analyze_location / analyze_weather 走 mock 模式 (没 IP / 城市抽取)
3. consult_sichuan 调用
"""
import os
import json

os.environ["AMAP_USE_MOCK"] = "true"

from food_agent.mcp.amap_client import AmapClient
from food_agent.master import FoodAgent

amap = AmapClient()  # mock 模式

# mock LLM (避免消耗 token)
class FakeLLM:
    def __init__(self, responses):
        self.responses = responses
        self.model = "fake"
        self.model_type = "fake"
        self.generate_cfg = {"use_raw_api": True}
        self.call_count = 0
        self.last_messages = []

    def chat(self, messages, functions=None, stream=True, **kwargs):
        self.call_count += 1
        self.last_messages = list(messages)
        from qwen_agent.llm.schema import Message
        def _gen():
            yield [Message(role="assistant", content=self.responses[(self.call_count - 1) % len(self.responses)])]
        return _gen()

llm = FakeLLM([
    "{\"name\": \"analyze_dietary\", \"arguments\": \"{\\\"user_msg\\\": \\\"我对花生过敏\\\"}\"}",
    "{\"name\": \"consult_sichuan\", \"arguments\": \"{\\\"user_query\\\": \\\"川菜推荐\\\"}\"}",
    "🎯 推荐: 陈麻婆豆腐 (排除花生类)",
])
agent = FoodAgent(llm=llm, amap_client=amap)

print(f"Tool 数: {len(agent.tools)}")
print("Tool 名:", [t.name for t in agent.tools])
print()

# 直接调 analyzer tool 验证 schema + 行为
print("=== analyze_dietary 直接调 ===")
dietary_tool = next(t for t in agent.tools if t.name == "analyze_dietary")
result = dietary_tool.call(json.dumps({"user_msg": "我对花生过敏, 不爱吃香菜"}))
data = json.loads(result)
print(json.dumps(data, ensure_ascii=False, indent=2))

print("\n=== analyze_weather 直接调 ===")
weather_tool = next(t for t in agent.tools if t.name == "analyze_weather")
result = weather_tool.call(json.dumps({"user_msg": "今天北京热, 吃啥"}))
data = json.loads(result)
print(json.dumps(data, ensure_ascii=False, indent=2))

print("\n=== analyze_location 直接调 ===")
loc_tool = next(t for t in agent.tools if t.name == "analyze_location")
result = loc_tool.call(json.dumps({"user_msg": "我在上海"}))
data = json.loads(result)
print(json.dumps(data, ensure_ascii=False, indent=2))

print("\nOK")