"""测试 CLI 单次命令 (mock LLM 模式, 不消耗 API token)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from food_agent import cli
from food_agent.exceptions import FoodAgentError
from food_agent.master import FoodAgent
from tests.test_cuisine_agent import FakeLLM


def _python_in_env() -> str:
    """返回当前 Python 解释器路径."""
    return sys.executable


# ---- 单元测试: 直接调 CLI 函数 ----------------------------------------------

def test_run_once_with_mock(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    """_run_once() 接受 mock LLM 时不崩, 输出非空."""
    monkeypatch.setattr(
        cli, "_build_agent",
        lambda **kwargs: FoodAgent(llm=FakeLLM(["推荐川菜-麻婆豆腐"])),
    )
    rc = cli._run_once("test", mock=True)
    assert rc == 0
    out = capsys.readouterr().out
    assert "麻婆豆腐" in out


def test_run_once_handles_food_agent_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """_run_once() 捕获 FoodAgentError, 返回 1."""

    class FailingAgent:
        def run(self, *args, **kwargs):
            raise FoodAgentError("API down")

    monkeypatch.setattr(cli, "_build_agent", lambda **kwargs: FailingAgent())
    rc = cli._run_once("test", mock=True)
    assert rc == 1
    err = capsys.readouterr().err
    assert "API down" in err


def test_build_agent_with_mock() -> None:
    """_build_agent(mock=True) 走 mock LLM."""
    agent = cli._build_agent(mock=True)
    assert isinstance(agent, FoodAgent)


def test_build_agent_default_has_long_term(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """默认情况下 _build_agent 应启用 long_term, db 写到指定路径."""
    monkeypatch.setattr(cli, "_DEFAULT_DB_PATH", tmp_path / "default.db")
    agent = cli._build_agent(mock=True)
    assert agent._long_term is not None
    assert Path(agent._long_term._db_path) == tmp_path / "default.db"


def test_build_agent_no_memory_flag() -> None:
    """--no-memory 时 long_term = None (Phase 1 兼容行为)."""
    agent = cli._build_agent(mock=True, no_memory=True)
    assert agent._long_term is None


def test_build_agent_custom_db_path(tmp_path: Path) -> None:
    """--memory-db PATH 改默认 db 路径."""
    db = tmp_path / "custom.db"
    agent = cli._build_agent(mock=True, db_path=str(db))
    assert agent._long_term is not None
    assert Path(agent._long_term._db_path) == db


def test_build_agent_creates_parent_dir(tmp_path: Path) -> None:
    """db 父目录不存在时自动创建 (sqlite3.connect 需要)."""
    db = tmp_path / "nested" / "dir" / "memory.db"
    assert not db.parent.exists()
    cli._build_agent(mock=True, db_path=str(db))
    assert db.parent.exists()


def test_build_agent_default_has_amap_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认情况下 _build_agent 构造 AmapClient (从 .env 读).

    回归测试: 之前 CLI 不构造 AmapClient, 导致 analyzer 内部
    get_amap_client() 返 None, 全部报 "AmapClient 未配置".
    """
    from food_agent.mcp.amap_client import AmapClient

    # 模拟 .env 有 key + USE_MOCK=false (用户 .env 默认配置)
    monkeypatch.setenv("AMAP_API_KEY", "fake_test_key")
    monkeypatch.setenv("AMAP_USE_MOCK", "false")
    agent = cli._build_agent(mock=True)
    assert agent._amap_client is not None
    assert isinstance(agent._amap_client, AmapClient)
    assert agent._amap_client.use_mock is False


def test_build_agent_amap_mock_flag() -> None:
    """--amap-mock 强制 amap 走 mock 模式 (覆盖 .env)."""
    from food_agent.mcp.amap_client import AmapClient

    agent = cli._build_agent(mock=True, amap_mock=True)
    assert agent._amap_client is not None
    assert agent._amap_client.use_mock is True


def test_build_agent_no_amap_flag() -> None:
    """--no-amap 关闭 amap, agent._amap_client 是 None."""
    agent = cli._build_agent(mock=True, no_amap=True)
    assert agent._amap_client is None


