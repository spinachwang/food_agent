"""analyze_location: IP 定位 + 地址解析, 返回用户位置.

Phase 3.2 精简版 3 维分析器之一.

策略:
1. 优先: context.client_ip → 调高德 maps_ip_location (web 场景)
2. 降级: 从 user_msg 抽地址 → 调高德 maps_geo
3. 都失败 → confidence 0
"""
from __future__ import annotations

import logging
import re
from typing import Any

from food_agent.agents.analyzers.base import _AnalyzerToolBase
from food_agent.tools.location import get_amap_client

logger = logging.getLogger(__name__)

# 地址抽取关键词: "在 XX" / "到 XX" / "在 XX 附近" / "我家在 XX"
_CITY_LIST = [
    "北京", "上海", "广州", "深圳", "杭州", "成都", "重庆", "武汉", "西安",
    "南京", "天津", "苏州", "青岛", "大连", "沈阳", "哈尔滨", "厦门", "福州",
    "济南", "合肥", "长沙", "郑州", "昆明", "贵阳", "南宁", "海口", "石家庄",
    "太原", "兰州", "西宁", "银川", "乌鲁木齐", "拉萨",
]
_ADDRESS_RE = re.compile(
    r"(?:我(?:在|家住在|住在|到|去)|在|到|去)\s*"
    r"(" + "|".join(_CITY_LIST) + r"[一-龥]{0,15})"
)


def _extract_address(user_msg: str) -> str:
    """从 user_msg 抽地址 (城市 + 区/路/商场等)."""
    if not user_msg:
        return ""
    m = _ADDRESS_RE.search(user_msg)
    if m:
        return m.group(1)
    # 兜底: 找 "XX市/区" 等
    m2 = re.search(r"([一-鿿]{2,12}(?:市|区|县|路|街))", user_msg)
    if m2:
        return m2.group(1)
    return ""


class LocationAnalyzerTool(_AnalyzerToolBase):
    """提取用户位置 (IP 优先, 地址兜底).

    用法:
        analyze_location(user_msg="", context={"client_ip": "8.8.8.8"})
        或
        analyze_location(user_msg="我在北京海淀", context={})
    """

    name = "analyze_location"
    description = (
        "提取用户位置. 优先用 context.client_ip (高德 IP 定位, 适合 web), "
        "降级从 user_msg 抽地址 (适合 CLI/对话). "
        "返回 {city, lng, lat, source: ip|address, confidence}."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "user_msg": {
                "type": "string",
                "description": "用户消息, 可含地址",
            },
            "client_ip": {
                "type": "string",
                "description": "可选, 用户 IP (web 场景)",
            },
        },
        "required": [],
    }

    def analyze(self, user_msg: str, context: dict | None = None) -> dict[str, Any]:
        client = get_amap_client()
        if client is None:
            return {
                "confidence": 0.0,
                "error": "AmapClient 未配置. 调用 FoodAgent(amap_client=...)",
            }

        ctx = context or {}

        # 1. 优先 IP 定位
        ip = ctx.get("client_ip") or ctx.get("ip")
        if ip:
            ip_result = client.ip_location(ip if ip != "self" else None)
            if ip_result and ip_result.get("city"):
                # IP 定位不返回精确 (lng, lat), 返 city + adcode
                # 用城市中心做近似 (mock 模式由 mock 返坐标)
                return {
                    "source": "ip",
                    "city": ip_result.get("city"),
                    "province": ip_result.get("province"),
                    "adcode": ip_result.get("adcode"),
                    "lng": _extract_city_center_lng(ip_result.get("city")),
                    "lat": _extract_city_center_lat(ip_result.get("city")),
                    "ip": ip,
                    "confidence": 0.85,
                }

        # 2. 降级: 地址解析
        addr = _extract_address(user_msg or "")
        if not addr:
            return {
                "confidence": 0.0,
                "error": "无 client_ip 也无法从 user_msg 提取地址",
            }
        geo = client.geocode(addr)
        if not geo or not geo.get("location"):
            return {
                "confidence": 0.0,
                "address": addr,
                "error": f"高德 geocode 失败 (address={addr})",
            }
        loc = geo["location"]
        return {
            "source": "address",
            "anchor": geo.get("formatted_address", addr),
            "city": geo.get("city"),
            "lng": loc.get("lng"),
            "lat": loc.get("lat"),
            "address": addr,
            "confidence": 0.8,
        }


# 城市中心近似坐标 (用于 IP 定位无精确坐标时). 简化版, 不依赖外部数据.
_CITY_CENTERS = {
    "北京": (116.4074, 39.9042),
    "上海": (121.4737, 31.2304),
    "广州": (113.2644, 23.1291),
    "深圳": (114.0579, 22.5431),
    "杭州": (120.1551, 30.2741),
    "成都": (104.0668, 30.5728),
    "重庆": (106.5516, 29.5630),
    "武汉": (114.3055, 30.5928),
    "西安": (108.9398, 34.3416),
    "南京": (118.7969, 32.0603),
    "天津": (117.1901, 39.1255),
}


def _extract_city_center_lng(city: str | None) -> float | None:
    if not city:
        return None
    coords = _CITY_CENTERS.get(city)
    return coords[0] if coords else None


def _extract_city_center_lat(city: str | None) -> float | None:
    if not city:
        return None
    coords = _CITY_CENTERS.get(city)
    return coords[1] if coords else None


__all__ = ["LocationAnalyzerTool"]