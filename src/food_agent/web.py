"""Gradio Web Demo 入口 (Phase 3.5).

直接复用 qwen_agent.gui.WebUI 包装 FoodAgent._assistant (qwen-agent Assistant),
零代码跑 Gradio 聊天界面. 14 菜系调度 + 3 analyzer + 高德 MCP 都自动接入.

Trade-off (vs 走 FoodAgent.run()):
- ✅ 14 菜系调度 + 高德 MCP (assistant 已含这些 tools)
- ❌ 短期/长期记忆 (WebUI 自己管 history, 不走 STM/LTM)
- ❌ 饮食偏好自动保存 (FoodAgent.run() 才触发)
- ❌ on_event 流式进度 (WebUI 是黑盒)
- Phase 3.5 (现在): 用 WebUI 跑通, 接受以上 trade-off
- Phase 6 (未来): 自定义 gr.ChatInterface + FoodAgent.run() + 流式 on_event

用法:
    PYTHONIOENCODING=utf-8 conda run -n qwenagent-mcp python -m food_agent.web
    # 浏览器打开 http://127.0.0.1:7860

环境变量:
    AMAP_USE_MOCK / AMAP_API_KEY: 高德 (CLI 同款, 见 cli._build_amap_client)
    FOOD_AGENT_USER_ID: web 端 user_id (默认 "web_user")
    FOOD_AGENT_WEB_HOST: 监听地址 (默认 127.0.0.1)
    FOOD_AGENT_WEB_PORT: 端口 (默认 7860)
"""
from __future__ import annotations

import os

from food_agent.cli import _build_agent

# Lazy import: gradio 依赖可能没装, 或在 pytest 严格 warnings 模式下
# import modelscope_studio.components.legacy 时触发 DeprecationWarning 被
# 升级为 error. 顶层 try/except 兜底, 真正使用时再报清晰错误.
try:
    from qwen_agent.gui import WebUI
except Exception:  # pragma: no cover
    WebUI = None  # type: ignore[assignment]


def main() -> None:  # pragma: no cover
    """启动 Gradio Web Demo."""
    if WebUI is None:
        raise ImportError(
            "WebUI 不可用. 请装 gradio + modelscope_studio: "
            "pip install 'qwen-agent[gui]'"
        )

    # 复用 CLI 的构造逻辑: amap_client / long_term 都自动配好
    agent = _build_agent()

    host = os.environ.get("FOOD_AGENT_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("FOOD_AGENT_WEB_PORT", "7860"))

    WebUI(
        agent._assistant,
        chatbot_config={
            # user.name / agent.name 是聊天框里显示的名字, 可放 emoji
            "user.name": "你",
            "agent.name": "🍜 老饕",
            # agent.avatar 是 bot 封面大图, 必须是图片文件路径 (gif/jpeg/png)
            # 不传则用 qwen-agent 默认图; 想自定义可传本地 PNG 路径.
            "input.placeholder": "想吃啥? 输入 quit 退不出 (web 模式不限时)",
            "prompt.suggestions": [
                "我想吃辣的, 一个人, 预算 100",
                "今天北京下雨, 推荐暖的汤面",
                "我在北京海淀, 附近 2km 的川菜",
                "我对花生过敏, 不爱吃香菜, 晚饭推荐",
            ],
        },
    ).run(
        server_name=host,
        server_port=port,
        share=False,  # 不开公网 tunnel (安全)
    )


if __name__ == "__main__":
    main()