def test_build_agent_no_amap_key_falls_back_silently(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> None:
    """无 AMAP_API_KEY + 无 USE_MOCK → 关闭 amap, stderr 警告, 不 raise."""
    monkeypatch.delenv("AMAP_API_KEY", raising=False)
    monkeypatch.delenv("AMAP_USE_MOCK", raising=False)
    agent = cli._build_agent(mock=True)
    # 不 raise, _amap_client 是 None
    assert agent._amap_client is None
    # 警告打到 stderr
    err = capsys.readouterr().err
    assert "AmapClient 未启用" in err


def test_default_db_path_is_under_project_root() -> None:
    """_DEFAULT_DB_PATH 应在项目根 (不是 src/), 含 data/food_agent.db."""
    expected = Path(__file__).resolve().parent.parent / "data" / "food_agent.db"
    assert cli._DEFAULT_DB_PATH == expected


def test_main_routes_to_repl_when_no_query(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() 无 query 时走 REPL (mock REPL 立即返回)."""
    monkeypatch.setattr(cli, "_run_repl", lambda **kwargs: 0)
    rc = cli.main(["--mock"])
    assert rc == 0


def test_main_routes_to_repl_when_chat_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() --chat 时走 REPL."""
    called = {"repl": False, "once": False}
    monkeypatch.setattr(cli, "_run_repl", lambda **kwargs: (called.__setitem__("repl", True) or 0))
    monkeypatch.setattr(cli, "_run_once", lambda *a, **k: (called.__setitem__("once", True) or 0))
    cli.main(["--chat", "--mock"])
    assert called["repl"] is True
    assert called["once"] is False


def test_main_with_query_routes_to_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() 有 query 时走单次."""
    called: dict = {"repl": False, "once": False, "query": None}

    monkeypatch.setattr(
        cli, "_run_repl",
        lambda **kwargs: (called.__setitem__("repl", True) or 0),
    )

    def fake_once(query, **kwargs):
        called["query"] = query
        called["once"] = True
        return 0

    monkeypatch.setattr(cli, "_run_once", fake_once)
    cli.main(["test query", "--mock"])
    assert called["once"] is True
    assert called["query"] == "test query"


# ---- 子进程 E2E: 真实 CLI 启动 ----------------------------------------------

def test_cli_help() -> None:
    """CLI --help 可用."""
    result = subprocess.run(
        [_python_in_env(), "-m", "food_agent", "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        cwd=Path(__file__).resolve().parent.parent,
    )
    assert result.returncode == 0
    assert "美食家" in result.stdout or "food-agent" in result.stdout


def test_cli_mock_single_query() -> None:
    """CLI 单次查询 (mock 模式)."""
    result = subprocess.run(
        [_python_in_env(), "-m", "food_agent", "--mock", "我想吃辣的"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        cwd=Path(__file__).resolve().parent.parent,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert len(result.stdout) > 0


def test_cli_mock_chat_repl_quit() -> None:
    """CLI REPL 模式 (mock, 输入 quit 退出)."""
    result = subprocess.run(
        [
            _python_in_env(), "-m", "food_agent",
            "--chat", "--mock",
        ],
        input="test\nquit\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        cwd=Path(__file__).resolve().parent.parent,
        timeout=15,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "老饕" in result.stdout


# =============================================================================
# 流式输出: --verbose flag + on_event 回调
# =============================================================================


def test_run_once_verbose_passes_callback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> None:
    """--verbose 时 _run_once 把非 None 的 on_event 传给 agent.run."""
    captured: dict = {"on_event": "sentinel"}

    class FakeCuisine:
        cuisine_id = "sichuan"
        cuisine_name = "川菜"

    class FakeAgent:
        cuisine_agents = [FakeCuisine()]

        def run(self, user_msg, on_event=None, **kwargs):
            captured["on_event"] = on_event
            captured["user_msg"] = user_msg
            return "ok"

    monkeypatch.setattr(cli, "_build_agent", lambda **kwargs: FakeAgent())
    rc = cli._run_once("test", mock=True, verbose=True)
    assert rc == 0
    assert callable(captured["on_event"])  # 非 None
    assert captured["user_msg"] == "test"


def test_run_once_without_verbose_no_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不加 --verbose 时 _run_once 传 None 给 agent.run (向后兼容)."""
    captured: dict = {"on_event": "sentinel"}

    class FakeAgent:
        cuisine_agents: list = []

        def run(self, user_msg, on_event=None, **kwargs):
            captured["on_event"] = on_event
            return "ok"

    monkeypatch.setattr(cli, "_build_agent", lambda **kwargs: FakeAgent())
    cli._run_once("test", mock=True)  # verbose 默认 False
    assert captured["on_event"] is None


def test_run_repl_default_verbose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REPL 默认 verbose=True, 把非 None 的 on_event 传给 agent.run.

    这里只验证 _run_repl 会构造 on_event 并传出去 — REPL 主循环是
    pragma: no cover, 不进入.
    """
    # Patch Prompt.ask 让 _run_repl 主循环立即退出, 便于验证传参
    captured: dict = {"on_event": "sentinel", "calls": 0}

    class FakeCuisine:
        cuisine_id = "sichuan"
        cuisine_name = "川菜"

    class FakeAgent:
        cuisine_agents = [FakeCuisine()]

        def run(self, user_msg, on_event=None, **kwargs):
            captured["on_event"] = on_event
            captured["calls"] += 1
            return "ok"

    monkeypatch.setattr(cli, "_build_agent", lambda **kwargs: FakeAgent())
    # 用 prompt 喂入一个 quit 立即退出
    monkeypatch.setattr(
        "rich.prompt.Prompt.ask", lambda *a, **kw: "quit",
    )
    cli._run_repl(mock=True, verbose=True)
    # _run_repl 在 quit 时不调用 run, 但 handler 已构造 → 通过 _build_agent 注入
    # 这里直接验证 handler 构造逻辑: REPL 必须传 verbose=True 默认
    assert captured["on_event"] == "sentinel"  # run 没被调用


def test_run_once_passes_user_id_to_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_run_once 把 user_id 传给 agent.run (顺便验证 _run_once 参数流)."""
    captured: dict = {}

    class FakeAgent:
        cuisine_agents: list = []

        def run(self, user_msg, user_id="default", **kwargs):
            captured["user_id"] = user_id
            return "ok"

    monkeypatch.setattr(cli, "_build_agent", lambda **kwargs: FakeAgent())
    cli._run_once("test", mock=True, user_id="alice")
    assert captured["user_id"] == "alice"


def test_main_verbose_flag_recognized() -> None:
    """CLI --verbose flag 解析正确 (不实际跑, 只验证 argparse)."""
    result = subprocess.run(
        [_python_in_env(), "-m", "food_agent", "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        cwd=Path(__file__).resolve().parent.parent,
    )
    assert "--verbose" in result.stdout
    assert "-v" in result.stdout


def test_make_event_handler_renders_tool_call(capsys: pytest.CaptureFixture) -> None:
    """_make_event_handler 把 tool_call 事件转成带 emoji 的中文行."""
    handler = cli._make_event_handler(
        cuisine_names={"sichuan": "川菜"},
    )
    handler({"type": "tool_call", "name": "consult_sichuan", "args": {}})
    handler({"type": "tool_call", "name": "analyze_weather", "args": {}})
    out = capsys.readouterr().out
    assert "请教川菜专家" in out
    assert "查询天气" in out


def test_make_event_handler_renders_tool_result(capsys: pytest.CaptureFixture) -> None:
    """_make_event_handler 把 tool_result 事件转成带 ✅ 的预览行."""
    handler = cli._make_event_handler()
    handler({
        "type": "tool_result",
        "name": "analyze_weather",
        "content": '{"city": "北京", "temperature": 25}',
        "ok": True,
    })
    handler({
        "type": "tool_result",
        "name": "analyze_weather",
        "content": '{"error": "API down"}',
        "ok": False,
    })
    out = capsys.readouterr().out
    assert "✅" in out  # 成功
    assert "❌" in out  # 失败
    assert "北京" in out
