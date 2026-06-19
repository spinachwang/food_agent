"""菜系/分析器动态注册中心.

Phase 2.2: 从 cuisines.yaml 动态加载所有菜系专家.

行为:
- 默认 (strict=False) 跳过 yaml 里有但 .py 未实现的菜系, 仅返回已实现的
- strict=True 时遇到未实现菜系 → ConfigurationError (fail-fast)

用法:
    >>> agents = load_all_cuisines(llm_cfg=cfg, fallback_text="...")
    >>> agents = load_all_cuisines(strict=True)  # 开发/测试: 全部必须实现
"""
from __future__ import annotations

import importlib
import inspect
import logging
import sys
from pathlib import Path
from typing import Any

from food_agent.agents.base import BaseCuisineAgent
from food_agent.config.loader import load_cuisines
from food_agent.exceptions import ConfigurationError

logger = logging.getLogger(__name__)

DEFAULT_CUISINES_PKG = "food_agent.agents.cuisines"


def _discover_cuisine_classes(
    pkg_name: str = DEFAULT_CUISINES_PKG,
) -> dict[str, type[BaseCuisineAgent]]:
    """扫描 sys.modules, 找所有 BaseCuisineAgent 子类.

    Args:
        pkg_name: cuisines 包名.

    Returns:
        {cuisine_id: class} 映射. 重复 id 后注册覆盖前者 (fail-fast 留给上层).

    Note:
        用 sys.modules 而不是 pkgutil.iter_modules, 这样:
        1) 测试可动态注入 fake module
        2) 子模块只需被 import 过 (cuisines/__init__.py 主动 import 所有子模块)

        这里必须先 import 一次包, 确保 cuisines/__init__.py 的
        "主动 import 所有子模块" 副作用生效, 否则 sys.modules
        里没东西可扫.
    """
    importlib.import_module(pkg_name)
    found: dict[str, type[BaseCuisineAgent]] = {}
    prefix = pkg_name + "."

    for mod_name, mod in list(sys.modules.items()):
        if not mod_name.startswith(prefix):
            continue
        if mod_name == pkg_name:
            continue  # 跳过包本身
        for cls in _scan_module_classes(mod):
            cid = getattr(cls, "cuisine_id", "")
            if cid and cid not in found:
                found[cid] = cls

    return found


def _scan_module_classes(mod: Any) -> list[type]:
    """扫一个模块里所有 BaseCuisineAgent 子类 (排除外部 import)."""
    classes: list[type] = []
    for name in dir(mod):
        if name.startswith("_"):
            continue
        try:
            obj = getattr(mod, name)
        except AttributeError:
            continue
        if not inspect.isclass(obj):
            continue
        if obj is BaseCuisineAgent:
            continue
        if not issubclass(obj, BaseCuisineAgent):
            continue
        classes.append(obj)
    return classes


def load_all_cuisines(
    llm_cfg: Any | None = None,
    fallback_text: str | None = None,
    cuisines_yaml_path: Path | str | None = None,
    *,
    strict: bool = False,
) -> list[BaseCuisineAgent]:
    """加载 + 实例化所有 enabled 菜系.

    Args:
        llm_cfg: LLM 配置 (dict 或 BaseChatModel). None 时由 agent 内部用默认.
        fallback_text: 失败降级文本, 传给每个 agent. None 表示无降级.
        cuisines_yaml_path: yaml 路径. None 用内置.
        strict: True 时遇到未实现菜系 → ConfigurationError (fail-fast).
               False 时跳过未实现菜系 (log warning).

    Returns:
        BaseCuisineAgent 实例列表, 按 yaml 顺序.

    Raises:
        ConfigurationError: strict=True 且 yaml 引用了未实现菜系.
    """
    if cuisines_yaml_path is not None:
        cuisines = load_cuisines(cuisines_yaml_path)
    else:
        cuisines = load_cuisines()
    enabled = [c for c in cuisines if c.enabled]
    classes_by_id = _discover_cuisine_classes()

    agents: list[BaseCuisineAgent] = []
    for c in enabled:
        if c.id not in classes_by_id:
            msg = (
                f"cuisines.yaml 引用了未实现的菜系: {c.id!r}. "
                f"需要在 food_agent/agents/cuisines/{c.id}.py 里实现 BaseCuisineAgent 子类."
            )
            if strict:
                raise ConfigurationError(msg)
            logger.warning("skip unimplemented cuisine: %s", c.id)
            continue
        cls = classes_by_id[c.id]
        agents.append(cls(llm=llm_cfg, fallback=fallback_text))
    return agents


__all__ = ["load_all_cuisines", "DEFAULT_CUISINES_PKG"]
