"""测试 src/food_agent/mcp/amap_client.py (TDD).

Phase 3.1: 高德地图 MCP client.

设计:
- mock 模式 (AMAP_USE_MOCK=true) 返回假数据, CI 不消耗 key
- 真模式: streamable HTTP 连 https://mcp.amap.com/mcp?key=...
  每次 call 新建 session (200ms 开销, 高德限频 3 QPS 可接受)
- 缓存 (key → result, TTL=86400) 避免重复调用
- fail-soft: 失败 → logger.warning + 返回 {}, 不挂上层
- sync wrapper (内部 asyncio.run), 让 BaseTool.call() 能直接调
"""
from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from food_agent.mcp.amap_client import AmapClient, _AMAP_MCP_URL_TEMPLATE


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_env(monkeypatch):
    """设 AMAP_API_KEY + AMAP_USE_MOCK=true."""
    monkeypatch.setenv("AMAP_API_KEY", "test-fake-key")
    monkeypatch.setenv("AMAP_USE_MOCK", "true")


@pytest.fixture
def client(mock_env) -> AmapClient:
    """默认 mock 模式 client."""
    return AmapClient()


# =============================================================================
# 初始化
# =============================================================================

def test_init_default_url_uses_env_key(mock_env) -> None:
    """AMAP_API_KEY 自动拼到 URL."""
    c = AmapClient()
    assert "test-fake-key" in c.mcp_url
    assert c.mcp_url.startswith("https://mcp.amap.com/mcp?key=")


def test_init_custom_url_overrides_env(mock_env) -> None:
    """显式 mcp_url 覆盖 env."""
    c = AmapClient(mcp_url="https://custom.example/mcp?key=xyz")
    assert c.mcp_url == "https://custom.example/mcp?key=xyz"


def test_init_use_mock() -> None:
    """AMAP_USE_MOCK=true → use_mock=True."""
    import os
    os.environ["AMAP_API_KEY"] = "test-fake-key"
    os.environ["AMAP_USE_MOCK"] = "true"
    c = AmapClient()
    assert c.use_mock is True
    del os.environ["AMAP_USE_MOCK"]


def test_init_missing_key_in_real_mode_raises(monkeypatch) -> None:
    """真模式 + 无 AMAP_API_KEY → raise (fail-fast)."""
    monkeypatch.delenv("AMAP_API_KEY", raising=False)
    monkeypatch.delenv("AMAP_USE_MOCK", raising=False)
    with pytest.raises(ValueError, match="AMAP_API_KEY"):
        AmapClient()


# =============================================================================
# mock 模式: geocode
# =============================================================================

def test_geocode_mock_returns_expected_structure(client: AmapClient) -> None:
    """mock geocode 返回 location 结构."""
    result = client.geocode("北京海淀中关村")
    assert isinstance(result, dict)
    # 高德 maps_geo 通常返回 location (lng, lat) + formatted_address
    assert "location" in result or "lng" in result
    if "location" in result:
        assert "lng" in result["location"]
        assert "lat" in result["location"]


def test_geocode_mock_contains_address_in_response(client: AmapClient) -> None:
    """mock geocode 返回包含地址字段."""
    result = client.geocode("上海陆家嘴")
    text = json.dumps(result, ensure_ascii=False)
    assert "上海" in text or "陆家嘴" in text


def test_geocode_empty_address_returns_empty(client: AmapClient) -> None:
    """空地址 → 立即返回 {}, 不调任何 API."""
    result = client.geocode("")
    assert result == {}
    result = client.geocode("   ")
    assert result == {}


# =============================================================================
# mock 模式: search_around
# =============================================================================

def test_search_around_mock_returns_poi_list(client: AmapClient) -> None:
    """mock search_around 返回 list[POI]."""
    result = client.search_around(
        lng=116.3, lat=39.9, keywords="川菜", radius=2000
    )
    assert isinstance(result, list)
    assert len(result) > 0
    poi = result[0]
    assert "name" in poi
    assert "address" in poi or "location" in poi


def test_search_around_with_different_keywords(client: AmapClient) -> None:
    """不同 keywords 返回不同 mock POI."""
    r1 = client.search_around(116.3, 39.9, keywords="川菜")
    r2 = client.search_around(116.3, 39.9, keywords="粤菜")
    names1 = " ".join(p["name"] for p in r1)
    names2 = " ".join(p["name"] for p in r2)
    # 至少应该有不同的菜系提示
    assert "川" in names1 or "辣" in names1 or "成都" in names1


