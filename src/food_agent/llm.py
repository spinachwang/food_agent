"""LLM 客户端配置.

所有 LLM 调用都通过这个模块的配置,便于切换模型/调整重试策略.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

from food_agent.exceptions import ConfigurationError

load_dotenv()


def _patch_qwen_agent_tool_call_id() -> None:
    """修复 qwen-agent 0.0.34 的 tool_call_id 字段名 bug.

    Bug 位置: qwen_agent/llm/base.py:_conv_qwen_agent_messages_to_oai().
    当把内部 'function' 角色转换为 OpenAI 'tool' 角色时, 错误地把 link id
    写到 'id' 字段, 而 OpenAI 规范 (MiniMax / GPT / 其他 OpenAI-兼容 API
    通用) 要求 'tool_call_id' 字段. 后果: MiniMax 返回
    "invalid params, tool result's tool id() not found (2013)", 400.

    修法: 启动时 monkey-patch BaseChatModel 的静态方法, 转换后把
    'id' 重命名为 'tool_call_id'. 防御式写法: 如果 upstream 已修, 跳
    过 patch (避免重复/冲突).

    升级 qwen-agent 后: 若 upstream 已自带 tool_call_id, 此函数自动
    变成 no-op; 若仍有 bug, 继续生效. 无需手动清理.
    """
    try:
        from qwen_agent.llm.base import BaseChatModel
    except ImportError:
        # qwen-agent 未安装, 不需要 patch
        return

    # 避免重复 patch (例如模块被 reload)
    if getattr(BaseChatModel, "_food_agent_tool_call_id_patched", False):
        return

    _original = BaseChatModel._conv_qwen_agent_messages_to_oai

    @staticmethod  # type: ignore[misc]
    def _patched(messages: Any) -> Any:
        result = _original(messages)
        for msg in result:
            if isinstance(msg, dict) and msg.get("role") == "tool":
                # 防御式: 只在缺 tool_call_id 时重命名, 不覆盖已有字段
                if "id" in msg and "tool_call_id" not in msg:
                    msg["tool_call_id"] = msg.pop("id")
        return result

    BaseChatModel._conv_qwen_agent_messages_to_oai = _patched  # type: ignore[assignment]
    BaseChatModel._food_agent_tool_call_id_patched = True  # type: ignore[attr-defined]


# 导入 qwen-agent 时立即打补丁, 保证后续 Assistant 实例化前生效.
_patch_qwen_agent_tool_call_id()


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

    Note:
        use_raw_api=True 强制 qwen-agent 走 OpenAI 原生 tool_calls 协议,
        跳过 nous_fncall_prompt 的 <tool_call> 文本模板 (MiniMax M3 / GPT 等
        native tool_call 模型必需). 详见 qwen-agent/llm/base.py 的
        _preprocess_messages / chat() 分支.
    """
    return {
        "model": os.environ.get("MINIMAX_MODEL", "MiniMax-M3"),
        "model_server": os.environ.get(
            "MINIMAX_BASE_URL", "https://api.minimaxi.com/v1"
        ),
        "api_key": _require_env("MINIMAX_API_KEY"),
        "generate_cfg": {
            "max_tokens": int(os.environ.get("MINIMAX_MAX_TOKENS", "4096")),
            "temperature": float(os.environ.get("MINIMAX_TEMPERATURE", "0.7")),
            "use_raw_api": True,  # 走 OpenAI 原生 tool_calls 协议
        },
    }
