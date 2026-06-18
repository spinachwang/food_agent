"""测试 src/food_agent/memory/short_term.py (TDD).

Phase 2.5: 短期记忆 - 滑动窗口 + token 阈值触发摘要.
"""
from __future__ import annotations

from typing import Any

import pytest


# =============================================================================
# Fake LLM for summary (同其他测试, 独立定义避免依赖)
# =============================================================================

class FakeLLM:
    """测试用 mock LLM, 模拟 qwen_agent BaseChatModel 接口."""

    def __init__(self, canned_responses: list[str]) -> None:
        self.canned_responses = canned_responses
        self.model = "fake"
        self.model_type = "fake"
        self.generate_cfg: dict = {}
        self.max_retries = 0
        self.cache = None
        self.use_raw_api = False
        self.call_count = 0
        self.last_messages: list = []

    def chat(self, messages, functions=None, stream=True, **kwargs):
        self.call_count += 1
        self.last_messages = list(messages)
        from qwen_agent.llm.schema import Message as QMessage

        def _gen():
            resp = self.canned_responses[(self.call_count - 1) % len(self.canned_responses)]
            yield [QMessage(role="assistant", content=resp)]
        return _gen()


class FailingLLM:
    """测试用失败 LLM."""

    def __init__(self) -> None:
        self.model = "fake"
        self.model_type = "fake"
        self.call_count = 0

    def chat(self, *args, **kwargs):
        self.call_count += 1
        raise RuntimeError("LLM API down")


# =============================================================================
# Imports
# =============================================================================

from food_agent.memory.short_term import ShortTermMemory


# =============================================================================
# 基本功能: add / get_messages
# =============================================================================

def test_add_and_get_messages() -> None:
    """add 后 get_messages 返回顺序保持."""
    stm = ShortTermMemory()
    stm.add({"role": "user", "content": "你好"})
    stm.add({"role": "assistant", "content": "你好! 推荐川菜"})
    msgs = stm.get_messages()
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"


def test_get_messages_no_summary() -> None:
    """没 summary 时 get_messages 就是 _messages 的副本."""
    stm = ShortTermMemory()
    stm.add({"role": "user", "content": "a"})
    msgs = stm.get_messages()
    assert len(msgs) == 1
    assert msgs[0]["content"] == "a"


def test_len() -> None:
    """__len__ 返回消息数."""
    stm = ShortTermMemory()
    assert len(stm) == 0
    stm.add({"role": "user", "content": "x"})
    assert len(stm) == 1


def test_clear() -> None:
    """clear 清空所有消息和 summary."""
    stm = ShortTermMemory()
    stm.add({"role": "user", "content": "a"})
    stm.add({"role": "assistant", "content": "b"})
    stm._summary = "旧 summary"
    stm.clear()
    assert len(stm) == 0
    assert stm._summary is None


# =============================================================================
# 滑动窗口: 超 max_messages 截断
# =============================================================================

def test_truncates_when_exceeds_max_messages() -> None:
    """超 max_messages 时自动截断最早的消息."""
    stm = ShortTermMemory(max_messages=4)
    for i in range(6):
        stm.add({"role": "user", "content": f"msg-{i}"})
    # 应该只保留最后 4 条
    msgs = stm.get_messages()
    assert len(msgs) == 4
    assert [m["content"] for m in msgs] == ["msg-2", "msg-3", "msg-4", "msg-5"]


# =============================================================================
# token 阈值: should_summarize
# =============================================================================

def test_should_summarize_false_when_under_threshold() -> None:
    """token 总数未超阈值 → False."""
    stm = ShortTermMemory(summarize_after_tokens=10000)
    for i in range(5):
        stm.add({"role": "user", "content": "短"})
    assert stm.should_summarize() is False


def test_should_summarize_true_when_over_threshold() -> None:
    """token 总数超阈值 → True."""
    stm = ShortTermMemory(summarize_after_tokens=100)
    # chars/4 = tokens, 100 tokens = 400 chars
    big = "x" * 500
    for i in range(2):
        stm.add({"role": "user", "content": big})
    assert stm.should_summarize() is True


def test_estimate_tokens_chars_div_4() -> None:
    """_estimate_tokens 估算函数: chars//4."""
    stm = ShortTermMemory()
    stm.add({"role": "user", "content": "a" * 400})  # 100 tokens
    stm.summarize_after_tokens = 50
    assert stm.should_summarize() is True
    stm.summarize_after_tokens = 200
    assert stm.should_summarize() is False


# =============================================================================
# summarize: 调 LLM, 保留最近 N 条 + summary 头
# =============================================================================

