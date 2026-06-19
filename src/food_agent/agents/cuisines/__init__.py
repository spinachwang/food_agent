"""菜系专家子包.

Phase 3.3 修复: 注册表 (registry.py) 通过扫描 sys.modules 找菜系类,
但仅 import food_agent.agents.cuisines 不会自动加载子模块.
所以这里用 pkgutil 主动 import 所有同级 .py 子模块,
确保 load_all_cuisines() 能找到 13 个新菜系 + sichuan = 14 个.
"""
from __future__ import annotations

import importlib
import pkgutil

__all__: list[str] = []


def _load_all_submodules() -> None:
    """Eager import 所有 cuisines 包下的子模块."""
    for mod_info in pkgutil.iter_modules(__path__):  # type: ignore[name-defined]
        if mod_info.name.startswith("_"):
            continue
        full_name = f"{__name__}.{mod_info.name}"
        importlib.import_module(full_name)
        __all__.append(mod_info.name)


_load_all_submodules()