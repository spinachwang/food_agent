"""CLI 入口 (Phase 1: 一次性命令 + 简单 REPL).

用法:
    food-agent "我想吃辣的"           # 单次命令
    food-agent --chat                 # REPL 模式
    food-agent --mock "test"          # 用 mock LLM 测试
"""
from __future__ import annotations

import argparse
import os
import sys

# 强制 UTF-8 输出, 避免 Windows gbk 报错
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from food_agent.exceptions import FoodAgentError
from food_agent.master import FoodAgent


def _build_agent(mock: bool = False) -> FoodAgent:
    """构造 FoodAgent.

    Args:
        mock: True 时用 FakeLLM, 不消耗 API token.
    """
    if mock:
        from tests.test_cuisine_agent import FakeLLM

        return FoodAgent(llm=FakeLLM(["临时降级: 推荐川菜-麻婆豆腐"]))
    return FoodAgent()


def _run_once(user_msg: str, mock: bool = False) -> int:
    """单次运行, 打印结果."""
    agent = _build_agent(mock=mock)
    try:
        result = agent.run(user_msg)
    except FoodAgentError as e:
        print(f"[错误] {e}", file=sys.stderr)
        return 1
    print(result)
    return 0


def _run_repl(mock: bool = False) -> int:  # pragma: no cover
    """简单 REPL."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt

    console = Console()
    agent = _build_agent(mock=mock)

    console.print(
        Panel(
            "[bold yellow]老饕[/] 上线了! 输入 'quit' 退出, 'reset' 清空历史.",
            title="🍜 Food Agent",
        )
    )

    history: list[dict] = []
    while True:
        try:
            user_input = Prompt.ask("\n[bold green]你[/]")
        except (EOFError, KeyboardInterrupt):
            break
        if user_input.lower() in ("quit", "exit", "q"):
            break
        if user_input.lower() == "reset":
            history = []
            console.print("[dim]历史已清空.[/]")
            continue
        if not user_input.strip():
            continue

        try:
            response = agent.run(user_input, history=history)
        except FoodAgentError as e:
            console.print(f"[red][错误] {e}[/]")
            continue

        console.print(Panel(response, title="[yellow]老饕[/]"))

        # 更新历史
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": response})

    console.print("\n[dim]下次见, 别吃太辣 🌶️[/]")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI 入口."""
    parser = argparse.ArgumentParser(
        prog="food-agent",
        description="地球顶级美食家 - 多 Agent 美食推荐",
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="单次查询 (e.g. '我想吃辣的'). 不传则进入 REPL.",
    )
    parser.add_argument(
        "--chat", "-c",
        action="store_true",
        help="进入 REPL 模式",
    )
    parser.add_argument(
        "--mock", "-m",
        action="store_true",
        help="用 mock LLM, 不消耗 API token",
    )

    args = parser.parse_args(argv)

    if args.chat or args.query is None:
        return _run_repl(mock=args.mock)
    return _run_once(args.query, mock=args.mock)


if __name__ == "__main__":
    sys.exit(main())
