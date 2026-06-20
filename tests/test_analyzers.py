"""测试 agents/analyzers/ 3 个 analyzer tool (TDD).

Phase 3.2: weather / location / dietary.
"""
from __future__ import annotations

import json
import os

import pytest


# 必须在 import analyzers 之前设环境变量, 因为 AmapClient.__init__ 会读 AMAP_API_KEY
@pytest.fixture(autouse=True)
def mock_amap_env(monkeypatch):
    monkeypatch.setenv("AMAP_API_KEY", "test-fake-key")
    monkeypatch.setenv("AMAP_USE_MOCK", "true")
    # 每次测试前清空 AmapClient singleton
    from food_agent.tools.location import set_amap_client
    from food_agent.mcp.amap_client import AmapClient

    set_amap_client(AmapClient())
    yield
    set_amap_client(None)


# =============================================================================
# WeatherAnalyzerTool
# =============================================================================

def test_weather_analyzer_basic() -> None:
    """天气分析: 用户消息含城市."""
    from food_agent.agents.analyzers.weather import WeatherAnalyzerTool

    tool = WeatherAnalyzerTool()
    result = tool.call(json.dumps({"user_msg": "今天北京热, 吃啥"}))
    data = json.loads(result)
    assert "city" in data
    assert data["city"] == "北京"
    assert "weather" in data or "temperature" in data
    assert "suggestion" in data
    assert "confidence" in data
    assert data["confidence"] > 0.5


def test_weather_analyzer_explicit_city_in_context() -> None:
    """context.city 优先于 user_msg 解析."""
    from food_agent.agents.analyzers.weather import WeatherAnalyzerTool

    tool = WeatherAnalyzerTool()
    result = tool.call(json.dumps({"user_msg": "天气如何", "city": "上海"}))
    data = json.loads(result)
    assert data["city"] == "上海"


def test_weather_analyzer_no_city_returns_error() -> None:
    """无城市 → confidence 0 + error."""
    from food_agent.agents.analyzers.weather import WeatherAnalyzerTool

    tool = WeatherAnalyzerTool()
    result = tool.call(json.dumps({"user_msg": "今天吃啥"}))
    data = json.loads(result)
    assert data["confidence"] == 0.0
    assert "error" in data


def test_weather_analyzer_schema() -> None:
    """schema 正确 (name / description / parameters)."""
    from food_agent.agents.analyzers.weather import WeatherAnalyzerTool

    assert WeatherAnalyzerTool.name == "analyze_weather"
    assert len(WeatherAnalyzerTool.description) > 10
    assert "user_msg" in WeatherAnalyzerTool.parameters["properties"]


def test_weather_suggestion_hot() -> None:
    """高温天气 → 建议清淡/凉菜."""
    from food_agent.agents.analyzers.weather import _derive_suggestion

    assert "清淡" in _derive_suggestion(35, "晴")
    assert "凉" in _derive_suggestion(30, "晴") or "清淡" in _derive_suggestion(30, "晴")


def test_weather_suggestion_cold() -> None:
    """低温 → 建议热汤/火锅."""
    from food_agent.agents.analyzers.weather import _derive_suggestion

    assert "热汤" in _derive_suggestion(0, "阴") or "火锅" in _derive_suggestion(0, "阴")


def test_weather_suggestion_rainy() -> None:
    """下雨 → 建议热汤."""
    from food_agent.agents.analyzers.weather import _derive_suggestion

    assert "热汤" in _derive_suggestion(20, "小雨") or "汤面" in _derive_suggestion(20, "小雨")


# =============================================================================
# LocationAnalyzerTool
# =============================================================================

def test_location_analyzer_from_ip() -> None:
    """context.client_ip 优先, 走 IP 定位."""
    from food_agent.agents.analyzers.location import LocationAnalyzerTool

    tool = LocationAnalyzerTool()
    result = tool.call(json.dumps({"user_msg": "", "client_ip": "8.8.8.8"}))
    data = json.loads(result)
    assert data["source"] == "ip"
    assert "city" in data
    assert data["confidence"] > 0.5


def test_location_analyzer_from_address() -> None:
    """user_msg 含地址 → 降级到 geocode."""
    from food_agent.agents.analyzers.location import LocationAnalyzerTool

    tool = LocationAnalyzerTool()
    result = tool.call(json.dumps({"user_msg": "我在北京海淀中关村"}))
    data = json.loads(result)
    assert data["source"] == "address"
    assert "city" in data
    assert data.get("lng") is not None
    assert data.get("lat") is not None
    assert data["confidence"] > 0.5


