"""测试 RobustToolCaller: 重试 + 熔断 + 降级."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from food_agent.exceptions import (
    ToolCallError,
    ToolTimeoutError,
)
from food_agent.tools.base import (
    NonRetryableError,
    RetryableError,
    RobustToolCaller,
)


class FakeRetryableError(RetryableError):
    """测试用可重试错误."""


class FakeNonRetryableError(NonRetryableError):
    """测试用不可重试错误."""


# ---- 基本重试 ---------------------------------------------------------------

def test_returns_result_on_success() -> None:
    """成功调用直接返回结果."""
    caller = RobustToolCaller(max_retries=3, base_delay=0.0)
    func = MagicMock(return_value="ok")
    result = caller.call(func, "arg1", key="val")
    assert result == "ok"
    func.assert_called_once_with("arg1", key="val")


def test_retries_on_retryable_error() -> None:
    """可重试错误会重试, 直到成功."""
    caller = RobustToolCaller(max_retries=3, base_delay=0.0)
    func = MagicMock(side_effect=[FakeRetryableError("boom"), "ok"])
    result = caller.call(func)
    assert result == "ok"
    assert func.call_count == 2


def test_gives_up_after_max_retries() -> None:
    """超过 max_retries 后抛最后一次错误."""
    caller = RobustToolCaller(max_retries=3, base_delay=0.0)
    func = MagicMock(side_effect=FakeRetryableError("always fails"))
    with pytest.raises(FakeRetryableError):
        caller.call(func)
    assert func.call_count == 3


def test_does_not_retry_non_retryable_error() -> None:
    """不可重试错误立即抛出, 不浪费重试次数."""
    caller = RobustToolCaller(max_retries=3, base_delay=0.0)
    func = MagicMock(side_effect=FakeNonRetryableError("bad params"))
    with pytest.raises(FakeNonRetryableError):
        caller.call(func)
    assert func.call_count == 1


def test_tool_timeout_error_is_retryable() -> None:
    """ToolTimeoutError 默认可重试."""
    from food_agent.exceptions import RetryableToolCallError

    assert issubclass(ToolTimeoutError, RetryableToolCallError)


# ---- 熔断器 -----------------------------------------------------------------

def test_circuit_opens_after_threshold_failures() -> None:
    """连续 threshold 次失败后熔断."""
    caller = RobustToolCaller(
        max_retries=1,
        base_delay=0.0,
        circuit_breaker_threshold=3,
        circuit_breaker_reset_timeout=10.0,
    )
    func = MagicMock(side_effect=FakeRetryableError("boom"))
    for _ in range(3):
        with pytest.raises(FakeRetryableError):
            caller.call(func)
    # 熔断后第 4 次调用, 应该 fail fast (func 不再被调用)
    with pytest.raises(ToolCallError):
        caller.call(func)
    assert func.call_count == 3  # 没再调用


def test_circuit_half_opens_after_reset_timeout() -> None:
    """熔断 reset_timeout 后, 半开允许一次试探."""
    caller = RobustToolCaller(
        max_retries=1,
        base_delay=0.0,
        circuit_breaker_threshold=2,
        circuit_breaker_reset_timeout=0.1,
    )
    func = MagicMock(side_effect=[FakeRetryableError("boom")] * 2 + ["ok"])
    # 触发熔断
    for _ in range(2):
        with pytest.raises(FakeRetryableError):
            caller.call(func)
    # 等 reset
    time.sleep(0.15)
    # 半开后调用应成功
    result = caller.call(func)
    assert result == "ok"


# ---- 降级 -------------------------------------------------------------------

def test_uses_fallback_when_main_fails() -> None:
    """主调用失败时, 降级到 fallback."""
    caller = RobustToolCaller(max_retries=1, base_delay=0.0)
    main = MagicMock(side_effect=FakeRetryableError("primary down"))
    fallback = MagicMock(return_value="fallback-result")
    result = caller.call(main, fallback=fallback)
    assert result == "fallback-result"
    fallback.assert_called_once()


def test_uses_fallback_when_circuit_open() -> None:
    """熔断期间直接走 fallback, 不调用主."""
    caller = RobustToolCaller(
        max_retries=1,
        base_delay=0.0,
        circuit_breaker_threshold=2,
        circuit_breaker_reset_timeout=100.0,  # 故意设大避免重置
    )
    main = MagicMock(side_effect=FakeRetryableError("boom"))
    fallback = MagicMock(return_value="cached")

    # 触发熔断 (前两次调用不传 fallback, 让异常穿透)
    for _ in range(2):
        with pytest.raises(FakeRetryableError):
            caller.call(main)

    # 熔断后, 带 fallback 的调用应走 fallback
    result = caller.call(main, fallback=fallback)
    assert result == "cached"
    # 熔断期间不再调用主
    initial_call_count = 2  # 前两次都调用了
    main.assert_called()
    assert main.call_count == initial_call_count  # 没新增调用

    # 清理: 无 fallback 时应抛 ToolUnavailableError
    with pytest.raises(ToolCallError):
        caller.call(main)


# ---- 退避延迟 ----------------------------------------------------------------

def test_exponential_backoff_increases_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    """重试间隔应指数增长 (用 monkeypatch 避免真等)."""
    delays: list[float] = []
    monkeypatch.setattr("food_agent.tools.base.time.sleep", lambda d: delays.append(d))
    caller = RobustToolCaller(max_retries=4, base_delay=1.0, jitter=0.0)
    func = MagicMock(side_effect=FakeRetryableError("boom"))
    with pytest.raises(FakeRetryableError):
        caller.call(func)
    assert func.call_count == 4
    # 4 次调用, 3 次 sleep, 大致 1, 2, 4 (with max_delay cap)
    assert delays == [1.0, 2.0, 4.0]


def test_max_delay_caps_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """max_delay 限制最大间隔."""
    delays: list[float] = []
    monkeypatch.setattr("food_agent.tools.base.time.sleep", lambda d: delays.append(d))
    caller = RobustToolCaller(
        max_retries=5,
        base_delay=1.0,
        max_delay=3.0,
        jitter=0.0,
    )
    func = MagicMock(side_effect=FakeRetryableError("boom"))
    with pytest.raises(FakeRetryableError):
        caller.call(func)
    # 期望: 1, 2, 3, 3 (第 4 个应该是 4, 被 cap 到 3)
    assert delays == [1.0, 2.0, 3.0, 3.0]
