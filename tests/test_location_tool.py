"""测试 src/food_agent/tools/location.py (TDD).

Phase 3.2: LocationTool — 把 AmapClient 包装成 qwen-agent BaseTool.

设计:
- 5 个 tool 类 (Geocode / Regeocode / SearchAround / Weather / Route)
- 共享一个 AmapClient (类变量 set_client())
- 每个 .call(params) 返回 JSON 字符串
- params 解析失败 / AmapClient 失败 → error JSON (不抛)
"""
from __future__ import annotations

import json

import pytest

from food_agent.mcp.amap_client import AmapClient
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

@pytest.fixture
def amap_client():
    """mock 模式 AmapClient."""
    import os
    os.environ["AMAP_USE_MOCK"] = "true"
    os.environ["AMAP_API_KEY"] = "test-fake-key"
    c = AmapClient()
    set_amap_client(c)
    yield c
    set_amap_client(None)


# =============================================================================
# schema
# =============================================================================

def test_geocode_tool_name() -> None:
    assert GeocodeTool.name == "geocode"


def test_regeocode_tool_name() -> None:
    assert RegeocodeTool.name == "regeocode"


def test_search_around_tool_name() -> None:
    assert SearchAroundTool.name == "search_around"


def test_weather_tool_name() -> None:
    assert WeatherTool.name == "weather"


def test_route_tool_name() -> None:
    assert RouteTool.name == "route"


def test_all_tools_have_description() -> None:
    """每个 tool 类必须有非空 description."""
    for cls in [GeocodeTool, RegeocodeTool, SearchAroundTool, WeatherTool, RouteTool]:
        assert isinstance(cls.description, str) and len(cls.description) > 10


def test_all_tools_have_parameters_schema() -> None:
    """每个 tool 必须有 OpenAI JSON Schema parameters."""
    for cls in [GeocodeTool, RegeocodeTool, SearchAroundTool, WeatherTool, RouteTool]:
        params = cls.parameters
        assert isinstance(params, dict)
        assert params.get("type") == "object"
        assert "properties" in params
        assert "required" in params


def test_geocode_parameters_require_address() -> None:
    params = GeocodeTool.parameters
    assert "address" in params["required"]


def test_search_around_parameters_require_lng_lat_keywords() -> None:
    params = SearchAroundTool.parameters
    for f in ["lng", "lat", "keywords"]:
        assert f in params["required"]


def test_route_parameters_require_origin_dest() -> None:
    params = RouteTool.parameters
    assert "origin" in params["required"]
    assert "destination" in params["required"]


# =============================================================================
# .call() 行为
# =============================================================================

def test_geocode_call_returns_json_string(amap_client) -> None:
    """GeocodeTool.call 返回 JSON 字符串."""
    tool = GeocodeTool()
    result = tool.call(json.dumps({"address": "北京海淀中关村"}))
    assert isinstance(result, str)
    data = json.loads(result)
    assert "location" in data or "lng" in data


def test_geocode_call_no_client_returns_error() -> None:
    """未 set client → 返回 error JSON, 不抛."""
    set_amap_client(None)
    tool = GeocodeTool()
    result = tool.call(json.dumps({"address": "北京"}))
    data = json.loads(result)
    assert "error" in data


def test_geocode_call_invalid_json_returns_error(amap_client) -> None:
    """params 不是合法 JSON → error JSON, 不抛."""
    tool = GeocodeTool()
    result = tool.call("not a json")
    data = json.loads(result)
    assert "error" in data


def test_geocode_call_empty_address_returns_error(amap_client) -> None:
    """address 空 → AmapClient 返空, tool 返回带 error 提示的 JSON."""
    tool = GeocodeTool()
    result = tool.call(json.dumps({"address": ""}))
    data = json.loads(result)
    # 空地址 → geocode 返 {} → tool 应该给个 error 提示
    assert "error" in data or data == {}


def test_search_around_call(amap_client) -> None:
    """search_around.call 返回 POI list (JSON 字符串)."""
    tool = SearchAroundTool()
    result = tool.call(json.dumps({
        "lng": 116.3, "lat": 39.9, "keywords": "川菜", "radius": 2000
    }))
    data = json.loads(result)
    assert isinstance(data, list)
    assert len(data) > 0
    assert "name" in data[0]


def test_weather_call(amap_client) -> None:
    """weather.call 返回 dict."""
    tool = WeatherTool()
    result = tool.call(json.dumps({"city": "北京"}))
    data = json.loads(result)
    assert isinstance(data, dict)
    assert "city" in data or "weather" in data


def test_route_call(amap_client) -> None:
    """route.call 返回 dict."""
    tool = RouteTool()
    result = tool.call(json.dumps({
        "origin": "116.3,39.9", "destination": "116.4,40.0", "mode": "walking"
    }))
    data = json.loads(result)
    assert isinstance(data, dict)


def test_regeocode_call(amap_client) -> None:
    """regeocode.call 返回 dict."""
    tool = RegeocodeTool()
    result = tool.call(json.dumps({"location": "116.3,39.9"}))
    data = json.loads(result)
    assert isinstance(data, dict)


# =============================================================================
# Fail-soft
# =============================================================================

def test_call_fails_soft_when_amap_raises(amap_client, monkeypatch) -> None:
    """AmapClient.geocode 抛 → tool 返 error JSON, 不挂上层."""
    def _explode(address):
        raise RuntimeError("amap down")

    monkeypatch.setattr(amap_client, "geocode", _explode)
    tool = GeocodeTool()
    result = tool.call(json.dumps({"address": "北京"}))
    data = json.loads(result)
    assert "error" in data
    assert "amap down" in data["error"]


def test_call_fails_soft_when_amap_raises_search(monkeypatch) -> None:
    """search_around 抛 → error JSON."""
    import os
    os.environ["AMAP_USE_MOCK"] = "true"
    os.environ["AMAP_API_KEY"] = "test-fake-key"
    c = AmapClient()
    set_amap_client(c)
    try:
        def _explode(*args, **kwargs):
            raise RuntimeError("amap down")

        monkeypatch.setattr(c, "search_around", _explode)
        tool = SearchAroundTool()
        result = tool.call(json.dumps({"lng": 1, "lat": 2, "keywords": "x"}))
        data = json.loads(result)
        assert "error" in data
    finally:
        set_amap_client(None)


# =============================================================================
# get_amap_client / set_amap_client
# =============================================================================

def test_set_amap_client_overrides() -> None:
    """set_amap_client 多次调用, 后者覆盖前者."""
    import os
    os.environ["AMAP_USE_MOCK"] = "true"
    os.environ["AMAP_API_KEY"] = "k"
    c1 = AmapClient()
    c2 = AmapClient()
    set_amap_client(c1)
    set_amap_client(c2)
    tool = GeocodeTool()
    # 验证 c2 是当前 client (通过 c2.mock_geocode 的 call_count)
    import food_agent.tools.location as loc_mod
    assert loc_mod._amap_client is c2


def test_get_amap_client_returns_current() -> None:
    """get_amap_client 拿到 set 进去的 client."""
    import os
    os.environ["AMAP_USE_MOCK"] = "true"
    os.environ["AMAP_API_KEY"] = "k"
    c = AmapClient()
    set_amap_client(c)
    from food_agent.tools.location import get_amap_client
    assert get_amap_client() is c
    set_amap_client(None)
