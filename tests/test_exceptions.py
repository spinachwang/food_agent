"""测试 exceptions 模块."""
import pytest

from food_agent.exceptions import (
    ConfigurationError,
    FoodAgentError,
    LLMError,
    ToolCallError,
    ToolTimeoutError,
)


def test_food_agent_error_is_exception() -> None:
    """基类继承自 Exception."""
    assert issubclass(FoodAgentError, Exception)


def test_tool_call_error_inherits_food_agent_error() -> None:
    """ToolCallError 继承 FoodAgentError, 可以统一捕获."""
    assert issubclass(ToolCallError, FoodAgentError)
    assert issubclass(ToolTimeoutError, ToolCallError)


def test_configuration_error_inherits_food_agent_error() -> None:
    assert issubclass(ConfigurationError, FoodAgentError)


def test_llm_error_inherits_food_agent_error() -> None:
    assert issubclass(LLMError, FoodAgentError)


def test_error_can_be_raised_and_caught() -> None:
    """错误可以被抛出和捕获."""
    with pytest.raises(FoodAgentError) as excinfo:
        raise ToolTimeoutError("timeout")
    assert "timeout" in str(excinfo.value)
