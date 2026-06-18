"""测试 CLI / Web 入口 (Phase 6 之前是 stub)."""

import pytest

from food_agent import cli, web


def test_cli_module_importable() -> None:
    """CLI 模块可以被导入."""
    assert hasattr(cli, "main")


def test_web_module_importable() -> None:
    """Web 模块可以被导入."""
    assert hasattr(web, "main")


def test_cli_main_not_implemented_yet() -> None:
    """Phase 0 stub 阶段, main 应当 raise NotImplementedError."""
    with pytest.raises(NotImplementedError):
        cli.main()


def test_web_main_not_implemented_yet() -> None:
    with pytest.raises(NotImplementedError):
        web.main()
