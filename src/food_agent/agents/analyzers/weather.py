"""analyze_weather: 查城市天气并推断适合吃什么.

Phase 3.2 精简版 3 维分析器之一.

调用: analyze_weather(user_msg, context={city?})
返回: {city, temperature, weather, suggestion, confidence}
"""
from __future__ import annotations

import logging
import re
from typing import Any

from food_agent.agents.analyzers.base import _AnalyzerToolBase
from food_agent.tools.location import get_amap_client

logger = logging.getLogger(__name__)

# 简易城市抽取: 优先 context.city, 降级到 regex
_CITY_LIST = [
    "北京", "上海", "广州", "深圳", "杭州", "成都", "重庆", "武汉", "西安",
    "南京", "天津", "苏州", "青岛", "大连", "沈阳", "哈尔滨", "厦门", "福州",
    "济南", "合肥", "长沙", "郑州", "昆明", "贵阳", "南宁", "海口", "石家庄",
    "太原", "兰州", "西宁", "银川", "乌鲁木齐", "拉萨", "香港", "澳门", "台北",
]
_CITY_RE = re.compile(
    r"(?:在|到|去|天气|气温|多少度|怎么样|如何|查)?"
    r"(" + "|".join(_CITY_LIST) + r")"
)


def _extract_city(user_msg: str, context: dict | None) -> str:
    """从 user_msg 或 context 抽城市."""
    if context and context.get("city"):
        return str(context["city"]).strip()
    m = _CITY_RE.search(user_msg or "")
    if m:
        return m.group(1)
    return ""


def _derive_suggestion(temp: int | None, weather: str | None) -> str:
    """根据温度 + 天气推断饮食建议 (规则引擎)."""
    if temp is None:
        return ""
    weather_lc = (weather or "").lower()
    # 极端天气
    if "雨" in weather_lc or "雪" in weather_lc:
        return "下雨/雪, 推荐热汤/火锅/汤面"
    if temp >= 32:
        return "天气炎热, 推荐清淡/凉菜/冰品/汤面"
    if temp >= 26:
        return "天气较热, 推荐清淡/凉拌/汤粥"
    if temp <= 5:
        return "天气寒冷, 推荐热汤/火锅/炖菜"
    if temp <= 15:
        return "天气偏凉, 推荐热菜/汤面"
    return "天气适中, 无特殊推荐"


class WeatherAnalyzerTool(_AnalyzerToolBase):
    """查城市天气并给出饮食建议.

    用法:
        analyze_weather(user_msg="今天北京热, 吃啥", context={})
        或
        analyze_weather(user_msg="", context={"city": "北京"})
    """

    name = "analyze_weather"
    description = (
        "查某城市的天气, 并根据温度/天气推导饮食建议. "
        "例: '今天北京热, 吃啥' → 查北京天气 + 推清淡. "
        "用法: user_msg (可含城市名) 或 context.city (二选一)."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "user_msg": {
                "type": "string",
                "description": "用户消息, 可含城市名",
            },
            "city": {
                "type": "string",
                "description": "可选, 显式城市 (如 '北京')",
            },
        },
        "required": [],
    }

    def analyze(self, user_msg: str, context: dict | None = None) -> dict[str, Any]:
        city = _extract_city(user_msg, context)
        if not city:
            return {
                "confidence": 0.0,
                "error": "无法从消息或 context 提取城市",
            }

        client = get_amap_client()
        if client is None:
            return {
                "confidence": 0.0,
                "error": "AmapClient 未配置. 调用 FoodAgent(amap_client=...)",
            }

        weather = client.weather(city)
        if not weather:
            return {
                "confidence": 0.0,
                "city": city,
                "error": f"高德 weather API 返回空 (city={city})",
            }

        # 解析温度 (高德可能返回 "25" 或 "25℃" 等)
        temp_raw = weather.get("temperature", "")
        try:
            temp = int(re.findall(r"-?\d+", str(temp_raw))[0])
        except (ValueError, IndexError):
            temp = None

        suggestion = _derive_suggestion(temp, weather.get("weather", ""))
        return {
            "city": city,
            "temperature": temp,
            "weather": weather.get("weather", ""),
            "windDirection": weather.get("windDirection", ""),
            "windPower": weather.get("windPower", ""),
            "suggestion": suggestion,
            "confidence": 0.85 if temp is not None else 0.6,
        }


__all__ = ["WeatherAnalyzerTool"]