def test_location_analyzer_no_ip_no_address() -> None:
    """既无 IP 也无地址 → confidence 0."""
    from food_agent.agents.analyzers.location import LocationAnalyzerTool

    tool = LocationAnalyzerTool()
    result = tool.call(json.dumps({"user_msg": "随便吃点啥"}))
    data = json.loads(result)
    assert data["confidence"] == 0.0


def test_location_analyzer_ip_priority_over_address() -> None:
    """同时有 ip + address, IP 优先."""
    from food_agent.agents.analyzers.location import LocationAnalyzerTool

    tool = LocationAnalyzerTool()
    result = tool.call(json.dumps({
        "user_msg": "我在上海",
        "client_ip": "8.8.8.8",  # mock 返北京
    }))
    data = json.loads(result)
    # IP 优先 → city=北京 (mock), 忽略 user_msg 的 "上海"
    assert data["source"] == "ip"
    assert data["city"] == "北京"


def test_location_analyzer_schema() -> None:
    from food_agent.agents.analyzers.location import LocationAnalyzerTool

    assert LocationAnalyzerTool.name == "analyze_location"
    assert "client_ip" in LocationAnalyzerTool.parameters["properties"]


# =============================================================================
# DietaryAnalyzerTool
# =============================================================================

def test_dietary_allergy_detection() -> None:
    """过敏关键词 → 硬约束."""
    from food_agent.agents.analyzers.dietary import DietaryAnalyzerTool

    tool = DietaryAnalyzerTool()
    result = tool.call(json.dumps({"user_msg": "我对花生过敏"}))
    data = json.loads(result)
    assert data["has_restrictions"] is True
    assert len(data["hard_constraints"]) >= 1
    allergy = data["hard_constraints"][0]
    assert allergy["value"] == "花生"
    assert allergy["must_exclude"] is True


def test_dietary_religion_detection() -> None:
    """宗教关键词 → 硬约束."""
    from food_agent.agents.analyzers.dietary import DietaryAnalyzerTool

    tool = DietaryAnalyzerTool()
    result = tool.call(json.dumps({"user_msg": "我吃清真"}))
    data = json.loads(result)
    assert data["has_restrictions"] is True
    assert any(h["value"] == "halal" for h in data["hard_constraints"])


def test_dietary_soft_preference() -> None:
    """软偏好 (不爱吃香菜) → soft_preferences."""
    from food_agent.agents.analyzers.dietary import DietaryAnalyzerTool

    tool = DietaryAnalyzerTool()
    result = tool.call(json.dumps({"user_msg": "我不爱吃香菜"}))
    data = json.loads(result)
    assert data["has_restrictions"] is True
    assert len(data["soft_preferences"]) >= 1
    assert any("香菜" in s["value"] for s in data["soft_preferences"])


def test_dietary_mixed_hard_and_soft() -> None:
    """同时含硬 + 软."""
    from food_agent.agents.analyzers.dietary import DietaryAnalyzerTool

    tool = DietaryAnalyzerTool()
    result = tool.call(json.dumps({
        "user_msg": "我海鲜过敏, 不爱吃香菜",
    }))
    data = json.loads(result)
    assert data["has_restrictions"] is True
    assert len(data["hard_constraints"]) >= 1
    assert len(data["soft_preferences"]) >= 1


def test_dietary_no_restrictions() -> None:
    """无限制 → has_restrictions false."""
    from food_agent.agents.analyzers.dietary import DietaryAnalyzerTool

    tool = DietaryAnalyzerTool()
    result = tool.call(json.dumps({"user_msg": "今天想吃川菜"}))
    data = json.loads(result)
    assert data["has_restrictions"] is False
    assert data["confidence"] == 0.5


# =============================================================================
# Phase B: 甜 / 糖 关键词 (auto-save 链路打通前置)
# =============================================================================

def test_dietary_sweet_soft_preference() -> None:
    """'不喜欢甜的' → soft_preferences (avoid_甜)."""
    from food_agent.agents.analyzers.dietary import DietaryAnalyzerTool

    tool = DietaryAnalyzerTool()
    result = tool.call(json.dumps({"user_msg": "我不喜欢甜的"}))
    data = json.loads(result)
    assert data["has_restrictions"] is True
    assert any(s["value"] == "甜" for s in data["soft_preferences"])


