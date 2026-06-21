"""测试 web.py: 验证 _build_agent + WebUI 构造, 不真 launch Gradio."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from food_agent import web


def test_web_module_imports() -> None:
    """web.py 能被 import 不报错."""
    assert callable(web.main)


def test_main_constructs_webui(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() 调用 _build_agent 拿 agent, 把 agent._assistant 传给 WebUI.

    不真 launch Gradio (会卡住), 通过 mock WebUI.run 验证参数.
    """
    # 模拟 WebUI class — 构造时记录传入的 agent, run() 不真启动
    captured: dict = {}

    class FakeWebUI:
        def __init__(self, agent, chatbot_config=None, **kwargs):
            captured["agent"] = agent
            captured["chatbot_config"] = chatbot_config

        def run(self, **kwargs):
            captured["run_kwargs"] = kwargs

    # 强制 mock 模式 (避免 .env AMAP_API_KEY 在 CI 报错)
    monkeypatch.setenv("AMAP_USE_MOCK", "true")
    # web.py 顶部 import 了 WebUI, 直接 patch module 级别
    monkeypatch.setattr(web, "WebUI", FakeWebUI)

    web.main()

    # 验证 agent._assistant 被传给 WebUI
    assert captured["agent"] is not None
    # 验证 chatbot_config 有 title / suggestions
    cfg = captured["chatbot_config"]
    assert "input.placeholder" in cfg
    assert "prompt.suggestions" in cfg
    assert len(cfg["prompt.suggestions"]) >= 1
    # 验证 run() 拿到 host/port
    assert "server_name" in captured["run_kwargs"]
    assert "server_port" in captured["run_kwargs"]


def test_main_respects_web_host_port_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """FOOD_AGENT_WEB_HOST / _PORT 环境变量被读."""
    monkeypatch.setenv("AMAP_USE_MOCK", "true")
    monkeypatch.setenv("FOOD_AGENT_WEB_HOST", "0.0.0.0")
    monkeypatch.setenv("FOOD_AGENT_WEB_PORT", "9000")

    captured: dict = {}

    class FakeWebUI:
        def __init__(self, agent, chatbot_config=None, **kwargs):
            pass

        def run(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(web, "WebUI", FakeWebUI)
    web.main()

    assert captured["server_name"] == "0.0.0.0"
    assert captured["server_port"] == 9000