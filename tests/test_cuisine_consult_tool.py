"""测试 CuisineConsultTool: 把菜系专家包装为 Master 可调用的 Tool."""
from __future__ import annotations

import json

from food_agent.agents.cuisines.sichuan import SichuanAgent
from food_agent.tools.cuisine_consult import CuisineConsultTool
from tests.test_cuisine_agent import FakeLLM


def _make_agent(responses: list[str]) -> SichuanAgent:
    return SichuanAgent(llm=FakeLLM(responses))


def test_tool_has_unique_name_per_cuisine() -> None:
    """不同菜系生成不同工具名."""
    tool = CuisineConsultTool(_make_agent(["ok"]))
    assert tool.name == "consult_sichuan"
    assert "川菜" in tool.description


def test_tool_has_valid_parameters() -> None:
    """工具参数符合 qwen-agent 规范."""
    tool = CuisineConsultTool(_make_agent(["ok"]))
    assert isinstance(tool.parameters, list)
    param_names = {p["name"] for p in tool.parameters}
    assert "user_query" in param_names
    assert any(p.get("required") for p in tool.parameters)


def test_tool_call_invokes_underlying_agent() -> None:
    """call() 调用 agent.recommend() 并返回结果."""
    fake = FakeLLM(["麻婆豆腐"])
    agent = SichuanAgent(llm=fake)
    tool = CuisineConsultTool(agent)
    result = tool.call({"user_query": "想吃辣的"})
    assert "麻婆豆腐" in result
    assert fake.call_count == 1


def test_tool_call_accepts_json_string() -> None:
    """qwen-agent 传 str 时, tool 能正确解析."""
    fake = FakeLLM(["ok"])
    agent = SichuanAgent(llm=fake)
    tool = CuisineConsultTool(agent)
    result = tool.call(json.dumps({"user_query": "test"}))
    assert "ok" in result


def test_tool_passes_context() -> None:
    """context 参数应传给 agent.recommend()."""
    fake = FakeLLM(["ok"])
    agent = SichuanAgent(llm=fake)
    tool = CuisineConsultTool(agent)
    tool.call({
        "user_query": "推荐个菜",
        "context": "下雨, 一个人, 预算 50",
    })
    combined = " ".join(str(m) for m in fake.last_messages)
    assert "下雨" in combined


def test_tool_retries_on_retryable_error() -> None:
    """Tool 调用失败时, 走 RobustToolCaller 重试逻辑."""
    from food_agent.tools.base import RetryableError

    fake = FakeLLM(["success"])
    agent = SichuanAgent(llm=fake)
    # 第一次失败, 第二次成功
    original_recommend = agent.recommend
    call_count = {"n": 0}

    def flaky_recommend(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RetryableError("transient")
        return original_recommend(*args, **kwargs)

    agent.recommend = flaky_recommend  # type: ignore[method-assign]
    tool = CuisineConsultTool(agent, max_retries=3, base_delay=0.0)
    result = tool.call({"user_query": "test"})
    assert "success" in result
    assert call_count["n"] == 2


def test_tool_falls_back_to_cached_on_failure() -> None:
    """主调用失败, 降级到 fallback."""
    from food_agent.tools.base import RetryableError

    fake = FakeLLM(["primary"])
    agent = SichuanAgent(llm=fake)
    fallback = lambda *args, **kwargs: "fallback result"  # noqa: E731
    # 让 agent.recommend 总是失败
    agent.recommend = lambda *a, **k: (_ for _ in ()).throw(RetryableError("down"))  # type: ignore
    tool = CuisineConsultTool(agent, max_retries=1, base_delay=0.0, fallback=fallback)
    result = tool.call({"user_query": "test"})
    assert "fallback" in result


def test_tool_exposes_function_schema() -> None:
    """tool.function 返回 qwen-agent 用于 LLM 的 schema."""
    tool = CuisineConsultTool(_make_agent(["ok"]))
    schema = tool.function
    assert schema["name"] == "consult_sichuan"
    assert "description" in schema
    assert "parameters" in schema