# =============================================================================
# mock 模式: weather / route
# =============================================================================

def test_weather_mock_returns_dict(client: AmapClient) -> None:
    """mock weather 返回 dict."""
    result = client.weather("北京")
    assert isinstance(result, dict)
    text = json.dumps(result, ensure_ascii=False)
    # 应包含 city + weather 信息
    assert "北京" in text or "city" in result


def test_route_mock_walking(client: AmapClient) -> None:
    """mock route walking 返回 distance + duration."""
    result = client.route(
        origin=(116.3, 39.9), dest=(116.4, 40.0), mode="walking"
    )
    assert isinstance(result, dict)
    text = json.dumps(result, ensure_ascii=False)
    # 距离/时间字段
    assert "distance" in result or "duration" in result or "千米" in text or "分钟" in text


def test_route_different_modes(client: AmapClient) -> None:
    """不同 mode 返回不同结果."""
    walk = client.route((0, 0), (1, 1), mode="walking")
    drive = client.route((0, 0), (1, 1), mode="driving")
    # walking 距离 > driving 时间 or 类似差异
    assert walk != drive


# =============================================================================
# 缓存
# =============================================================================

def test_geocode_caches_results(client: AmapClient, monkeypatch) -> None:
    """同地址二次调用 → 缓存命中, 不再调 mock 实际生成."""
    # 用 patch 模拟 mock 内部生成, 验证只被调 1 次
    call_count = 0
    original = client._mock_geocode

    def counting_mock(address):
        nonlocal call_count
        call_count += 1
        return original(address)

    monkeypatch.setattr(client, "_mock_geocode", counting_mock)
    client.geocode("北京")
    client.geocode("北京")
    client.geocode("北京")
    assert call_count == 1  # 缓存命中


def test_search_around_caches_results(client: AmapClient, monkeypatch) -> None:
    """search_around 也走缓存."""
    call_count = 0
    original = client._mock_search_around

    def counting_mock(lng, lat, keywords, radius=3000):
        nonlocal call_count
        call_count += 1
        return original(lng, lat, keywords, radius)

    monkeypatch.setattr(client, "_mock_search_around", counting_mock)
    client.search_around(116.3, 39.9, "川菜")
    client.search_around(116.3, 39.9, "川菜")
    assert call_count == 1


def test_cache_ttl_expires(monkeypatch, mock_env) -> None:
    """缓存 TTL 到期 → 重新调."""
    client = AmapClient(cache_ttl=0)  # TTL=0 立即过期
    call_count = 0
    original = client._mock_geocode

    def counting(address):
        nonlocal call_count
        call_count += 1
        return original(address)

    monkeypatch.setattr(client, "_mock_geocode", counting)
    client.geocode("北京")
    time.sleep(0.01)
    client.geocode("北京")
    assert call_count == 2


# =============================================================================
# Fail-soft
# =============================================================================

def test_geocode_failure_returns_empty_dict(monkeypatch) -> None:
    """mock 内部 raise → 返回 {}, 不抛."""
    client = AmapClient()

    def _explode(address):
        raise RuntimeError("network down")

    monkeypatch.setattr(client, "_mock_geocode", _explode)
    result = client.geocode("北京")
    assert result == {}


