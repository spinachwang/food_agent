"""高德地图 MCP client.

Phase 3.1.

通过 MCP 协议 (streamable HTTP) 连高德官方 server:
  https://mcp.amap.com/mcp?key=<AMAP_API_KEY>

提供 12 个 tool (maps_geo, maps_regeocode, maps_around_search, maps_weather,
maps_direction_walking 等), 见 https://lbs.amap.com/api/mcp-server/

设计:
- mock 模式 (AMAP_USE_MOCK=true) → 返回假数据, 不消耗 key
- 真模式 → 每次 call 新建 mcp session (asyncio.run)
  开销 ~200ms, 高德限频 3 QPS, 一次推荐流程 2-3 次 call 可接受
- 内存缓存 (TTL 默认 1 天) 避免重复同 key 调用
- fail-soft: 任何异常 → logger.warning + 返回空, 不挂上层
- sync API (内部 asyncio.run), 方便 qwen-agent BaseTool 调
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

# 顶部 load .env, 保证 AmapClient 独立可用 (不依赖 FoodAgent/llm.py 已 import)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # pragma: no cover
    pass

# mcp SDK 顶层 import, 便于 test patch.
# mock 模式不会实际调用, 启动开销 ~50ms 可接受.
try:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    _MCP_AVAILABLE = True
except ImportError:  # pragma: no cover
    _MCP_AVAILABLE = False
    ClientSession = None  # type: ignore[assignment]
    streamablehttp_client = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_AMAP_MCP_URL_TEMPLATE = "https://mcp.amap.com/mcp?key={key}"


class AmapClient:
    """高德地图 MCP client.

    用法:
        >>> client = AmapClient()  # 默认读 env, mock 模式由 AMAP_USE_MOCK 控制
        >>> result = client.geocode("北京海淀中关村")
        >>> pois = client.search_around(116.3, 39.9, "川菜", radius=2000)

    或 with 语句:
        >>> with AmapClient() as c:
        ...     c.geocode("...")

    Attributes:
        mcp_url: 实际 MCP server URL
        use_mock: 是否 mock 模式
        cache_ttl: 缓存 TTL (秒), 默认 86400 (1 天)
    """

    def __init__(
        self,
        mcp_url: str | None = None,
        use_mock: bool | None = None,
        cache_ttl: int = 86400,
    ) -> None:
        """初始化.

        Args:
            mcp_url: 显式 URL. None 时用 env AMAP_API_KEY 拼.
            use_mock: 强制 mock. None 时读 env AMAP_USE_MOCK.
            cache_ttl: 缓存秒数. 0 = 不缓存.

        Raises:
            ValueError: 真模式但缺 AMAP_API_KEY.
        """
        # 决定 mock 模式
        if use_mock is None:
            use_mock = os.environ.get("AMAP_USE_MOCK", "").lower() in ("true", "1", "yes")
        self.use_mock = use_mock

        # 决定 URL
        if mcp_url is not None:
            self.mcp_url = mcp_url
        else:
            key = os.environ.get("AMAP_API_KEY", "")
            if not key and not self.use_mock:
                raise ValueError(
                    "AMAP_API_KEY 未设置. 真模式必须配置 key, "
                    "或设 AMAP_USE_MOCK=true 用 mock 数据."
                )
            self.mcp_url = _AMAP_MCP_URL_TEMPLATE.format(key=key) if key else ""

        self._cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, Any]] = {}
        # mock 模式: 列出已知 tool name
        self._MOCK_TOOLS = [
            {"name": "maps_geo", "description": "地址解析为经纬度"},
            {"name": "maps_regeocode", "description": "经纬度反查地址"},
            {"name": "maps_around_search", "description": "周边 POI 搜索"},
            {"name": "maps_text_search", "description": "关键词 POI 搜索"},
            {"name": "maps_direction_walking", "description": "步行路径规划"},
            {"name": "maps_direction_bicycling", "description": "骑行路径规划"},
            {"name": "maps_direction_driving", "description": "驾车路径规划"},
            {"name": "maps_direction_transit_integrated", "description": "公交路径规划"},
            {"name": "maps_weather", "description": "天气查询"},
            {"name": "maps_ip_location", "description": "IP 定位"},
            {"name": "maps_distance", "description": "测距"},
            {"name": "maps_schema", "description": "数据表查询"},
        ]

    # =================================================================
    # 公共 API (sync wrapper)
    # =================================================================

    def geocode(self, address: str) -> dict[str, Any]:
        """地址 → 坐标. 返回 {"location": {"lng", "lat}, "formatted_address", ...}.

        失败 / 空地址 → {}.

        Note:
            高德 MCP geocode 实际返回 v2 结构, location 是 "lng,lat" 字符串.
            这里统一解析为 {"lng": float, "lat": float} dict, 方便调用方.
        """
        if not address or not address.strip():
            return {}
        cache_key = f"geocode:{address}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            if self.use_mock:
                result = self._mock_geocode(address)
            else:
                raw = self._call_mcp_tool("maps_geo", {"address": address})
                result = self._normalize_geocode(raw)
        except Exception as e:
            logger.warning("amap geocode failed: %s", e)
            return {}
        if result:
            self._cache_set(cache_key, result)
        return result

    @staticmethod
    def _normalize_geocode(raw: Any) -> dict[str, Any]:
        """把高德 MCP geocode 的多种返回格式统一为 {location: {lng, lat}, formatted_address, city}.

        高德可能返回:
        - {"results": [{"location": "lng,lat", ...}]} (v2 实际格式)
        - {"location": {"lng": ..., "lat": ...}} (规范化格式)
        - 单个 dict (mock 模式)
        """
        if not raw:
            return {}
        # 取出第一条结果 (v2 是 list)
        item: dict[str, Any]
        if isinstance(raw, list) and raw:
            item = raw[0] if isinstance(raw[0], dict) else {}
        elif isinstance(raw, dict):
            # 看是否含 results
            results = raw.get("results")
            if isinstance(results, list) and results:
                item = results[0] if isinstance(results[0], dict) else raw
            else:
                item = raw
        else:
            return {}

        # 解析 location
        loc = item.get("location")
        if isinstance(loc, str) and "," in loc:
            try:
                lng_s, lat_s = loc.split(",", 1)
                lng, lat = float(lng_s.strip()), float(lat_s.strip())
                item["location"] = {"lng": lng, "lat": lat}
            except ValueError:
                pass
        # 已经是 dict (mock 或已规范化), 保留
        return item

    def regeocode(self, lng: float, lat: float) -> dict[str, Any]:
        """坐标 → 地址. 返回 {"formatted_address", "city", ...}.

        失败 → {}.
        """
        cache_key = f"regeocode:{lng},{lat}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            if self.use_mock:
                result = self._mock_regeocode(lng, lat)
            else:
                result = self._call_mcp_tool(
                    "maps_regeocode", {"location": f"{lng},{lat}"}
                )
        except Exception as e:
            logger.warning("amap regeocode failed: %s", e)
            return {}
        if result:
            self._cache_set(cache_key, result)
        return result

    def search_around(
        self,
        lng: float,
        lat: float,
        keywords: str,
        radius: int = 3000,
    ) -> list[dict[str, Any]]:
        """周边搜索. 返回 list[POI] (每条含 name/address/location/...).

        失败 → [].
        """
        cache_key = f"search_around:{lng},{lat}:{keywords}:{radius}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            if self.use_mock:
                result = self._mock_search_around(lng, lat, keywords, radius)
            else:
                result = self._call_mcp_tool(
                    "maps_around_search",
                    {
                        "location": f"{lng},{lat}",
                        "keywords": keywords,
                        "radius": radius,
                    },
                )
                # mcp tool 可能返回 dict 包含 pois 列表或直接 list
                if isinstance(result, dict) and "pois" in result:
                    result = result["pois"]
                if not isinstance(result, list):
                    result = []
        except Exception as e:
            logger.warning("amap search_around failed: %s", e)
            return []
        self._cache_set(cache_key, result)
        return result

    def text_search(self, keywords: str, city: str | None = None) -> list[dict[str, Any]]:
        """关键词搜索. 返回 list[POI].

        失败 → [].
        """
        cache_key = f"text_search:{keywords}:{city or ''}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            if self.use_mock:
                result = self._mock_text_search(keywords, city)
            else:
                args: dict[str, Any] = {"keywords": keywords}
                if city:
                    args["city"] = city
                result = self._call_mcp_tool("maps_text_search", args)
                if isinstance(result, dict) and "pois" in result:
                    result = result["pois"]
                if not isinstance(result, list):
                    result = []
        except Exception as e:
            logger.warning("amap text_search failed: %s", e)
            return []
        self._cache_set(cache_key, result)
        return result

    def weather(self, city: str) -> dict[str, Any]:
        """天气查询. 返回 {"city", "weather", "temperature", ...}.

        失败 → {}.
        """
        if not city or not city.strip():
            return {}
        cache_key = f"weather:{city}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            if self.use_mock:
                result = self._mock_weather(city)
            else:
                result = self._call_mcp_tool("maps_weather", {"city": city})
        except Exception as e:
            logger.warning("amap weather failed: %s", e)
            return {}
        if result:
            self._cache_set(cache_key, result)
        return result

    def route(
        self,
        origin: tuple[float, float],
        dest: tuple[float, float],
        mode: str = "walking",
    ) -> dict[str, Any]:
        """路径规划. mode: walking/bicycling/driving/transit_integrated.

        返回 {"distance": 米, "duration": 秒, "path": ...}

        失败 → {}.
        """
        cache_key = f"route:{origin}->{dest}:{mode}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        tool_map = {
            "walking": "maps_direction_walking",
            "bicycling": "maps_direction_bicycling",
            "driving": "maps_direction_driving",
            "transit": "maps_direction_transit_integrated",
            "transit_integrated": "maps_direction_transit_integrated",
        }
        tool_name = tool_map.get(mode, "maps_direction_walking")
        try:
            if self.use_mock:
                result = self._mock_route(origin, dest, mode)
            else:
                result = self._call_mcp_tool(
                    tool_name,
                    {
                        "origin": f"{origin[0]},{origin[1]}",
                        "destination": f"{dest[0]},{dest[1]}",
                    },
                )
        except Exception as e:
            logger.warning("amap route failed: %s", e)
            return {}
        if result:
            self._cache_set(cache_key, result)
        return result

    def list_tools(self) -> list[dict[str, Any]]:
        """列出 server 提供的所有 tool. 失败 → []. mock 模式返回预定义列表."""
        if self.use_mock:
            return list(self._MOCK_TOOLS)
        try:
            return self._list_tools_real()
        except Exception as e:
            logger.warning("amap list_tools failed: %s", e)
            return []

    def ip_location(self, ip: str | None = None) -> dict[str, Any]:
        """IP 定位 → 城市/省份. Web 场景自动定位用.

        Args:
            ip: 客户端 IP. None 时由高德根据请求头自动获取 (需 HTTP context).

        Returns:
            {province, city, adcode}. 失败 → {}.
        """
        cache_key = f"ip_location:{ip or 'self'}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            if self.use_mock:
                result = self._mock_ip_location(ip)
            else:
                args: dict[str, Any] = {}
                if ip:
                    args["ip"] = ip
                result = self._call_mcp_tool("maps_ip_location", args)
        except Exception as e:
            logger.warning("amap ip_location failed: %s", e)
            return {}
        if result:
            self._cache_set(cache_key, result)
        return result

    # =================================================================
    # 真模式: 调 MCP SDK
    # =================================================================

    def _call_mcp_tool(self, name: str, args: dict[str, Any]) -> Any:
        """调 MCP server 上的 tool.

        每次新建 session (streamable HTTP), 返回 structuredContent 或从 text 解析.

        Raises:
            任何 mcp SDK 异常 (在公共方法里被 catch 成 fail-soft).
        """
        if not _MCP_AVAILABLE:
            raise RuntimeError("mcp SDK 未安装, 无法调真 server")

        async def _call() -> Any:
            async with streamablehttp_client(self.mcp_url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(name, args)
                    if result.isError:
                        return {}
                    # 优先 structuredContent
                    if result.structuredContent:
                        return result.structuredContent
                    # fallback: 从 text blocks 解析
                    for block in result.content:
                        if hasattr(block, "text"):
                            try:
                                return json.loads(block.text)
                            except (json.JSONDecodeError, TypeError):
                                return {"raw": block.text}
                    return {}

        return asyncio.run(_call())

    def _list_tools_real(self) -> list[dict[str, Any]]:
        """真模式: list_tools 走 mcp 协议."""
        if not _MCP_AVAILABLE:
            raise RuntimeError("mcp SDK 未安装")

        async def _list() -> list[dict[str, Any]]:
            async with streamablehttp_client(self.mcp_url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return [
                        {
                            "name": t.name,
                            "description": t.description,
                            "inputSchema": t.inputSchema,
                        }
                        for t in result.tools
                    ]

        return asyncio.run(_list())

    # =================================================================
    # Mock 数据 (CI 用)
    # =================================================================

    def _mock_geocode(self, address: str) -> dict[str, Any]:
        """mock: 基于地址 hash 生成稳定 (lng, lat) (在北京范围内)."""
        h = abs(hash(address))
        lng = 116.3 + (h % 1000) / 10000  # 116.3 ~ 116.4
        lat = 39.9 + ((h // 1000) % 1000) / 10000  # 39.9 ~ 40.0
        return {
            "location": {"lng": round(lng, 6), "lat": round(lat, 6)},
            "formatted_address": f"北京市海淀区{address}",
            "city": "北京",
        }

    def _mock_regeocode(self, lng: float, lat: float) -> dict[str, Any]:
        return {
            "formatted_address": f"北京市海淀区(模拟) {lng},{lat}",
            "city": "北京",
            "district": "海淀区",
        }

    def _mock_search_around(
        self, lng: float, lat: float, keywords: str, radius: int
    ) -> list[dict[str, Any]]:
        """mock: 按 keywords 生成 2-3 个 POI."""
        templates = {
            "川菜": [
                {"name": "老成都火锅(模拟)", "address": "模拟地址 A"},
                {"name": "麻辣诱惑(模拟)", "address": "模拟地址 B"},
                {"name": "眉州东坡(模拟)", "address": "模拟地址 C"},
            ],
            "粤菜": [
                {"name": "点都德(模拟)", "address": "模拟地址 D"},
                {"name": "陶陶居(模拟)", "address": "模拟地址 E"},
            ],
            "default": [
                {"name": f"餐厅_{keywords}_1(模拟)", "address": f"模拟地址 {keywords} 1"},
                {"name": f"餐厅_{keywords}_2(模拟)", "address": f"模拟地址 {keywords} 2"},
            ],
        }
        pois = templates.get(keywords, templates["default"])
        for i, p in enumerate(pois):
            p["location"] = {
                "lng": round(lng + (i - 1) * 0.001, 6),
                "lat": round(lat + (i - 1) * 0.001, 6),
            }
            p["distance"] = (i + 1) * 500  # 500m, 1000m, 1500m
        return pois

    def _mock_text_search(self, keywords: str, city: str | None) -> list[dict[str, Any]]:
        return self._mock_search_around(116.3, 39.9, keywords, 3000)

    def _mock_weather(self, city: str) -> dict[str, Any]:
        return {
            "city": city,
            "weather": "晴",
            "temperature": "25",
            "windDirection": "南",
            "windPower": "≤3级",
        }

    def _mock_ip_location(self, ip: str | None) -> dict[str, Any]:
        """mock IP 定位: 默认返回北京."""
        return {
            "province": "北京市",
            "city": "北京",
            "adcode": "110000",
            "rectangle": "116.011934,39.661271;116.782983,40.216496",
        }

    def _mock_route(
        self, origin: tuple[float, float], dest: tuple[float, float], mode: str
    ) -> dict[str, Any]:
        """mock: 简单欧式距离, mode 影响时间."""
        import math

        dist_m = math.hypot(dest[0] - origin[0], dest[1] - origin[1]) * 111000
        speed_mps = {
            "walking": 1.4,  # ~5 km/h
            "bicycling": 4.2,  # ~15 km/h
            "driving": 8.3,  # ~30 km/h (城市)
            "transit": 6.0,
        }.get(mode, 1.4)
        duration_s = dist_m / speed_mps
        return {
            "distance": int(dist_m),
            "duration": int(duration_s),
            "mode": mode,
        }

    # =================================================================
    # 缓存
    # =================================================================

    def _cache_get(self, key: str) -> Any | None:
        if self._cache_ttl <= 0:
            return None
        item = self._cache.get(key)
        if item is None:
            return None
        expire_at, value = item
        if time.time() > expire_at:
            self._cache.pop(key, None)
            return None
        return value

    def _cache_set(self, key: str, value: Any) -> None:
        if self._cache_ttl <= 0:
            return
        self._cache[key] = (time.time() + self._cache_ttl, value)

    # =================================================================
    # 生命周期
    # =================================================================

    def close(self) -> None:
        """关闭. mock 模式无资源, 直接 pass. 真模式无持久资源 (每次新建 session)."""
        self._cache.clear()

    def __enter__(self) -> "AmapClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


__all__ = ["AmapClient", "_AMAP_MCP_URL_TEMPLATE"]
