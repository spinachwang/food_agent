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


# ---- qwen-agent 兼容层 patch 回归测试 ----------------------------------------
# 背景: qwen-agent 0.0.34 在 _conv_qwen_agent_messages_to_oai() 中把内部
# 'function' 角色转为 OpenAI 'tool' 角色时, 把 link id 写到 'id' 字段, 而
# MiniMax/OpenAI 规范要求 'tool_call_id' 字段, 触发 400 错误
# "invalid params, tool result's tool id() not found (2013)".
# food_agent.llm 在导入时 monkey-patch 修复此 bug. 本组测试锁住修复行为,
# 防止上游升级或重构时悄悄回归.


def _build_tool_use_messages() -> list[dict]:
    """模拟 use_raw_api=True 时, master agent 调一次 tool 的完整消息序列."""
    return [
        {"role": "user", "content": "我想吃辣的, 一个人, 预算 100"},
        {
            "role": "assistant",
            "content": "",
            "function_call": {
                "name": "consult_sichuan",
                "arguments": '{"user_query":"辣的"}',
            },
            "extra": {"function_id": "call_abc123"},
        },
        {
            "role": "function",
            "content": "麻婆豆腐",
            "extra": {"function_id": "call_abc123"},
        },
    ]


def test_tool_message_has_tool_call_id_not_id() -> None:
    """function→tool 转换后, tool 消息必须有 tool_call_id, 不能有 id."""
    # food_agent.llm 已在 conftest/import 时打过补丁
    from qwen_agent.llm.base import BaseChatModel

    result = BaseChatModel._conv_qwen_agent_messages_to_oai(
        _build_tool_use_messages()
    )

    tool_msgs = [m for m in result if isinstance(m, dict) and m.get("role") == "tool"]
    assert len(tool_msgs) == 1, f"期望 1 条 tool 消息, 实际 {len(tool_msgs)}"

    tool_msg = tool_msgs[0]
    assert "tool_call_id" in tool_msg, (
        "tool 消息缺 tool_call_id 字段 — MiniMax/OpenAI 会返回 400 "
        "'tool result's tool id() not found'. patch 失效?"
    )
    assert tool_msg["tool_call_id"] == "call_abc123", (
        f"tool_call_id 应等于 assistant tool_calls[i].id (call_abc123), "
        f"实际 {tool_msg['tool_call_id']!r}"
    )
    assert "id" not in tool_msg, (
        "tool 消息不应再有 'id' 字段 — OpenAI/MiniMax 不认这个字段名"
    )


def test_tool_call_id_matches_assistant_function_id() -> None:
    """tool 消息的 tool_call_id 必须与 assistant 的 function_id 一致.

    两者一致是工具调用多轮对话能继续的基础 — API 用它把 tool result 关联回
    assistant 的 tool_calls[i]. 任何脱节都会导致 400.
    """
    from qwen_agent.llm.base import BaseChatModel

    result = BaseChatModel._conv_qwen_agent_messages_to_oai(
        _build_tool_use_messages()
    )

    assistant_tool_call_ids = [
        tc["id"]
        for msg in result
        if msg.get("role") == "assistant"
        for tc in msg.get("tool_calls", [])
    ]
    tool_call_ids = [
        m["tool_call_id"]
        for m in result
        if m.get("role") == "tool" and "tool_call_id" in m
    ]

    assert assistant_tool_call_ids == ["call_abc123"]
    assert tool_call_ids == ["call_abc123"]
    assert assistant_tool_call_ids == tool_call_ids


def test_patch_is_idempotent() -> None:
    """重复 patch 不应产生副作用 (例如双重包装 / 字段错乱)."""
    from food_agent.llm import _patch_qwen_agent_tool_call_id
    from qwen_agent.llm.base import BaseChatModel

    _patch_qwen_agent_tool_call_id()
    _patch_qwen_agent_tool_call_id()

    result = BaseChatModel._conv_qwen_agent_messages_to_oai(
        _build_tool_use_messages()
    )
    tool_msgs = [m for m in result if m.get("role") == "tool"]
    assert tool_msgs[0]["tool_call_id"] == "call_abc123"
    assert "id" not in tool_msgs[0]


def test_patch_handles_multiple_tool_calls() -> None:
    """一次调多个 tool 时, 每个 tool 消息的 tool_call_id 都应对得上."""
    from qwen_agent.llm.base import BaseChatModel

    msgs = [
        {"role": "user", "content": "推荐川菜和粤菜"},
        {
            "role": "assistant",
            "content": "",
            "function_call": {"name": "consult_sichuan", "arguments": "{}"},
            "extra": {"function_id": "call_001"},
        },
        {
            "role": "assistant",
            "content": "",
            "function_call": {"name": "consult_cantonese", "arguments": "{}"},
            "extra": {"function_id": "call_002"},
        },
        {
            "role": "function",
            "content": "麻婆豆腐",
            "extra": {"function_id": "call_001"},
        },
        {
            "role": "function",
            "content": "白切鸡",
            "extra": {"function_id": "call_002"},
        },
    ]
    result = BaseChatModel._conv_qwen_agent_messages_to_oai(msgs)

    tool_msgs = [m for m in result if m.get("role") == "tool"]
    assert len(tool_msgs) == 2
    ids = {m["tool_call_id"] for m in tool_msgs}
    assert ids == {"call_001", "call_002"}, f"tool_call_id 失配: {ids}"


def test_patch_preserves_other_message_roles() -> None:
    """patch 只动 tool 消息, 不影响 user / assistant / system."""
    from qwen_agent.llm.base import BaseChatModel

    result = BaseChatModel._conv_qwen_agent_messages_to_oai(
        _build_tool_use_messages()
    )
    roles = [m.get("role") for m in result]
    assert "user" in roles
    assert "assistant" in roles
    assert "tool" in roles

    # assistant 消息的 tool_calls 必须保留 'id' 字段 (这是 OpenAI 规范要求的)
    assistant = next(m for m in result if m.get("role") == "assistant")
    assert assistant["tool_calls"][0]["id"] == "call_abc123"