def test_dietary_sugar_allergy() -> None:
    """'不能吃糖' (糖尿病场景) → hard_constraints."""
    from food_agent.agents.analyzers.dietary import DietaryAnalyzerTool

    tool = DietaryAnalyzerTool()
    result = tool.call(json.dumps({"user_msg": "我有糖尿病不能吃糖"}))
    data = json.loads(result)
    assert data["has_restrictions"] is True
    allergy = [h for h in data["hard_constraints"] if h.get("type") == "allergy"]
    assert any(h["value"] == "糖" for h in allergy)


def test_dietary_dessert_keywords() -> None:
    """甜食系关键词 (蛋糕 / 奶茶 / 冰淇淋) → soft_preferences."""
    from food_agent.agents.analyzers.dietary import DietaryAnalyzerTool

    tool = DietaryAnalyzerTool()
    for kw in ("蛋糕", "奶茶", "冰淇淋"):
        result = tool.call(json.dumps({"user_msg": f"我不爱吃{kw}"}))
        data = json.loads(result)
        assert data["has_restrictions"] is True
        assert any(s["value"] == kw for s in data["soft_preferences"]), \
            f"expected soft pref for {kw}, got {data['soft_preferences']}"


def test_dietary_integrates_long_term(tmp_path) -> None:
    """context.user_id + long_term 注入 → 已知偏好自动加载."""
    from food_agent.agents.analyzers.dietary import DietaryAnalyzerTool
    from food_agent.memory.long_term import LongTermMemory

    db = tmp_path / "diet.db"
    with LongTermMemory(db) as ltm:
        ltm.save_preference("alice", "allergy_peanut", "花生", 0.9)
        ltm.save_preference("alice", "avoid_cilantro", "香菜", 0.7)

        tool = DietaryAnalyzerTool(long_term=ltm)
        result = tool.call(json.dumps({
            "user_msg": "随便",  # 没显式说限制
            "user_id": "alice",
        }))
        data = json.loads(result)
        # 长期记忆的过敏/avoid 应被识别
        assert data["has_restrictions"] is True
        keys = [h.get("key", "") for h in data["hard_constraints"]] + \
               [s.get("key", "") for s in data["soft_preferences"]]
        assert "allergy_peanut" in keys
        assert "avoid_cilantro" in keys


def test_dietary_schema() -> None:
    from food_agent.agents.analyzers.dietary import DietaryAnalyzerTool

    assert DietaryAnalyzerTool.name == "analyze_dietary"
    assert "user_msg" in DietaryAnalyzerTool.parameters["properties"]
    assert "user_id" in DietaryAnalyzerTool.parameters["properties"]


# =============================================================================
# Phase B-2: LLM 抽取 (替代 keyword 抽取)
# =============================================================================

class FakeLLM:
    """LLM 抽取的 mock — 返回构造好的 JSON 字符串."""

    def __init__(self, canned_response: str) -> None:
        self.canned_response = canned_response
        self.call_count = 0
        self.last_prompt: str = ""

    def chat(self, messages, functions=None, stream=True, **kwargs):
        self.call_count += 1
        # 拿 user message 当 prompt (qwen-agent Message 对象)
        for m in messages:
            content = getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else None)
            if content:
                self.last_prompt = content
                break

        from qwen_agent.llm.schema import Message as QMessage
        def _gen():
            yield [QMessage(role="assistant", content=self.canned_response)]
        return _gen()


def test_dietary_llm_extract_likes_spicy() -> None:
    """LLM 抽取: '我喜欢吃辣' → like_辣 (keyword 抽不到, LLM 能)."""
    from food_agent.agents.analyzers.dietary import DietaryAnalyzerTool

    fake = FakeLLM(
        '{"hard_constraints": [], "soft_preferences": [], '
        '"like_preferences": [{"type": "like", "value": "辣", '
        '"should_prefer": true, "source": "msg"}], '
        '"has_restrictions": false, "confidence": 0.85}'
    )
    tool = DietaryAnalyzerTool(llm=fake)
    result = tool.analyze("我喜欢吃辣, 干辣尤其喜欢")

    assert any(lp["value"] == "辣" for lp in result["like_preferences"])
    assert result["has_restrictions"] is False  # 只有 like, 不算 restriction
    assert fake.call_count == 1


