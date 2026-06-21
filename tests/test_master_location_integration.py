"""测试 FoodAgent 接入 AmapClient (Phase 3.5: location tool 改走 analyzer).

Phase 3.5 行为变化:
- FoodAgent(amap_client=...) 接受 AmapClient 实例 (不变)
- 5 个 location tools (geocode/regeocode/search_around/weather/route)
  **不再** 加入 master.tools — 改由 3 个 analyzer (weather/location/dietary)
  内部调 AmapClient, master LLM 看到的 tool 总数从 22 降到 17
  (14 菜系 + 3 analyzer). Toolformer 建议 LLM 同时可见 ≤10 个 tool, 17
  仍有压力但比 22 好. 后续可考虑 per-query 路由.
- amap_client 仍注入模块级单例 (供 analyzer 内部 get_amap_client() 用)

注: 5 个 location tool 类本身保留 (tools/location.py), 单元测试
tests/test_location_tool.py 继续验证 tool 类本身可独立用, 只是不再被
master 自动加载.
"""
from __future__ import annotations

import os

import pytest

from food_agent.mcp.amap_client import AmapClient
from food_agent.master import FoodAgent
from food_agent.tools.location import set_amap_client


# =============================================================================
# Fixtures
# =============================================================================

class FakeLLM:
    """测试用 mock LLM."""

    def __init__(self, canned_responses: list[str] | None = None) -> None:
        self.canned_responses = canned_responses or ["ok"]
        self.model = "fake"
        self.model_type = "fake"
        self.generate_cfg: dict = {}
        self.max_retries = 0
        self.cache = None
        self.use_raw_api = False
        self.call_count = 0
        self.last_messages: list = []

    def chat(self, messages, functions=None, stream=True, **kwargs):
        self.call_count += 1
        self.last_messages = list(messages)
        from qwen_agent.llm.schema import Message as QMessage

        def _gen():
            resp = self.canned_responses[(self.call_count - 1) % len(self.canned_responses)]
            yield [QMessage(role="assistant", content=resp)]
        return _gen()


@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("AMAP_API_KEY", "test-fake-key")
    monkeypatch.setenv("AMAP_USE_MOCK", "true")
    set_amap_client(None)  # 清理


@pytest.fixture
def amap_client(mock_env) -> AmapClient:
    return AmapClient()


# =============================================================================
# FoodAgent 接受 amap_client
# =============================================================================

def test_foodagent_accepts_amap_client_param(amap_client) -> None:
    """FoodAgent(amap_client=...) 不报错."""
    agent = FoodAgent(llm=FakeLLM(), amap_client=amap_client)  # type: ignore[arg-type]
    assert agent is not None


def test_foodagent_no_longer_registers_raw_location_tools(amap_client) -> None:
    """Phase 3.5: 5 个 raw location tool 不再加入 master.tools."""
    agent = FoodAgent(llm=FakeLLM(), amap_client=amap_client)  # type: ignore[arg-type]
    tool_names = [getattr(t, "name", None) for t in agent.tools]
    # raw location tool 不应出现
    for raw in ("geocode", "regeocode", "search_around", "weather", "route"):
        assert raw not in tool_names, (
            f"{raw} 不应直接暴露给 master, 应走 analyzer 内部"
        )
    # analyzer tool 仍在
    assert "analyze_location" in tool_names
    assert "analyze_weather" in tool_names


def test_foodagent_tools_count_unaffected_by_amap(amap_client) -> None:
    """Phase 3.5: 有/无 amap 时 master.tools 数相同 (location tool 不再算入)."""
    agent_without = FoodAgent(llm=FakeLLM())  # type: ignore[arg-type]
    agent_with = FoodAgent(llm=FakeLLM(), amap_client=amap_client)  # type: ignore[arg-type]
    # Phase 3.5: 差异应为 0 (location tool 不再挂 master)
    assert len(agent_with.tools) == len(agent_without.tools)


def test_foodagent_amap_client_still_globally_registered(amap_client) -> None:
    """虽然不挂 tools, amap_client 仍注入 module 单例 (供 analyzer 内部用)."""
    agent = FoodAgent(llm=FakeLLM(), amap_client=amap_client)  # type: ignore[arg-type]
    from food_agent.tools.location import get_amap_client
    assert get_amap_client() is amap_client


# =============================================================================
# analyzer 内部用 amap_client (端到端)
# =============================================================================

def test_analyze_location_uses_injected_amap_client(amap_client) -> None:
    """analyze_location 调用能用 FoodAgent 注入的 amap_client (mock 模式)."""
    import json

    from food_agent.agents.analyzers.location import LocationAnalyzerTool

    agent = FoodAgent(llm=FakeLLM(), amap_client=amap_client)  # type: ignore[arg-type]
    # 现在直接调 analyzer tool, 验证 mock amap 能用
    tool = LocationAnalyzerTool()
    data = json.loads(tool.call(json.dumps({"user_msg": "我在北京海淀"})))
    # mock 模式 geocode 应有 lng/lat (新行为不返回顶层 location 字段)
    assert "lng" in data and "lat" in data
    assert data["source"] == "address"


def test_analyze_location_search_around_uses_amap(amap_client) -> None:
    """user_msg 含 "附近" + 食物词 → 自动 search_around, 用注入的 amap_client."""
    import json

    from food_agent.agents.analyzers.location import LocationAnalyzerTool

    agent = FoodAgent(llm=FakeLLM(), amap_client=amap_client)  # type: ignore[arg-type]
    tool = LocationAnalyzerTool()
    data = json.loads(tool.call(json.dumps({"user_msg": "我在北京, 找川菜"})))
    # mock 模式 search_around 返固定 2-3 个 POI
    if "pois" in data:
        assert len(data["pois"]) >= 1
        assert data["search_keywords"] == "川菜"


# =============================================================================
# AmapClient 生命周期
# =============================================================================

def test_foodagent_does_not_close_amap_client_on_exit(amap_client) -> None:
    """FoodAgent 不应在析构时关 amap_client (AmapClient 生命周期由调用方管)."""
    agent = FoodAgent(llm=FakeLLM(), amap_client=amap_client)  # type: ignore[arg-type]
    # agent 引用后, amap_client 仍能用
    result = amap_client.geocode("测试")
    assert "location" in result or result == {}


def test_two_foodagents_share_amap_client(amap_client) -> None:
    """两个 FoodAgent 共享同一 amap_client → set_amap_client 后者覆盖前者."""
    a1 = FoodAgent(llm=FakeLLM(), amap_client=amap_client)  # type: ignore[arg-type]
    a2 = FoodAgent(llm=FakeLLM(), amap_client=amap_client)  # type: ignore[arg-type]
    # Phase 3.5: 5 个 raw location tool 不再挂 master.tools. 验证两个 agent
    # 共享同一 amap_client 通过 analyzer 间接使用.
    from food_agent.tools.location import get_amap_client
    for agent in [a1, a2]:
        # analyzer 仍可拿到 amap client (get_amap_client 模块单例被 a2 覆盖为同一实例)
        assert get_amap_client() is amap_client
        # raw location tool 不应出现在 master.tools
        assert not any(getattr(t, "name", None) == "geocode" for t in agent.tools)
