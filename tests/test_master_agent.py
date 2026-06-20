"""测试 FoodAgent (Master Foodie Agent)."""
from __future__ import annotations

import pytest

from food_agent.agents.cuisines.sichuan import SichuanAgent
from food_agent.master import FoodAgent
from food_agent.tools.cuisine_consult import CuisineConsultTool
from tests.test_cuisine_agent import FakeLLM


def test_food_agent_loads_default_cuisines() -> None:
    """默认加载 Phase 1 的 1 个菜系 (sichuan)."""
    llm = FakeLLM(["ok"])
    agent = FoodAgent(llm=llm)
    assert any(isinstance(a, SichuanAgent) for a in agent.cuisine_agents)


def test_food_agent_builds_tools_from_agents() -> None:
    """每个菜系 agent 对应一个 consult tool, + 3 个 analyzer tool (Phase 3.2)."""
    llm = FakeLLM(["ok"])
    agent = FoodAgent(llm=llm)
    tool_names = {t.name for t in agent.tools}
    assert "consult_sichuan" in tool_names
    # analyzer tool (Phase 3.2) 也应自动加入
    assert "analyze_weather" in tool_names
    assert "analyze_location" in tool_names
    assert "analyze_dietary" in tool_names
    # consult_* 类 tool 都是 CuisineConsultTool
    consult_tools = [t for t in agent.tools if t.name.startswith("consult_")]
    assert all(isinstance(t, CuisineConsultTool) for t in consult_tools)


def test_food_agent_loads_master_prompt() -> None:
    """Master system prompt 从文件加载, 不为空."""
    llm = FakeLLM(["ok"])
    agent = FoodAgent(llm=llm)
    assert agent.system_prompt
    # 提示词应包含关键词
    assert "美食家" in agent.system_prompt or "老饕" in agent.system_prompt


def test_food_agent_accepts_custom_cuisines() -> None:
    """可以注入自定义菜系列表."""
    custom_sichuan = SichuanAgent(llm=FakeLLM(["custom"]), name="sichuan")
    agent = FoodAgent(llm=FakeLLM(["ok"]), cuisine_agents=[custom_sichuan])
    assert agent.cuisine_agents == [custom_sichuan]


def test_food_agent_run_returns_response() -> None:
    """run() 返回 assistant 的响应文本."""
    llm = FakeLLM([
        # 第一次: 模拟 LLM 决定调用 consult_sichuan
        # 第二次: 综合结果
        "调用了 consult_sichuan, 它说: 推荐陈麻婆豆腐",
    ])
    agent = FoodAgent(llm=llm)
    result = agent.run("我想吃辣的")
    assert isinstance(result, str)
    assert len(result) > 0


def test_food_agent_tools_are_callable_directly() -> None:
    """Master 的 tools 可以被直接调用, 间接验证调度链路."""
    sichuan_llm = FakeLLM(["麻婆豆腐 yyds"])
    sichuan_agent = SichuanAgent(llm=sichuan_llm)
    food_agent_llm = FakeLLM(["ok"])
    agent = FoodAgent(llm=food_agent_llm, cuisine_agents=[sichuan_agent])

    # 找到 consult_sichuan 工具
    tool = next(t for t in agent.tools if t.name == "consult_sichuan")
    result = tool.call({"user_query": "想吃辣的"})
    assert "麻婆豆腐" in result
    assert sichuan_llm.call_count >= 1