def test_dietary_llm_extract_mixed() -> None:
    """LLM 抽: 三类偏好混合 (allergy + avoid + like) 一次抽齐."""
    from food_agent.agents.analyzers.dietary import DietaryAnalyzerTool

    fake = FakeLLM(
        '{"hard_constraints": [{"type": "allergy", "value": "花生", '
        '"must_exclude": true, "source": "msg"}], '
        '"soft_preferences": [{"type": "avoid", "value": "香菜", '
        '"should_avoid": true, "source": "msg"}], '
        '"like_preferences": [{"type": "like", "value": "辣", '
        '"should_prefer": true, "source": "msg"}], '
        '"has_restrictions": true, "confidence": 0.95}'
    )
    tool = DietaryAnalyzerTool(llm=fake)
    result = tool.analyze("对花生过敏, 不爱吃香菜, 喜欢辣的")

    assert any(h["value"] == "花生" for h in result["hard_constraints"])
    assert any(s["value"] == "香菜" for s in result["soft_preferences"])
    assert any(l["value"] == "辣" for l in result["like_preferences"])
    assert result["has_restrictions"] is True


def test_dietary_llm_extract_handles_implicit_preference() -> None:
    """LLM 抽: '最近在减脂' 这种隐含偏好也能识别."""
    from food_agent.agents.analyzers.dietary import DietaryAnalyzerTool

    fake = FakeLLM(
        '{"hard_constraints": [], '
        '"soft_preferences": [{"type": "avoid", "value": "油炸", '
        '"should_avoid": true, "source": "msg"}, '
        '{"type": "avoid", "value": "甜食", "should_avoid": true, "source": "msg"}], '
        '"like_preferences": [], '
        '"has_restrictions": true, "confidence": 0.8}'
    )
    tool = DietaryAnalyzerTool(llm=fake)
    result = tool.analyze("最近在减脂, 油炸的和甜食都不想吃")

    soft_vals = [s["value"] for s in result["soft_preferences"]]
    assert "油炸" in soft_vals or "甜食" in soft_vals


def test_dietary_llm_extract_falls_back_on_invalid_json() -> None:
    """LLM 返回非 JSON → 降级到 keyword 抽取 (fail-soft)."""
    from food_agent.agents.analyzers.dietary import DietaryAnalyzerTool

    fake = FakeLLM("invalid json {{{")
    tool = DietaryAnalyzerTool(llm=fake)
    # 不会抛, 应降级到 keyword 抽
    result = tool.analyze("我对花生过敏")
    # keyword 抽能识别花生 (allergy)
    assert any(h["value"] == "花生" for h in result["hard_constraints"])


def test_dietary_no_llm_uses_keyword() -> None:
    """无 llm 参数时, 仍走 keyword 抽取 (向后兼容)."""
    from food_agent.agents.analyzers.dietary import DietaryAnalyzerTool

    tool = DietaryAnalyzerTool()  # 无 llm
    result = tool.analyze("对花生过敏")
    assert any(h["value"] == "花生" for h in result["hard_constraints"])
    assert result.get("like_preferences", []) == []  # keyword 抽不支持 like


def test_dietary_llm_extract_prompt_contains_user_msg() -> None:
    """LLM 抽的 prompt 应包含用户消息原文 (让 LLM 看得到原话)."""
    from food_agent.agents.analyzers.dietary import DietaryAnalyzerTool

    fake = FakeLLM('{"hard_constraints": [], "soft_preferences": [], '
                   '"like_preferences": [], "has_restrictions": false, '
                   '"confidence": 0.5}')
    tool = DietaryAnalyzerTool(llm=fake)
    tool.analyze("测试消息: 我对螃蟹过敏")

    assert "我对螃蟹过敏" in fake.last_prompt


# =============================================================================
# 公共
# =============================================================================

def test_list_analyzer_tools_returns_three() -> None:
    """list_analyzer_tools 返 3 个 tool."""
    from food_agent.agents.analyzers import list_analyzer_tools

    tools = list_analyzer_tools()
    assert len(tools) == 3
    names = [getattr(t, "name", "") for t in tools]
    assert "analyze_weather" in names
    assert "analyze_location" in names
    assert "analyze_dietary" in names
