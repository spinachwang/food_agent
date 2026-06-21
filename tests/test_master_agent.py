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


# =============================================================================
# 流式事件回调 (on_event) — 分阶段输出
# =============================================================================


class _ToolCallFakeLLM:
    """模拟 master LLM: 第 1 次返回 function_call, 第 2 次返回文本.

    用于测试 master.run() 在多轮 LLM 调用中能正确发 tool_call /
    tool_result 事件. 仅用作 master 的 LLM, 不影响 sub-agent.
    """

    def __init__(
        self,
        tool_name: str = "consult_sichuan",
        tool_args: str = '{"user_query": "辣的"}',
        final_text: str = "推荐: 麻婆豆腐",
    ) -> None:
        self.tool_name = tool_name
        self.tool_args = tool_args
        self.final_text = final_text
        self.call_count = 0
        self.model = "fake-toolcall"
        self.model_type = "fake"
        self.generate_cfg: dict = {}
        self.max_retries = 0
        self.cache = None
        self.use_raw_api = False

    def chat(self, messages, functions=None, stream=True, **kwargs):
        self.call_count += 1
        from qwen_agent.llm.schema import FunctionCall, Message as QMessage

        def _gen():
            if self.call_count == 1:
                # extra 必须有, 否则 qwen-agent fncall_agent.py:101 读 out.extra.get 报错
                msg = QMessage(
                    role="assistant",
                    content="",
                    function_call=FunctionCall(
                        name=self.tool_name, arguments=self.tool_args,
                    ),
                    extra={"function_id": "test_call_1"},
                )
            else:
                msg = QMessage(role="assistant", content=self.final_text)
            yield [msg]

        return _gen()


def test_run_emits_tool_call_event() -> None:
    """on_event 收到 tool_call 事件, name + args 正确."""
    sichuan_llm = FakeLLM(["麻婆豆腐 yyds"])
    sichuan_agent = SichuanAgent(llm=sichuan_llm)
    master_llm = _ToolCallFakeLLM(
        tool_name="consult_sichuan",
        tool_args='{"user_query": "想吃辣的"}',
    )
    agent = FoodAgent(llm=master_llm, cuisine_agents=[sichuan_agent])

    events: list[dict] = []
    agent.run("test", on_event=events.append)

    tool_calls = [e for e in events if e["type"] == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0]["name"] == "consult_sichuan"
    assert tool_calls[0]["args"] == {"user_query": "想吃辣的"}


def test_run_emits_tool_result_event() -> None:
    """on_event 收到 tool_result 事件, content 含工具输出."""
    sichuan_llm = FakeLLM(["麻婆豆腐 yyds"])
    sichuan_agent = SichuanAgent(llm=sichuan_llm)
    master_llm = _ToolCallFakeLLM()
    agent = FoodAgent(llm=master_llm, cuisine_agents=[sichuan_agent])

    events: list[dict] = []
    agent.run("test", on_event=events.append)

    tool_results = [e for e in events if e["type"] == "tool_result"]
    assert len(tool_results) == 1
    assert tool_results[0]["name"] == "consult_sichuan"
    assert "麻婆豆腐" in tool_results[0]["content"]
    assert tool_results[0]["ok"] is True


def test_run_without_callback_works() -> None:
    """on_event=None 时 run() 行为完全等价于旧版, 返回最终回复."""
    llm = FakeLLM([
        "调用了 consult_sichuan, 它说: 推荐陈麻婆豆腐",
    ])
    agent = FoodAgent(llm=llm)
    # 不传 on_event
    result = agent.run("test")
    assert isinstance(result, str)
    assert len(result) > 0
    # 显式传 None 也应 work
    result2 = agent.run("test", on_event=None)
    assert isinstance(result2, str)


def test_run_emits_events_in_order() -> None:
    """多工具调用场景: 同一工具的 tool_call 在 tool_result 之前."""
    sichuan_llm = FakeLLM(["麻婆豆腐 yyds"])
    sichuan_agent = SichuanAgent(llm=sichuan_llm)
    master_llm = _ToolCallFakeLLM()
    agent = FoodAgent(llm=master_llm, cuisine_agents=[sichuan_agent])

    events: list[dict] = []
    agent.run("test", on_event=events.append)

    # 应有 tool_call → tool_result 成对出现
    assert len(events) >= 2
    tool_call_idx = next(
        i for i, e in enumerate(events) if e["type"] == "tool_call"
    )
    tool_result_idx = next(
        i for i, e in enumerate(events) if e["type"] == "tool_result"
    )
    assert tool_call_idx < tool_result_idx  # tool_call 先, tool_result 后
