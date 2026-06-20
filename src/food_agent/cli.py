"""CLI 入口 (Phase 1: 一次性命令 + 简单 REPL).

用法:
    food-agent "我想吃辣的"             # 单次命令
    food-agent --chat                   # REPL 模式
    food-agent --mock "test"            # 用 mock LLM 测试
    food-agent --no-memory "test"       # 关闭 long_term (Phase 1 兼容)
    food-agent --user-id alice "test"   # 指定 user_id (多用户隔离)
    food-agent --memory-db /tmp/x.db    # 改 db 路径 (默认 ./data/food_agent.db)

Phase B 修复: 默认启用 long_term, 自动持久化饮食偏好.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# 强制 UTF-8 输出, 避免 Windows gbk 报错
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from food_agent.exceptions import FoodAgentError
from food_agent.master import FoodAgent


# 默认 db 路径 (项目内 data/ 目录)
# cli.py 在 src/food_agent/cli.py, 上 3 层 parent = 项目根
_DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "food_agent.db"


def _build_agent(
    mock: bool = False,
    no_memory: bool = False,
    db_path: str | None = None,
) -> FoodAgent:
    """构造 FoodAgent.

    Args:
        mock: True 时用 FakeLLM, 不消耗 API token.
        no_memory: True 时不启用 long_term (Phase 1 兼容).
        db_path: 改默认 db 路径. None 时用 _DEFAULT_DB_PATH.
    """
    if mock:
        from tests.test_cuisine_agent import FakeLLM

        llm = FakeLLM(["临时降级: 推荐川菜-麻婆豆腐"])
    else:
        llm = None

    long_term = None
    if not no_memory:
        from food_agent.memory.long_term import LongTermMemory

        path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        path.parent.mkdir(parents=True, exist_ok=True)  # sqlite3 需要父目录存在
        long_term = LongTermMemory(path)

    return FoodAgent(llm=llm, long_term=long_term)


def _run_once(
    user_msg: str,
    mock: bool = False,
    user_id: str = "default",
    no_memory: bool = False,
    db_path: str | None = None,
) -> int:
    """单次运行, 打印结果."""
    agent = _build_agent(mock=mock, no_memory=no_memory, db_path=db_path)
    try:
        result = agent.run(user_msg, user_id=user_id)
    except FoodAgentError as e:
        print(f"[错误] {e}", file=sys.stderr)
        return 1
    print(result)
    return 0


def _run_repl(
    mock: bool = False,
    user_id: str = "default",
    no_memory: bool = False,
    db_path: str | None = None,
) -> int:  # pragma: no cover
    """简单 REPL."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt

    console = Console()
    agent = _build_agent(mock=mock, no_memory=no_memory, db_path=db_path)

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
            response = agent.run(user_input, history=history, user_id=user_id)
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
    parser.add_argument(
        "--no-memory",
        action="store_true",
        help="关闭长期记忆 (Phase 1 兼容行为)",
    )
    parser.add_argument(
        "--user-id",
        default="default",
        help="用户 ID, 用于长期记忆隔离 (默认 'default')",
    )
    parser.add_argument(
        "--memory-db",
        default=None,
        help=f"长期记忆 db 路径 (默认 {_DEFAULT_DB_PATH})",
    )

    args = parser.parse_args(argv)

    if args.chat or args.query is None:
        return _run_repl(
            mock=args.mock,
            user_id=args.user_id,
            no_memory=args.no_memory,
            db_path=args.memory_db,
        )
    return _run_once(
        args.query,
        mock=args.mock,
        user_id=args.user_id,
        no_memory=args.no_memory,
        db_path=args.memory_db,
    )


if __name__ == "__main__":
    sys.exit(main())