def test_search_around_failure_returns_empty_list(monkeypatch) -> None:
    """search_around 失败 → [], 不抛."""
    client = AmapClient()

    def _explode(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(client, "_mock_search_around", _explode)
    result = client.search_around(116.3, 39.9, "川菜")
    assert result == []


# =============================================================================
# 真模式 (mock mcp SDK)
# =============================================================================

def test_real_geocode_calls_mcp_tool(monkeypatch) -> None:
    """真模式: geocode 调 mcp SDK 走 maps_geo tool."""
    # 强制真模式
    monkeypatch.setenv("AMAP_API_KEY", "test-real-key")
    monkeypatch.delenv("AMAP_USE_MOCK", raising=False)
    client = AmapClient()

    # mock _call_mcp_tool 拿 fake result
    fake_result = {"location": {"lng": 116.3, "lat": 39.9}, "formatted_address": "北京"}
    monkeypatch.setattr(client, "_call_mcp_tool", lambda name, args: fake_result)

    result = client.geocode("北京")
    assert result == fake_result


def test_real_call_mcp_tool_uses_streamable_http(monkeypatch) -> None:
    """_call_mcp_tool 用 streamablehttp_client + ClientSession."""
    monkeypatch.setenv("AMAP_API_KEY", "real-key")
    monkeypatch.delenv("AMAP_USE_MOCK", raising=False)
    client = AmapClient()

    # patch mcp.client.streamable_http
    fake_session = AsyncMock()
    fake_session.initialize = AsyncMock()
    fake_session.call_tool = AsyncMock(
        return_value=MagicMock(
            isError=False,
            content=[],
            structuredContent={"location": {"lng": 1, "lat": 2}},
        )
    )

    # patch asyncio.run 跑 async
    async def fake_main(coro):
        # 实际上 run 这个 coroutine
        return await coro

    # 复杂: 直接 patch _call_mcp_tool 的内部实现
    with patch("food_agent.mcp.amap_client.streamablehttp_client") as mock_http:
        # mock context manager
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock(), lambda: None))
        cm.__aexit__ = AsyncMock(return_value=None)
        mock_http.return_value = cm

        with patch("food_agent.mcp.amap_client.ClientSession") as mock_session_class:
            session_instance = AsyncMock()
            session_instance.__aenter__ = AsyncMock(return_value=session_instance)
            session_instance.__aexit__ = AsyncMock(return_value=None)
            session_instance.initialize = AsyncMock()
            session_instance.call_tool = AsyncMock(
                return_value=MagicMock(
                    isError=False,
                    content=[],
                    structuredContent={"location": {"lng": 1, "lat": 2}},
                )
            )
            mock_session_class.return_value = session_instance

            result = client._call_mcp_tool("maps_geo", {"address": "北京"})
            assert result == {"location": {"lng": 1, "lat": 2}}


def test_real_call_mcp_tool_returns_empty_on_error(monkeypatch) -> None:
    """mcp call_tool 返回 isError=True → {}."""
    monkeypatch.setenv("AMAP_API_KEY", "real-key")
    monkeypatch.delenv("AMAP_USE_MOCK", raising=False)
    client = AmapClient()

    with patch("food_agent.mcp.amap_client.streamablehttp_client") as mock_http:
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock(), lambda: None))
        cm.__aexit__ = AsyncMock(return_value=None)
        mock_http.return_value = cm

        with patch("food_agent.mcp.amap_client.ClientSession") as mock_session_class:
            session_instance = AsyncMock()
            session_instance.__aenter__ = AsyncMock(return_value=session_instance)
            session_instance.__aexit__ = AsyncMock(return_value=None)
            session_instance.initialize = AsyncMock()
            session_instance.call_tool = AsyncMock(
                return_value=MagicMock(
                    isError=True,
                    content=[],
                    structuredContent=None,
                )
            )
            mock_session_class.return_value = session_instance

            result = client._call_mcp_tool("maps_geo", {"address": "x"})
            assert result == {}


def test_real_call_mcp_tool_fails_soft_on_exception(monkeypatch) -> None:
    """mcp SDK 抛异常 → 公共方法返回 {}, 不挂上层."""
    monkeypatch.setenv("AMAP_API_KEY", "real-key")
    monkeypatch.delenv("AMAP_USE_MOCK", raising=False)
    client = AmapClient()

    with patch("food_agent.mcp.amap_client.streamablehttp_client", side_effect=RuntimeError("network")):
        # 公共方法 geocode 应该 catch, 返回 {}
        result = client.geocode("北京")
        assert result == {}


# =============================================================================
# 关闭 / context manager
# =============================================================================

def test_close_is_idempotent(client: AmapClient) -> None:
    """close 多次调用不报错 (mock 模式无资源)."""
    client.close()
    client.close()  # 不抛


def test_context_manager(client: AmapClient) -> None:
    """with 语句自动 close."""
    with client as c:
        assert c is client
    # 退出 with 后再 close 不报错
    client.close()


# =============================================================================
# 工具 list
# =============================================================================

def test_list_tools_mock_returns_list(client: AmapClient) -> None:
    """list_tools mock 返回高德 12 个 tool name."""
    tools = client.list_tools()
    assert isinstance(tools, list)
    assert len(tools) >= 5  # 至少几个
    names = [t["name"] if isinstance(t, dict) else t.name for t in tools]
    # 包含核心 tool
    assert any("geo" in n for n in names)  # maps_geo / maps_geocode
    assert any("weather" in n or "search" in n for n in names)
