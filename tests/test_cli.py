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
