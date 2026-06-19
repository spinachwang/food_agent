"""高德地图工具集 (qwen-agent BaseTool 包装).

Phase 3.2.

5 个 tool:
- GeocodeTool: 地址 → 坐标
- RegeocodeTool: 坐标 → 地址
- SearchAroundTool: 周边 POI 搜索
- WeatherTool: 天气查询
- RouteTool: 路径规划 (walking/bicycling/driving/transit)

共享一个 AmapClient (类级单例), 通过 set_amap_client() / get_amap_client() 管理.

每个 tool 的 .call(params) 接收 JSON 字符串, 返回 JSON 字符串 (qwen-agent 约定).
失败 / 解析错误 → error JSON (不抛, fail-soft).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from qwen_agent.tools.base import BaseTool

from food_agent.mcp.amap_client import AmapClient

logger = logging.getLogger(__name__)

# 模块级单例 AmapClient (FoodAgent 启动时 set 一次)
_amap_client: AmapClient | None = None


def set_amap_client(client: AmapClient | None) -> None:
    """设置 (或清除) 全局 AmapClient. FoodAgent.__init__ 调一次."""
    global _amap_client
    _amap_client = client


def get_amap_client() -> AmapClient | None:
    """拿当前 AmapClient. None 表示未配置."""
    return _amap_client


# =============================================================================
# 公共基类
# =============================================================================

class _AmapToolBase(BaseTool):
    """所有 Amap tool 的共同行为: 拿 client → 解析 params → 调方法 → 返 JSON."""

    def _call_impl(self, args: dict[str, Any]) -> Any:
        """子类实现具体调哪个 client 方法. 失败/异常 → 由 .call 统一处理."""
        raise NotImplementedError

    def call(self, params: str, **kwargs: Any) -> str:
        """主入口. 接收 JSON 字符串, 返回 JSON 字符串.

        Args:
            params: JSON 字符串, 形如 '{"address": "北京"}'
            **kwargs: qwen-agent 透传 (ignore)

        Returns:
            JSON 字符串. 成功 → 结果. 失败 → {"error": "..."}.
        """
        client = get_amap_client()
        if client is None:
            return json.dumps(
                {"error": "AmapClient 未初始化. 调用 set_amap_client() 或 FoodAgent(amap_client=...)"},
                ensure_ascii=False,
            )

        # 解析 params
        if not params or not params.strip():
            return json.dumps({"error": "params 为空"}, ensure_ascii=False)
        try:
            args = json.loads(params)
        except json.JSONDecodeError as e:
            return json.dumps(
                {"error": f"params 不是合法 JSON: {e}"},
                ensure_ascii=False,
            )
        if not isinstance(args, dict):
            return json.dumps(
                {"error": f"params 必须是 JSON object, 收到 {type(args).__name__}"},
                ensure_ascii=False,
            )

        # 调实现
        try:
            result = self._call_impl(args)
        except Exception as e:
            logger.warning("%s call failed: %s", self.name, e)
            return json.dumps(
                {"error": f"{type(e).__name__}: {e}"},
                ensure_ascii=False,
            )

        if result is None or result == {} or result == []:
            return json.dumps(
                {"error": f"{self.name} 返回空结果"}, ensure_ascii=False,
            )

        return json.dumps(result, ensure_ascii=False)


# =============================================================================
# 5 个具体 tool
# =============================================================================

class GeocodeTool(_AmapToolBase):
    """地址解析为经纬度坐标. 例: geocode('北京海淀中关村') → {lng, lat}."""

    name = "geocode"
    description = (
        "把用户描述的地址解析为经纬度坐标 (高德地图). "
        "用法: 输入 address 参数 (如 '北京海淀中关村'), "
        "返回 {location: {lng, lat}, formatted_address, city}."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "address": {
                "type": "string",
                "description": "用户描述的地址, 如 '北京海淀中关村' / '上海市浦东新区'",
            },
        },
        "required": ["address"],
    }

    def _call_impl(self, args: dict[str, Any]) -> Any:
        address = args.get("address", "")
        return get_amap_client().geocode(address)  # type: ignore[union-attr]


class RegeocodeTool(_AmapToolBase):
    """经纬度反查地址. 例: regeocode('116.3,39.9') → formatted_address."""

    name = "regeocode"
    description = (
        "把经纬度反查为地址 (高德地图). "
        "用法: 输入 location='lng,lat' (字符串), "
        "返回 {formatted_address, city, district}."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "经纬度字符串, 形如 '116.307,39.985'",
            },
        },
        "required": ["location"],
    }

    def _call_impl(self, args: dict[str, Any]) -> Any:
        loc_str = args.get("location", "")
        if not loc_str or "," not in loc_str:
            return {}
        try:
            lng_s, lat_s = loc_str.split(",", 1)
            lng, lat = float(lng_s.strip()), float(lat_s.strip())
        except ValueError:
            return {}
        return get_amap_client().regeocode(lng, lat)  # type: ignore[union-attr]


class SearchAroundTool(_AmapToolBase):
    """周边 POI 搜索. 例: search_around(lng=116.3, lat=39.9, keywords='川菜') → [POI]."""

    name = "search_around"
    description = (
        "在指定经纬度周边搜索 POI (餐厅/景点等). "
        "用法: 输入 lng, lat, keywords (如 '川菜' / '咖啡' / '火锅'), "
        "可选 radius (米, 默认 3000). "
        "返回 list[POI] (每条含 name, address, location, distance)."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "lng": {"type": "number", "description": "经度"},
            "lat": {"type": "number", "description": "纬度"},
            "keywords": {"type": "string", "description": "搜索关键词, 如 '川菜' / '咖啡'"},
            "radius": {
                "type": "integer",
                "description": "搜索半径 (米), 默认 3000",
            },
        },
        "required": ["lng", "lat", "keywords"],
    }

    def _call_impl(self, args: dict[str, Any]) -> Any:
        lng = float(args.get("lng", 0))
        lat = float(args.get("lat", 0))
        keywords = args.get("keywords", "")
        radius = int(args.get("radius", 3000))
        return get_amap_client().search_around(  # type: ignore[union-attr]
            lng, lat, keywords, radius=radius
        )


class WeatherTool(_AmapToolBase):
    """天气查询. 例: weather('北京') → {city, weather, temperature}."""

    name = "weather"
    description = (
        "查询某城市的天气 (高德地图). "
        "用法: 输入 city (如 '北京' / '上海'). "
        "返回 {city, weather, temperature, windDirection, windPower}."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名, 如 '北京' / '上海' / '深圳市'",
            },
        },
        "required": ["city"],
    }

    def _call_impl(self, args: dict[str, Any]) -> Any:
        return get_amap_client().weather(args.get("city", ""))  # type: ignore[union-attr]


class RouteTool(_AmapToolBase):
    """路径规划. mode: walking/bicycling/driving/transit."""

    name = "route"
    description = (
        "规划两点之间的路径 (高德地图). "
        "用法: 输入 origin='lng,lat', destination='lng,lat', "
        "可选 mode (walking/bicycling/driving/transit, 默认 walking). "
        "返回 {distance: 米, duration: 秒, mode}."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "origin": {"type": "string", "description": "起点 'lng,lat'"},
            "destination": {"type": "string", "description": "终点 'lng,lat'"},
            "mode": {
                "type": "string",
                "description": "出行方式: walking / bicycling / driving / transit, 默认 walking",
                "enum": ["walking", "bicycling", "driving", "transit"],
            },
        },
        "required": ["origin", "destination"],
    }

    def _call_impl(self, args: dict[str, Any]) -> Any:
        origin_s = args.get("origin", "")
        dest_s = args.get("destination", "")
        mode = args.get("mode", "walking")
        if not origin_s or not dest_s or "," not in origin_s or "," not in dest_s:
            return {}

        def _parse(s: str) -> tuple[float, float]:
            a, b = s.split(",", 1)
            return float(a.strip()), float(b.strip())

        origin = _parse(origin_s)
        dest = _parse(dest_s)
        return get_amap_client().route(origin, dest, mode=mode)  # type: ignore[union-attr]


__all__ = [
    "GeocodeTool",
    "RegeocodeTool",
    "SearchAroundTool",
    "WeatherTool",
    "RouteTool",
    "set_amap_client",
    "get_amap_client",
]
