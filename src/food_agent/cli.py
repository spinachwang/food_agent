"""CLI 入口 (Phase 1: 一次性命令 + 简单 REPL).

用法:
    food-agent "我想吃辣的"             # 单次命令
    food-agent --chat                   # REPL 模式 (默认 verbose 显示分阶段进度)
    food-agent --mock "test"            # 用 mock LLM 测试
    food-agent --no-memory "test"       # 关闭 long_term (Phase 1 兼容)
    food-agent --user-id alice "test"   # 指定 user_id (多用户隔离)
    food-agent --memory-db /tmp/x.db    # 改 db 路径 (默认 ./data/food_agent.db)
    food-agent --verbose "test"         # 单次模式: 显示分阶段进度 (REPL 默认开)
    food-agent --amap-mock "test"       # amap 走 mock (覆盖 .env, 省 key 配额)
    food-agent --no-amap "test"         # 关闭 amap (analyzer 返 confidence=0)

Phase B 修复: 默认启用 long_term, 自动持久化饮食偏好.
Phase 流式输出: REPL 默认 + 单次 --verbose, 通过 on_event 回调分阶段打印
(master 思考 → 分析器调用 → 子 agent 请教 → 综合 → 最终结果).
Amap: CLI 默认从 .env 读 AMAP_API_KEY / AMAP_USE_MOCK 构造 AmapClient;
     否则 analyzer 全部报 "AmapClient 未配置".
"""
from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from pathlib import Path

# 强制 UTF-8 输出, 避免 Windows gbk 报错
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from food_agent.exceptions import FoodAgentError
from food_agent.mcp.amap_client import AmapClient
from food_agent.master import EVENT_TOOL_CALL, EVENT_TOOL_RESULT, FoodAgent


# 默认 db 路径 (项目内 data/ 目录)
# cli.py 在 src/food_agent/cli.py, 上 3 层 parent = 项目根
_DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "food_agent.db"

# 工具名 → (emoji, 中文标签) 映射. consult_<id> 在 handler 运行时按菜系名动态生成.
_TOOL_LABELS: dict[str, tuple[str, str]] = {
    "analyze_weather": ("🌦️ ", "查询天气"),
    "analyze_location": ("📍", "定位"),
    "analyze_dietary": ("🥗 ", "提取饮食限制"),
    "geocode": ("🗺️ ", "地理编码"),
    "regeocode": ("🗺️ ", "逆地理编码"),
    "search_around": ("🔍", "周边搜索"),
    "weather": ("🌦️ ", "查询天气"),
    "route": ("🚗", "路径规划"),
}
_RESULT_PREVIEW_MAX = 80  # 工具结果预览最大字符数


def _make_event_handler(
    cuisine_names: dict[str, str] | None = None,
) -> Callable[[dict], None]:
    """构造 CLI 事件 handler. 用 rich console 打印分阶段进度.

    Args:
        cuisine_names: cuisine_id → cuisine_name 映射, 用来把 consult_sichuan
            转成 "请教川菜专家". None 时用 cuisine_id 兜底.

    Returns:
        on_event 回调, 签名 (event: dict) -> None.
    """
    from rich.console import Console

    console = Console()
    cuisines = cuisine_names or {}

    def handler(event: dict) -> None:
        etype = event.get("type")
        tool_name = event.get("name", "")

        if etype == EVENT_TOOL_CALL:
            emoji, label = _TOOL_LABELS.get(tool_name, ("🔧", tool_name))
            if tool_name.startswith("consult_"):
                cuisine_id = tool_name[len("consult_"):]
                cuisine_name = cuisines.get(cuisine_id, cuisine_id)
                label = f"请教{cuisine_name}专家"
                emoji = "🍜 "
            console.print(f"[cyan]{emoji} {label}...[/]")

        elif etype == EVENT_TOOL_RESULT:
            content = event.get("content", "") or ""
            ok = event.get("ok", True)
            # 截断 + 折叠换行, 太长会淹没其他输出
            preview = content[:_RESULT_PREVIEW_MAX].replace("\n", " ")
            if len(content) > _RESULT_PREVIEW_MAX:
                preview += "..."
            color = "green" if ok else "red"
            mark = "✅" if ok else "❌"
            console.print(f"[{color}]{mark} {preview}[/]")

        # 未知事件类型: 静默忽略 (未来加新事件时改这里)

    return handler


def _build_amap_client(amap_mock: bool = False, no_amap: bool = False) -> Any:
    """构造 AmapClient, 默认从 env 读配置.

    Args:
        amap_mock: 强制 mock 模式 (覆盖 env).
        no_amap: 禁用 amap (返回 None), analyzer 会返回 confidence=0,
            不影响主流程.

    Returns:
        AmapClient 实例, 或 None (禁用).
    """
    if no_amap:
        return None
    if amap_mock:
        return AmapClient(use_mock=True)
    # 默认: 让 AmapClient 自己读 env (AMAP_USE_MOCK / AMAP_API_KEY)
    try:
        return AmapClient()
    except ValueError as e:
        # 缺 key 又非 mock → 关闭 amap, 不阻塞 CLI
        print(f"[警告] AmapClient 未启用: {e}", file=sys.stderr)
        return None


