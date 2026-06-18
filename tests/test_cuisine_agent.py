"""测试 BaseCuisineAgent + SichuanAgent (TDD).

Phase 1: 验证菜系专家能:
1. 加载 system prompt + 知识库
2. 接收用户消息, 返回 LLM 响应
3. 暴露 metadata (id/name/category)
"""
from __future__ import annotations

from typing import Any

from food_agent.agents.cuisines.sichuan import SichuanAgent

# ---- FakeLLM: 替代真实 LLM -------------------------------------------------

class FakeLLM:
    """测试用 mock LLM.

    兼容 qwen_agent.llm.base.BaseChatModel 的接口.
    qwen-agent 内部会访问 self.llm.model, 这里给出 fake model name.
    """

    def __init__(
        self,
        canned_responses: list[str],
        model: str = "fake-model",
    ) -> None:
        self.canned_responses = canned_responses
        self.model = model
        self.model_type = "fake"
        self.generate_cfg: dict = {}
        self.max_retries = 0
        self.cache = None
        self.use_raw_api = False
        self.call_count = 0
        self.last_messages: list[dict] = []
        self.last_functions: list[dict] | None = None

    def chat(
        self,
        messages: list,
        functions: list | None = None,
        stream: bool = True,
        **kwargs: Any,
    ):
        self.call_count += 1
        self.last_messages = [
            m.model_dump() if hasattr(m, "model_dump") else dict(m)
            for m in messages
        ]
        self.last_functions = functions

        def _gen():
            resp = self.canned_responses[
                (self.call_count - 1) % len(self.canned_responses)
            ]
            from qwen_agent.llm.schema import Message as QMessage
            # qwen-agent 期望 stream 输出是 iterator of list[Message]
            yield [QMessage(role="assistant", content=resp)]

        return _gen()


# ---- BaseCuisineAgent 接口 ----------------------------------------------------

def test_base_cuisine_agent_is_abstract() -> None:
    """BaseCuisineAgent 不能直接实例化 (它是抽象概念, 用子类)."""
    # 实际上 BaseCuisineAgent 不是 ABC, 但应该有共同的 .recommend() 方法
    agent = SichuanAgent(llm=FakeLLM(["ok"]))
    assert hasattr(agent, "recommend")
    assert hasattr(agent, "cuisine_id")
    assert hasattr(agent, "cuisine_name")


def test_sichuan_agent_metadata() -> None:
    """SichuanAgent 暴露正确的元数据."""
    agent = SichuanAgent(llm=FakeLLM(["ok"]))
    assert agent.cuisine_id == "sichuan"
    assert agent.cuisine_name == "川菜"


def test_sichuan_agent_has_distinctive_prompt() -> None:
    """川菜专家 system prompt 应包含川菜相关关键词."""
    agent = SichuanAgent(llm=FakeLLM(["ok"]))
    # 验证 prompt 不是空, 且包含川菜关键概念
    assert "川菜" in agent.system_prompt or "麻婆" in agent.system_prompt


# ---- recommend() 方法 --------------------------------------------------------

def test_recommend_returns_llm_response() -> None:
    """recommend() 返回 LLM 的内容."""
    fake = FakeLLM(["推荐: 陈麻婆豆腐, 必点麻婆豆腐和夫妻肺片"])
    agent = SichuanAgent(llm=fake)
    result = agent.recommend("想吃辣的")
    assert "麻婆豆腐" in result
    assert fake.call_count == 1


def test_recommend_passes_user_message_to_llm() -> None:
    """用户消息应被传给 LLM."""
    fake = FakeLLM(["ok"])
    agent = SichuanAgent(llm=fake)
    agent.recommend("想吃辣的")
    # 检查 last_messages 包含用户消息
    assert any("想吃辣的" in str(m) for m in fake.last_messages)


def test_recommend_includes_context_if_provided() -> None:
    """如果提供 context, 应注入到 prompt."""
    fake = FakeLLM(["ok"])
    agent = SichuanAgent(llm=fake)
    agent.recommend("推荐个菜", context="下雨, 一个人, 预算 50")
    combined = " ".join(str(m) for m in fake.last_messages)
    assert "下雨" in combined
    assert "预算 50" in combined


def test_recommend_handles_streaming_response() -> None:
    """qwen-agent 内部用流式, recommend() 应正确聚合."""
    # 真实 qwen-agent 在 stream=True 时返回 generator
    # 我们的 wrapper 应正确处理
    fake = FakeLLM(["streamed result"])
    agent = SichuanAgent(llm=fake)
    result = agent.recommend("test")
    assert "streamed result" in result


def test_recommend_falls_back_on_error() -> None:
    """LLM 失败时, 返回降级响应而非抛异常给上层."""
    from food_agent.exceptions import LLMError

    class FailingLLM(FakeLLM):
        def __init__(self) -> None:
            super().__init__(canned_responses=[])

        def chat(self, *args, **kwargs):  # type: ignore[override]
            raise LLMError("API down")

    agent = SichuanAgent(llm=FailingLLM(), fallback="推荐通用川菜: 麻婆豆腐、回锅肉")
    result = agent.recommend("test")
    # 降级返回, 不抛
    assert "麻婆豆腐" in result
