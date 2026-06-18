"""LLM 客户端配置.

所有 LLM 调用都通过这个模块的配置,便于切换模型/调整重试策略.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

from food_agent.exceptions import ConfigurationError

load_dotenv()


def _require_env(key: str) -> str:
    value = os.environ.get(key)
    if not value or value == f"your_{key.lower()}_here":
        raise ConfigurationError(
            f"环境变量 {key} 未设置. 请复制 .env.example 为 .env 并填入实际值."
        )
    return value


def get_llm_cfg() -> dict[str, Any]:
    """获取 LLM 配置 dict (qwen-agent / openai 兼容格式).

    Returns:
        符合 qwen-agent 要求的 LLM 配置.
    """
    return {
        "model": os.environ.get("MINIMAX_MODEL", "MiniMax-Text-01"),
        "model_server": os.environ.get(
            "MINIMAX_BASE_URL", "https://api.minimaxi.com/v1"
        ),
        "api_key": _require_env("MINIMAX_API_KEY"),
        "generate_cfg": {
            "max_tokens": int(os.environ.get("MINIMAX_MAX_TOKENS", "4096")),
            "temperature": float(os.environ.get("MINIMAX_TEMPERATURE", "0.7")),
        },
    }
