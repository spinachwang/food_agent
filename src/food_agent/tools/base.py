"""自定义 Tool 基类 + RobustToolCaller.

工具调用三件套:
- 重试 (exponential backoff + jitter)
- 熔断 (consecutive failure threshold)
- 降级 (fallback callable)
"""
from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from food_agent.exceptions import (
    NonRetryableToolCallError,
    RetryableToolCallError,
    ToolCallError,
    ToolUnavailableError,
)

T = TypeVar("T")


# ---- 错误分类 ---------------------------------------------------------------

class RetryableError(RetryableToolCallError):
    """可重试的工具错误 (网络/超时/限流/5xx)."""


class NonRetryableError(NonRetryableToolCallError):
    """不可重试的工具错误 (参数错/权限错/404)."""


# ---- 熔断器状态 -------------------------------------------------------------

@dataclass
class CircuitBreakerState:
    """熔断器状态."""

    fail_max: int = 5
    reset_timeout: float = 60.0
    consecutive_failures: int = 0
    opened_at: float | None = None  # 熔断开始时间

    @property
    def is_open(self) -> bool:
        """当前是否熔断 (且未到 reset 时间)."""
        if self.opened_at is None:
            return False
        return (time.monotonic() - self.opened_at) < self.reset_timeout

    @property
    def is_half_open(self) -> bool:
        """是否到达 reset 时间, 允许试探一次."""
        if self.opened_at is None:
            return False
        return (time.monotonic() - self.opened_at) >= self.reset_timeout

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.fail_max:
            self.opened_at = time.monotonic()


# ---- 指数退避 ---------------------------------------------------------------

def _compute_backoff(
    attempt: int,
    base_delay: float,
    max_delay: float,
    jitter: float,
) -> float:
    """计算第 N 次重试的延迟 (秒).

    公式: delay = min(base_delay * 2^attempt, max_delay) * (1 ± jitter)
    attempt 从 0 开始 (第 1 次重试).
    """
    delay = min(base_delay * (2 ** attempt), max_delay)
    if jitter > 0:
        delay *= 1.0 + random.uniform(-jitter, jitter)
    return max(0.0, delay)


# ---- RobustToolCaller --------------------------------------------------------

@dataclass
class RobustToolCaller:
    """工具调用三件套: 重试 + 熔断 + 降级.

    Example:
        >>> caller = RobustToolCaller(max_retries=3, base_delay=1.0)
        >>> result = caller.call(my_tool.invoke, "params",
        ...                      fallback=my_tool_fallback.invoke)
    """

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    jitter: float = 0.2
    circuit_breaker_threshold: int = 5
    circuit_breaker_reset_timeout: float = 60.0
    breaker: CircuitBreakerState = field(init=False)

    def __post_init__(self) -> None:
        self.breaker = CircuitBreakerState(
            fail_max=self.circuit_breaker_threshold,
            reset_timeout=self.circuit_breaker_reset_timeout,
        )

    def call(
        self,
        func: Callable[..., T],
        *args: Any,
        fallback: Callable[..., T] | None = None,
        **kwargs: Any,
    ) -> T:
        """调用 func, 自动重试/熔断/降级.

        Args:
            func: 主函数.
            *args / **kwargs: 传给 func.
            fallback: 降级函数, 签名应与 func 兼容.

        Returns:
            func 或 fallback 的返回值.

        Raises:
            RetryableError / NonRetryableError: 重试耗尽或不可重试.
            ToolUnavailableError: 熔断中且无 fallback.
        """
        # 熔断中 → 直接走 fallback
        if self.breaker.is_open:
            if fallback is not None:
                return fallback(*args, **kwargs)
            raise ToolUnavailableError(
                f"tool unavailable: circuit open "
                f"(failures={self.breaker.consecutive_failures})"
            )

        # 半开 → 重置 failure 计数, 允许一次试探
        if self.breaker.is_half_open:
            self.breaker.consecutive_failures = 0
            self.breaker.opened_at = None

        last_error: ToolCallError | None = None
        for attempt in range(self.max_retries):
            try:
                result = func(*args, **kwargs)
            except NonRetryableError:
                # 不可重试, 立即失败
                self.breaker.record_failure()
                raise
            except RetryableError as e:
                last_error = e
                self.breaker.record_failure()
                # 检查是否已熔断
                if self.breaker.is_open:
                    break
                # 最后一次不 sleep
                if attempt < self.max_retries - 1:
                    delay = _compute_backoff(
                        attempt,
                        self.base_delay,
                        self.max_delay,
                        self.jitter,
                    )
                    time.sleep(delay)
            except Exception as e:
                # 未知异常包装为不可重试, fail fast
                raise NonRetryableError(str(e)) from e
            else:
                self.breaker.record_success()
                return result

        # 重试耗尽
        if fallback is not None:
            return fallback(*args, **kwargs)
        assert last_error is not None
        raise last_error
