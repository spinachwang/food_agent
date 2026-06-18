# pytest 全局 fixtures
"""
所有测试共享的 fixtures:
- mock_llm_response: mock qwen-agent 的 LLM 调用
- settings: 测试用配置
- tmp_db: 临时 SQLite 数据库
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

# 测试期间不读 .env, 强制使用 fake key
os.environ.setdefault("MINIMAX_API_KEY", "test-fake-key-for-tests")
os.environ.setdefault("MINIMAX_BASE_URL", "http://localhost:0/v1")


@pytest.fixture
def project_root() -> Path:
    """项目根目录."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def fake_llm_response() -> dict[str, Any]:
    """一个 mock LLM 响应的模板."""
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "🎯 推荐：陈麻婆豆腐（川菜）",
                }
            }
        ]
    }
