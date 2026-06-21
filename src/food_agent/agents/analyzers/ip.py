"""detect_location: 用户消息没明确地址时, 自动用 IP 定位.

Phase 3.5: 新增独立 analyzer tool. 解决 master 之前无法在无地址时定位的问题.

设计:
- 内部调 AmapClient.ip_location(None) — ip=None 让高德从 HTTP context 自动推断
  (web 场景: 高德拿到访问者的真实 IP; CLI 场景: 高德拿到本机/出口 IP, 可能不准)
- 不传任何参数 (LLM 调时不需要知道 IP), 让 tool 自己解决
- IP 定位没精确 (lng, lat), 高德只返 city + adcode, 用城市中心近似坐标
- mock 模式: _mock_ip_location(None) 默认返北京

跟 analyze_location 的区别:
- analyze_location: 用户消息含明确地址 → 调高德 geocode 拿精确坐标
- detect_location:  无地址 → 调高德 IP 定位拿城市中心坐标

LLM 调用策略 (master prompt 里说明):
- 用户消息含 "在 XX/到 XX" → analyze_location
- 用户消息无地址 → detect_location
"""
from __future__ import annotations

import logging
from typing import Any

from food_agent.agents.analyzers.base import _AnalyzerToolBase
from food_agent.tools.location import get_amap_client

logger = logging.getLogger(__name__)

# 城市中心近似坐标 (用于 IP 定位无精确坐标时). 简化版, 不依赖外部数据.
# 跟 analyze_location 重复, 但模块隔离更清晰 (避免 analyzer 间耦合).
_CITY_CENTERS: dict[str, tuple[float, float]] = {
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


def _city_center(city: str | None) -> tuple[float | None, float | None]:
    """查城市中心坐标, 返 (lng, lat). 找不到 → (None, None)."""
    if not city:
        return None, None
    coords = _CITY_CENTERS.get(city)
    if not coords:
        return None, None
    return coords[0], coords[1]


class IPLocatorTool(_AnalyzerToolBase):
    """用户消息没明确地址时, 调此 tool 拿 IP 定位.

    用法:
        detect_location()  # 不需要参数

    适用:
        用户说"今天想吃川菜" (没地址) → master 调此工具, 拿城市中心坐标
        用户说"附近 2km 的川菜" (有地址) → master 调 analyze_location 拿精确坐标

    Returns:
        {source: 'ip', city, province, adcode, lng, lat, confidence}
    """

    name = "detect_location"
    description = (
        "用户消息没明确地址时, 调此 tool 拿定位. "
        "web 场景: 高德根据访问者 HTTP IP 自动定位. "
        "CLI 场景: 用本机/出口 IP 定位 (可能不准, fallback 到 mock 北京). "
        "返回 {source: 'ip', city, province, lng, lat, confidence}. "
        "lng/lat 是城市中心近似值, 精度不如 analyze_location 的地址解析."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def analyze(self, user_msg: str = "", context: dict | None = None) -> dict[str, Any]:
        client = get_amap_client()
        if client is None:
            return {
                "confidence": 0.0,
                "error": "AmapClient 未配置. 调用 FoodAgent(amap_client=...)",
            }

        # ip=None 让高德从 HTTP context 自动拿 (web 真模式)
        # 或直接用 mock (CLI mock 模式)
        try:
            ip_result = client.ip_location(None)
        except Exception as e:
            logger.warning("detect_location: ip_location failed: %s", e)
            return {
                "confidence": 0.0,
                "error": f"高德 IP 定位异常: {type(e).__name__}: {e}",
            }

        if not ip_result or not ip_result.get("city"):
            return {
                "confidence": 0.0,
                "error": "高德 IP 定位返空 (CLI 场景或网络问题)",
            }

        city = ip_result["city"]
        lng, lat = _city_center(city)
        return {
            "source": "ip",
            "city": city,
            "province": ip_result.get("province"),
            "adcode": ip_result.get("adcode"),
            "lng": lng,
            "lat": lat,
            "confidence": 0.7 if lng is not None else 0.5,
        }


__all__ = ["IPLocatorTool"]


def _city_center_lng(city: str | None) -> float | None:
    """兼容 analyze_location 的 helper, 保留单值版本."""
    lng, _ = _city_center(city)
    return lng


def _city_center_lat(city: str | None) -> float | None:
    """兼容 analyze_location 的 helper."""
    _, lat = _city_center(city)
    return lat