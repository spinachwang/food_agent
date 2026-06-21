"""analyzers: 4 维分析器 (Phase 3.5).

实现 4 个 analyzer tool:
- analyze_weather: 查天气 (调高德 maps_weather)
- analyze_location: IP 定位 + 地址解析 (调高德 maps_ip_location / maps_geo),
  含周边 POI 自动搜索 (user_msg 含 附近 + 食物关键词)
- analyze_dietary: 硬约束过滤 (过敏/宗教/医学, 安全关键) + LLM 抽取 (Phase B-2)
- detect_location: 用户消息无地址时, 自动用 IP 定位 (Phase 3.5 新增,
  web 场景从 HTTP IP, CLI 场景 mock 北京)

价格/口味/情绪/场合/时间 5 个维度让 master LLM 在 system prompt 里直接分析.
"""
from food_agent.agents.analyzers.weather import WeatherAnalyzerTool
from food_agent.agents.analyzers.location import LocationAnalyzerTool
from food_agent.agents.analyzers.dietary import DietaryAnalyzerTool
from food_agent.agents.analyzers.ip import IPLocatorTool


def list_analyzer_tools(long_term=None, llm=None) -> list:
    """返回 4 个 analyzer tool 实例.

    Args:
        long_term: 注入给 dietary 用于已知偏好召回.
        llm: 注入给 dietary 用于 LLM 抽取 (Phase B-2). None 时 dietary 走 keyword 抽取.
    """
    return [
        WeatherAnalyzerTool(),
        LocationAnalyzerTool(),
        DietaryAnalyzerTool(long_term=long_term, llm=llm),
        IPLocatorTool(),  # Phase 3.5: 用户消息无地址时主动调
    ]


__all__ = [
    "WeatherAnalyzerTool",
    "LocationAnalyzerTool",
    "DietaryAnalyzerTool",
    "IPLocatorTool",
    "list_analyzer_tools",
]
