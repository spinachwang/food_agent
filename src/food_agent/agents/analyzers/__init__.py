"""analyzers: 3 维分析器 (Phase 3.2 精简版).

只实现 3 个真正需要外部数据/安全保障的分析器:
- analyze_weather: 查天气 (调高德 maps_weather)
- analyze_location: IP 定位 + 地址解析 (调高德 maps_ip_location / maps_geo)
- analyze_dietary: 硬约束过滤 (过敏/宗教/医学, 安全关键) + LLM 抽取 (Phase B-2)

其他 5 维 (price/taste/mood/occasion/time) 让 master LLM 在 system prompt 里
直接分析, 不做 tool (避免冗余).
"""
from food_agent.agents.analyzers.weather import WeatherAnalyzerTool
from food_agent.agents.analyzers.location import LocationAnalyzerTool
from food_agent.agents.analyzers.dietary import DietaryAnalyzerTool


def list_analyzer_tools(long_term=None, llm=None) -> list:
    """返回 3 个 analyzer tool 实例.

    Args:
        long_term: 注入给 dietary 用于已知偏好召回.
        llm: 注入给 dietary 用于 LLM 抽取 (Phase B-2). None 时 dietary 走 keyword 抽取.
    """
    return [
        WeatherAnalyzerTool(),
        LocationAnalyzerTool(),
        DietaryAnalyzerTool(long_term=long_term, llm=llm),
    ]


__all__ = [
    "WeatherAnalyzerTool",
    "LocationAnalyzerTool",
    "DietaryAnalyzerTool",
    "list_analyzer_tools",
]