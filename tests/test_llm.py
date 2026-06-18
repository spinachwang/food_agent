"""测试 LLM 配置模块."""
import pytest

from food_agent.exceptions import ConfigurationError
from food_agent.llm import get_llm_cfg


def test_get_llm_cfg_returns_minimax() -> None:
    """默认配置是 MiniMax M3."""
    cfg = get_llm_cfg()
    assert "model" in cfg
    assert "model_server" in cfg
    assert "api_key" in cfg
    assert "generate_cfg" in cfg


def test_get_llm_cfg_uses_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """环境变量可覆盖默认配置."""
    monkeypatch.setenv("MINIMAX_MODEL", "custom-model")
    monkeypatch.setenv("MINIMAX_MAX_TOKENS", "8192")

    cfg = get_llm_cfg()
    assert cfg["model"] == "custom-model"
    assert cfg["generate_cfg"]["max_tokens"] == 8192


def test_missing_api_key_raises() -> None:
    """缺 API key 时 fail-fast."""
    import os

    old = os.environ.pop("MINIMAX_API_KEY", None)
    # 把默认值也清掉, 让 ConfigurationError 触发
    os.environ["MINIMAX_API_KEY"] = ""
    try:
        with pytest.raises(ConfigurationError) as excinfo:
            get_llm_cfg()
        assert "MINIMAX_API_KEY" in str(excinfo.value)
    finally:
        if old is not None:
            os.environ["MINIMAX_API_KEY"] = old