def test_summarize_calls_llm_and_keeps_recent() -> None:
    """summarize() 调 LLM 摘要, 保留最近 N 条, summary 写入 _summary."""
    fake = FakeLLM(["这是对话摘要"])
    stm = ShortTermMemory(keep_last_n_after_summary=2, max_messages=100)
    for i in range(6):
        stm.add({"role": "user" if i % 2 == 0 else "assistant", "content": f"msg-{i}"})

    stm.summarize(llm_cfg=fake)  # type: ignore[arg-type]

    # LLM 被调 1 次
    assert fake.call_count == 1
    # summary 被记录
    assert stm._summary is not None
    assert "这是对话摘要" in stm._summary
    # 保留最近 2 条 (msg-4 user, msg-5 assistant)
    msgs = stm.get_messages()
    assert [m["content"] for m in msgs[-2:]] == ["msg-4", "msg-5"]
    # 总消息数: 1 system summary + 2 recent
    assert len(msgs) == 3
    assert msgs[0]["role"] == "system"


def test_summarize_failure_falls_back_to_truncate() -> None:
    """LLM 失败 → 降级硬截断到最近 N 条, 不抛异常."""
    failing = FailingLLM()
    stm = ShortTermMemory(keep_last_n_after_summary=2)
    for i in range(5):
        stm.add({"role": "user" if i % 2 == 0 else "assistant", "content": f"msg-{i}"})

    stm.summarize(llm_cfg=failing)  # type: ignore[arg-type]

    # 失败时 summary 应为 None (不写入脏数据)
    assert stm._summary is None
    # 硬截断到最近 2 条
    msgs = stm.get_messages()
    assert [m["content"] for m in msgs] == ["msg-3", "msg-4"]


def test_summarize_too_few_messages_noop() -> None:
    """消息数 ≤ keep_last_n, 不调 LLM, noop."""
    fake = FakeLLM(["不应该被调"])
    stm = ShortTermMemory(keep_last_n_after_summary=3)
    stm.add({"role": "user", "content": "only msg"})

    stm.summarize(llm_cfg=fake)  # type: ignore[arg-type]

    # LLM 不应被调
    assert fake.call_count == 0
    # 消息不变
    assert len(stm.get_messages()) == 1


# =============================================================================
# FoodAgent 集成
# =============================================================================

def test_foodagent_session_id_preserves_history() -> None:
    """FoodAgent(session_id) 多次 run, 后者能看到前者的对话."""
    from food_agent.agents.cuisines.sichuan import SichuanAgent
    from food_agent.master import FoodAgent

    fake = FakeLLM([
        "1st response",
        "2nd response (should see history)",
    ])
    agent = FoodAgent(llm=fake)  # type: ignore[arg-type]

    a1 = agent.run("first question", session_id="s1")
    a2 = agent.run("second question", session_id="s1")
    assert "1st" in a1 or "response" in a1
    assert "2nd" in a2 or "response" in a2
    # 第二次 LLM 调用时, 消息列表应包含前一轮的 user + assistant
    second_call_messages = fake.last_messages
    combined = " ".join(str(m) for m in second_call_messages)
    assert "first question" in combined
    assert "1st response" in combined


def test_foodagent_different_sessions_isolated() -> None:
    """不同 session_id 互不干扰."""
    from food_agent.agents.cuisines.sichuan import SichuanAgent
    from food_agent.master import FoodAgent

    fake = FakeLLM(["r1", "r2", "r3", "r4"])
    agent = FoodAgent(llm=fake)  # type: ignore[arg-type]

    agent.run("u1", session_id="s1")
    # s2 完全独立, 上轮历史不应出现
    fake.call_count = 0
    agent.run("u2", session_id="s2")
    combined = " ".join(str(m) for m in fake.last_messages)
    assert "u1" not in combined  # s1 的消息不应串到 s2


def test_foodagent_no_session_id_works_as_before() -> None:
    """不传 session_id 仍能跑通 (Phase 1 兼容)."""
    from food_agent.agents.cuisines.sichuan import SichuanAgent
    from food_agent.master import FoodAgent

    fake = FakeLLM(["ok"])
    agent = FoodAgent(llm=fake)  # type: ignore[arg-type]
    result = agent.run("test")
    assert "ok" in result


# =============================================================================
# 防御式: 异常输入
# =============================================================================

def test_add_ignores_non_dict() -> None:
    """add 非 dict 输入应忽略或抛 TypeError (不静默吞)."""
    stm = ShortTermMemory()
    with pytest.raises(TypeError):
        stm.add("not a dict")  # type: ignore[arg-type]


def test_add_validates_role() -> None:
    """add 的 dict 必须有 role 字段."""
    stm = ShortTermMemory()
    with pytest.raises((KeyError, ValueError, TypeError)):
        stm.add({"content": "x"})  # 缺 role
