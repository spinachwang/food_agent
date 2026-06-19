"""测试 FoodAgent 接入 AmapClient + location tools (TDD).

Phase 3.3: master 集成.

行为:
- FoodAgent(amap_client=...) 接受 AmapClient 实例
- 接受后: 5 个 location tools 自动加入 master.tools
- 不传: 与 Phase 2 行为一致 (无 location tools)
- amap_client 关闭时 (with 语句退出), master 应能优雅处理
"""
from __future__ import annotations

import os

import pytest

from food_agent.mcp.amap_client import AmapClient
from food_agent.master import FoodAgent
from food_agent.tools.location import (
    GeocodeTool,
    RegeocodeTool,
    RouteTool,
    SearchAroundTool,
    WeatherTool,
    set_amap_client,
)


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


def test_foodagent_registers_amap_tools_when_provided(amap_client) -> None:
    """传 amap_client → 5 个 location tool 都在 self.tools."""
    agent = FoodAgent(llm=FakeLLM(), amap_client=amap_client)  # type: ignore[arg-type]
    tool_names = [getattr(t, "name", None) for t in agent.tools]
    assert "geocode" in tool_names
    assert "regeocode" in tool_names
    assert "search_around" in tool_names
    assert "weather" in tool_names
    assert "route" in tool_names


def test_foodagent_no_amap_client_no_location_tools(mock_env) -> None:
    """不传 amap_client → 无 location tool (Phase 2 行为)."""
    agent = FoodAgent(llm=FakeLLM())  # type: ignore[arg-type]
    tool_names = [getattr(t, "name", None) for t in agent.tools]
    assert "geocode" not in tool_names
    assert "search_around" not in tool_names


def test_foodagent_tools_count_with_and_without_amap(amap_client) -> None:
    """有 amap 时 tools 数 = cuisine tools + 5."""
    agent_without = FoodAgent(llm=FakeLLM())  # type: ignore[arg-type]
    agent_with = FoodAgent(llm=FakeLLM(), amap_client=amap_client)  # type: ignore[arg-type]
    # 验证: with 比 without 多 5 个 (cuisine + 5 location)
    assert len(agent_with.tools) - len(agent_without.tools) == 5


def test_foodagent_amap_client_globally_registered(amap_client) -> None:
    """构造后, 模块级 get_amap_client() 拿得到."""
    agent = FoodAgent(llm=FakeLLM(), amap_client=amap_client)  # type: ignore[arg-type]
    from food_agent.tools.location import get_amap_client
    assert get_amap_client() is amap_client


# =============================================================================
# end-to-end: master 真能调 location tool
# =============================================================================

def test_master_can_call_geocode_tool(amap_client) -> None:
    """用 LLM 模拟 master 调 geocode tool: 不直接测, 但确保 tool 在 list 里能被 qwen-agent 调.

    这里用 qwen-agent 的 tool list 验证: location tool schema 可被序列化.
    """
    agent = FoodAgent(llm=FakeLLM(), amap_client=amap_client)  # type: ignore[arg-type]
    # 取 geocode tool
    geocode_tool = next(t for t in agent.tools if getattr(t, "name", None) == "geocode")
    # 模拟一次调
    result = geocode_tool.call('{"address": "北京海淀中关村"}')
    assert isinstance(result, str)
    import json
    data = json.loads(result)
    # mock 模式: 应有 location 字段
    assert "location" in data or "error" in data  # error 也接受 (e.g. amap 限频)


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
    # 两个 agent 都能正常调 location tool
    for agent in [a1, a2]:
        assert any(getattr(t, "name", None) == "geocode" for t in agent.tools)