def _build_agent(
    mock: bool = False,
    no_memory: bool = False,
    db_path: str | None = None,
    amap_mock: bool = False,
    no_amap: bool = False,
) -> FoodAgent:
    """构造 FoodAgent.

    Args:
        mock: True 时用 FakeLLM, 不消耗 API token.
        no_memory: True 时不启用 long_term (Phase 1 兼容).
        db_path: 改默认 db 路径. None 时用 _DEFAULT_DB_PATH.
        amap_mock: 强制 amap 走 mock 模式 (覆盖 env).
        no_amap: 关闭 amap (analyzer 返回 confidence=0, 不阻塞).
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

    # 构造 amap client (默认从 env 读 AMAP_API_KEY/AMAP_USE_MOCK).
    # 关键: 不传 amap_client 会导致 analyzer 内部 get_amap_client() 返 None,
    # 3 个 analyzer (天气/位置/饮食) 全部报 "AmapClient 未配置".
    amap_client = _build_amap_client(amap_mock=amap_mock, no_amap=no_amap)
    return FoodAgent(llm=llm, long_term=long_term, amap_client=amap_client)


def _run_once(
    user_msg: str,
    mock: bool = False,
    user_id: str = "default",
    no_memory: bool = False,
    db_path: str | None = None,
    verbose: bool = False,
    amap_mock: bool = False,
    no_amap: bool = False,
) -> int:
    """单次运行, 打印结果.

    Args:
        verbose: True 时显示分阶段进度 (REPL 默认开, 单次需 --verbose).
        amap_mock: 强制 amap 走 mock 模式.
        no_amap: 关闭 amap.
    """
    agent = _build_agent(
        mock=mock, no_memory=no_memory, db_path=db_path,
        amap_mock=amap_mock, no_amap=no_amap,
    )
    on_event = (
        _make_event_handler(
            cuisine_names={a.cuisine_id: a.cuisine_name for a in agent.cuisine_agents},
        )
        if verbose
        else None
    )
    try:
        result = agent.run(user_msg, user_id=user_id, on_event=on_event)
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
    verbose: bool = True,  # REPL 默认 verbose
    amap_mock: bool = False,
    no_amap: bool = False,
) -> int:  # pragma: no cover
    """简单 REPL. 默认 verbose 显示分阶段进度.

    Args:
        verbose: REPL 模式下默认 True, --verbose 显式传 True (REPL 模式忽略).
        amap_mock: 强制 amap 走 mock 模式.
        no_amap: 关闭 amap.
    """
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt

    console = Console()
    agent = _build_agent(
        mock=mock, no_memory=no_memory, db_path=db_path,
        amap_mock=amap_mock, no_amap=no_amap,
    )
    on_event = (
        _make_event_handler(
            cuisine_names={a.cuisine_id: a.cuisine_name for a in agent.cuisine_agents},
        )
        if verbose
        else None
    )

    console.print(
        Panel(
            "[bold yellow]老饕[/] 上线了! 输入 'quit' 退出, 'reset' 清空历史.",
            title="🍜 Food Agent",
        )
    )

    # 稳定 session_id 让 STM 接管 (token 阈值 + LLM 摘要)
    # 同 user 复用同一 session, 不同 user 隔离
    session_id = f"repl-{user_id}"

    while True:
        try:
            user_input = Prompt.ask("\n[bold green]你[/]")
        except (EOFError, KeyboardInterrupt):
            break
        if user_input.lower() in ("quit", "exit", "q"):
            break
        if user_input.lower() == "reset":
            agent.clear_stm(session_id)
            console.print("[dim]会话已重置.[/]")
            continue
        if not user_input.strip():
            continue

        try:
            response = agent.run(
                user_input, session_id=session_id, user_id=user_id, on_event=on_event,
            )
        except FoodAgentError as e:
            console.print(f"[red][错误] {e}[/]")
            continue

        console.print(Panel(response, title="[yellow]老饕[/]"))

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
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help=(
            "显示分阶段进度 (master 思考 / 工具调用 / 子 agent 请教). "
            "REPL 默认开启, 单次模式需显式指定."
        ),
    )
    parser.add_argument(
        "--amap-mock",
        action="store_true",
        help="强制 amap 走 mock 模式 (覆盖 .env 的 AMAP_USE_MOCK), 省 key 配额",
    )
    parser.add_argument(
        "--no-amap",
        action="store_true",
        help="关闭 amap (天气/位置 analyzer 返 confidence=0, 不阻塞主流程)",
    )

    args = parser.parse_args(argv)

    if args.chat or args.query is None:
        return _run_repl(
            mock=args.mock,
            user_id=args.user_id,
            no_memory=args.no_memory,
            db_path=args.memory_db,
            verbose=True,  # REPL 默认 verbose, 不管 --verbose
            amap_mock=args.amap_mock,
            no_amap=args.no_amap,
        )
    return _run_once(
        args.query,
        mock=args.mock,
        user_id=args.user_id,
        no_memory=args.no_memory,
        db_path=args.memory_db,
        verbose=args.verbose,
        amap_mock=args.amap_mock,
        no_amap=args.no_amap,
    )


if __name__ == "__main__":
    sys.exit(main())