def test_food_agent_dispatches_via_tool_function(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证 Master 包含 cuisine tools, 工具调用最终调用到 agent."""
    sichuan_llm = FakeLLM(["综合结果: 推荐麻婆豆腐"])
    sichuan_agent = SichuanAgent(llm=sichuan_llm)
    food_agent_llm = FakeLLM(["ok"])
    agent = FoodAgent(llm=food_agent_llm, cuisine_agents=[sichuan_agent])

    # 直接调用 tool, 验证 agent.recommend 被触发
    for tool in agent.tools:
        if tool.name == "consult_sichuan":
            result = tool.call({"user_query": "test"})
            assert sichuan_llm.call_count == 1
            assert "麻婆豆腐" in result
            break
    else:
        pytest.fail("consult_sichuan tool not found")


def test_food_agent_handles_empty_response() -> None:
    """assistant 返回空时, 给降级文本."""
    llm = FakeLLM([""])
    agent = FoodAgent(llm=llm)
    result = agent.run("test")
    # 降级文本包含"老饕"或"稍后"
    assert "老饕" in result or "稍后" in result or "不可用" in result


def test_food_agent_propagates_llm_error() -> None:
    """LLM 不可恢复错误时, 抛出 LLMError."""
    from food_agent.exceptions import LLMError

    class FailingLLM(FakeLLM):
        def __init__(self) -> None:
            super().__init__(canned_responses=[])

        def chat(self, *args, **kwargs):  # type: ignore[override]
            raise LLMError("API down")

    agent = FoodAgent(llm=FailingLLM())
    with pytest.raises(LLMError):
        agent.run("test")


def test_master_prompt_file_exists() -> None:
    """Master prompt 文件存在, 路径正确."""
    from food_agent.master import MASTER_PROMPT_PATH

    assert MASTER_PROMPT_PATH.exists()
    content = MASTER_PROMPT_PATH.read_text(encoding="utf-8")
    assert "美食家" in content or "老饕" in content


def test_food_agent_repr() -> None:
    """__repr__ 应有信息量."""
    llm = FakeLLM(["ok"])
    agent = FoodAgent(llm=llm)
    r = repr(agent)
    assert "FoodAgent" in r
    assert "cuisines" in r or "sichuan" in r


# =============================================================================
# Phase B-2 bugfix: dict LLM config 包装成 LLM 实例 (dietary 用)
# =============================================================================

def test_food_agent_dict_llm_wrapped_for_dietary(monkeypatch: pytest.MonkeyPatch) -> None:
    """master.llm 是 dict (qwen-agent config) 时, dietary tool 拿到 BaseChatModel 实例.

    Bug: 之前 dietary._llm = dict, dict.chat() 不存在, 走 fallback keyword,
    like_preferences 永远空. CLI 默认用 get_llm_cfg() 返 dict, 触发 bug.
    """
    # 模拟 dict config (不需要真 API key, 跑不到 chat 也能验)
    from food_agent.llm import get_llm_cfg
    from food_agent.agents.analyzers.dietary import DietaryAnalyzerTool

    # 用 FakeLLM 当 raw llm, 但 FoodAgent 拿 dict 形式, 验证内部包装
    # 直接测: master.py 的 _resolve_llm_instance 函数
    from food_agent.master import _resolve_llm_instance

    fake_instance = FakeLLM(["ok"])
    # dict 包装
    # monkeypatch get_chat_model 避免真 API
    from unittest.mock import patch

    with patch("food_agent.master.get_chat_model", return_value=fake_instance) as m:
        cfg = {"model": "fake", "model_server": "fake", "api_key": "fake"}
        result = _resolve_llm_instance(cfg)
        assert result is fake_instance
        m.assert_called_once_with(cfg)

    # 已经 BaseChatModel 风格的对象直接返回
    assert _resolve_llm_instance(fake_instance) is fake_instance


def test_food_agent_dietary_tool_receives_llm_instance() -> None:
    """FoodAgent 初始化后, analyze_dietary 工具的 _llm 是可调 chat() 的对象.

    端到端: dict LLM 也能让 dietary 走 LLM 抽取路径.
    """
    from unittest.mock import patch, MagicMock
    from food_agent.llm import get_llm_cfg

    fake_llm_instance = FakeLLM(["ok"])
    cfg = {"model": "fake", "model_server": "fake", "api_key": "fake"}

    with patch("food_agent.master.get_chat_model", return_value=fake_llm_instance):
        agent = FoodAgent(llm=cfg)  # 传 dict, 模拟 CLI 默认
        # 找 dietary tool
        dietary = next(t for t in agent.tools if t.name == "analyze_dietary")
        assert dietary._llm is fake_llm_instance  # 不是 dict!
