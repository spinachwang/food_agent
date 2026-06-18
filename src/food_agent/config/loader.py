"""yaml 配置加载器.

Phase 2.1: 把 settings.yaml / cuisines.yaml 转成 frozen dataclass.

设计:
- 用 frozen dataclass (而非 pydantic), 保持依赖轻量
- fail-fast: 缺字段 / 类型错 / 重复 id → ConfigurationError
- module-level singleton: load_settings() 缓存结果, reload() 清空
- get_setting("a.b.c") 嵌套取值, 缺路径返回 default
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

from food_agent.exceptions import ConfigurationError

# ---- 默认 yaml 路径 (项目内置) ---------------------------------------------
_PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_SETTINGS_PATH = _PACKAGE_DIR / "settings.yaml"
DEFAULT_CUISINES_PATH = _PACKAGE_DIR / "cuisines.yaml"


# =============================================================================
# Dataclasses
# =============================================================================

@dataclass(frozen=True)
class LLMConfig:
    """LLM 后端配置."""
    model: str
    base_url: str
    max_tokens: int
    temperature: float
    timeout_seconds: int


@dataclass(frozen=True)
class ToolCallerConfig:
    """工具调用容错配置."""
    max_retries: int
    base_delay_seconds: float
    max_delay_seconds: float
    jitter_ratio: float
    circuit_breaker_fail_max: int
    circuit_breaker_reset_timeout_seconds: int


@dataclass(frozen=True)
class MasterConfig:
    """Master Agent 调度配置."""
    max_rounds: int
    parallel_cuisines: int
    stream_output: bool
    cost_budget_tokens: int


@dataclass(frozen=True)
class ShortTermConfig:
    """短期记忆配置."""
    max_messages: int
    summarize_after_tokens: int
    keep_last_n_after_summary: int


@dataclass(frozen=True)
class LongTermConfig:
    """长期记忆配置."""
    sqlite_path: str
    decay_lambda: float


@dataclass(frozen=True)
class Settings:
    """全局配置 (含 5 个子配置)."""
    environment: str
    llm: LLMConfig
    tool_caller: ToolCallerConfig
    master: MasterConfig
    short_term: ShortTermConfig
    long_term: LongTermConfig


@dataclass(frozen=True)
class CuisineConfig:
    """单个菜系的元数据 (来自 cuisines.yaml)."""
    id: str
    name: str
    category: str
    subcategory: str
    prompt_file: str
    knowledge_file: str
    enabled: bool
    tags: list[str] = field(default_factory=list)


# =============================================================================
# Module-level singletons
# =============================================================================

_settings: Settings | None = None
_cuisines: list[CuisineConfig] | None = None


# =============================================================================
# load_settings()
# =============================================================================

def load_settings(path: Path | str | None = None) -> Settings:
    """加载 settings.yaml → Settings (singleton).

    Args:
        path: yaml 路径. None 时用内置 DEFAULT_SETTINGS_PATH.

    Returns:
        Settings 冻结实例.

    Raises:
        ConfigurationError: 文件不存在 / yaml 语法错 / 缺字段 / 类型错.
    """
    global _settings
    if _settings is not None:
        return _settings

    p = Path(path) if path is not None else DEFAULT_SETTINGS_PATH
    raw = _read_yaml(p, kind="settings")

    try:
        llm_raw = _require(raw, "llm", p, "settings")
        tool_raw = _require(raw, "tool_caller", p, "settings")
        master_raw = _require(raw, "master", p, "settings")
        memory_raw = _require(raw, "memory", p, "settings")
        st_raw = _require(memory_raw, "short_term", p, "memory")
        lt_raw = _require(memory_raw, "long_term", p, "memory")
        cb_raw = _require(tool_raw, "circuit_breaker", p, "tool_caller")

        settings = Settings(
            environment=_require_str(raw, "environment", p, "settings"),
            llm=LLMConfig(
                model=_require_str(llm_raw, "model", p, "llm"),
                base_url=_require_str(llm_raw, "base_url", p, "llm"),
                max_tokens=_require_int(llm_raw, "max_tokens", p, "llm"),
                temperature=_require_num(llm_raw, "temperature", p, "llm"),
                timeout_seconds=_require_int(llm_raw, "timeout_seconds", p, "llm"),
            ),
            tool_caller=ToolCallerConfig(
                max_retries=_require_int(tool_raw, "max_retries", p, "tool_caller"),
                base_delay_seconds=_require_num(tool_raw, "base_delay_seconds", p, "tool_caller"),
                max_delay_seconds=_require_num(tool_raw, "max_delay_seconds", p, "tool_caller"),
                jitter_ratio=_require_num(tool_raw, "jitter_ratio", p, "tool_caller"),
                circuit_breaker_fail_max=_require_int(cb_raw, "fail_max", p, "tool_caller.circuit_breaker"),
                circuit_breaker_reset_timeout_seconds=_require_int(cb_raw, "reset_timeout_seconds", p, "tool_caller.circuit_breaker"),
            ),
            master=MasterConfig(
                max_rounds=_require_int(master_raw, "max_rounds", p, "master"),
                parallel_cuisines=_require_int(master_raw, "parallel_cuisines", p, "master"),
                stream_output=_require_bool(master_raw, "stream_output", p, "master"),
                cost_budget_tokens=_require_int(master_raw, "cost_budget_tokens", p, "master"),
            ),
            short_term=ShortTermConfig(
                max_messages=_require_int(st_raw, "max_messages", p, "memory.short_term"),
                summarize_after_tokens=_require_int(st_raw, "summarize_after_tokens", p, "memory.short_term"),
                keep_last_n_after_summary=_require_int(st_raw, "keep_last_n_after_summary", p, "memory.short_term"),
            ),
            long_term=LongTermConfig(
                sqlite_path=_require_str(lt_raw, "sqlite_path", p, "memory.long_term"),
                decay_lambda=_require_num(lt_raw, "decay_lambda", p, "memory.long_term"),
            ),
        )
    except ConfigurationError:
        raise
    except Exception as e:  # 捕获 dataclass 构造时的 TypeError 等
        raise ConfigurationError(
            f"settings.yaml 结构错: {e} (path={p})"
        ) from e

    _settings = settings
    return settings


# =============================================================================
# load_cuisines()
# =============================================================================

def load_cuisines(path: Path | str | None = None) -> list[CuisineConfig]:
    """加载 cuisines.yaml → list[CuisineConfig] (singleton).

    Args:
        path: yaml 路径. None 时用内置 DEFAULT_CUISINES_PATH.

    Returns:
        CuisineConfig 列表 (按 yaml 顺序).

    Raises:
        ConfigurationError: 文件不存在 / yaml 语法错 / 缺 id / 重复 id.
    """
    global _cuisines
    if _cuisines is not None:
        return _cuisines

    p = Path(path) if path is not None else DEFAULT_CUISINES_PATH
    raw = _read_yaml(p, kind="cuisines")
    items = _require(raw, "cuisines", p, "cuisines")

    if not isinstance(items, list):
        raise ConfigurationError(
            f"cuisines.yaml: 'cuisines' must be a list, got {type(items).__name__} (path={p})"
        )

    cuisines: list[CuisineConfig] = []
    seen_ids: set[str] = set()
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ConfigurationError(
                f"cuisines.yaml: cuisines[{idx}] must be a dict, got {type(item).__name__} (path={p})"
            )
        cid = item.get("id")
        if not cid or not isinstance(cid, str):
            raise ConfigurationError(
                f"cuisines.yaml: cuisines[{idx}] missing or invalid 'id' (path={p})"
            )
        if cid in seen_ids:
            raise ConfigurationError(
                f"cuisines.yaml: duplicate cuisine id={cid!r} (path={p})"
            )
        seen_ids.add(cid)

        try:
            cuisines.append(
                CuisineConfig(
                    id=cid,
                    name=_require_str(item, "name", p, f"cuisines[{cid}]"),
                    category=_require_str(item, "category", p, f"cuisines[{cid}]"),
                    subcategory=_require_str(item, "subcategory", p, f"cuisines[{cid}]"),
                    prompt_file=_require_str(item, "prompt_file", p, f"cuisines[{cid}]"),
                    knowledge_file=_require_str(item, "knowledge_file", p, f"cuisines[{cid}]"),
                    enabled=_require_bool(item, "enabled", p, f"cuisines[{cid}]"),
                    tags=list(item.get("tags", []) or []),
                )
            )
        except ConfigurationError:
            raise
        except Exception as e:
            raise ConfigurationError(
                f"cuisines.yaml: cuisines[{cid}] 结构错: {e} (path={p})"
            ) from e

    _cuisines = cuisines
    return cuisines


def list_enabled_cuisines() -> list[CuisineConfig]:
    """只返回 enabled=true 的菜系."""
    return [c for c in load_cuisines() if c.enabled]


# =============================================================================
# get_setting() - 嵌套取值
# =============================================================================

def get_setting(key_path: str, default: Any = None) -> Any:
    """按 'a.b.c' 路径取 Settings 字段.

    第一次调用会触发 load_settings(). 不存在路径返回 default.
    """
    s = load_settings()
    cur: Any = s
    for part in key_path.split("."):
        if cur is None:
            return default
        if hasattr(cur, part):
            cur = getattr(cur, part)
        elif isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


# =============================================================================
# reload() - 清空 singleton
# =============================================================================

def reload() -> None:
    """清空缓存. 下次 load_*() 重新读 yaml."""
    global _settings, _cuisines
    _settings = None
    _cuisines = None


# =============================================================================
# 内部: yaml 读取 + 字段校验
# =============================================================================

def _read_yaml(path: Path, kind: str) -> dict[str, Any]:
    """读 yaml 文件, 失败 → ConfigurationError."""
    if not path.exists():
        raise ConfigurationError(
            f"{kind} yaml not found: {path}"
        )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigurationError(
            f"{kind} yaml not readable: {path} ({e})"
        ) from e
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ConfigurationError(
            f"{kind} yaml parse error: {path} ({e})"
        ) from e
    if not isinstance(data, dict):
        raise ConfigurationError(
            f"{kind} yaml top-level must be a dict, got {type(data).__name__} (path={path})"
        )
    return data


def _require(d: dict, key: str, path: Path, where: str) -> Any:
    """dict 必须含 key, 否则 ConfigurationError."""
    if not isinstance(d, dict) or key not in d:
        raise ConfigurationError(
            f"{path.name}: missing required field {where}.{key} (path={path})"
        )
    return d[key]


def _require_str(d: dict, key: str, path: Path, where: str) -> str:
    val = _require(d, key, path, where)
    if not isinstance(val, str):
        raise ConfigurationError(
            f"{path.name}: {where}.{key} must be str, got {type(val).__name__} (path={path})"
        )
    return val


def _require_int(d: dict, key: str, path: Path, where: str) -> int:
    val = _require(d, key, path, where)
    # bool 是 int 的子类, 排除
    if isinstance(val, bool) or not isinstance(val, int):
        raise ConfigurationError(
            f"{path.name}: {where}.{key} must be int, got {type(val).__name__} (path={path})"
        )
    return val


def _require_num(d: dict, key: str, path: Path, where: str) -> float:
    val = _require(d, key, path, where)
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise ConfigurationError(
            f"{path.name}: {where}.{key} must be number, got {type(val).__name__} (path={path})"
        )
    return float(val)


def _require_bool(d: dict, key: str, path: Path, where: str) -> bool:
    val = _require(d, key, path, where)
    if not isinstance(val, bool):
        raise ConfigurationError(
            f"{path.name}: {where}.{key} must be bool, got {type(val).__name__} (path={path})"
        )
    return val


__all__ = [
    "LLMConfig",
    "ToolCallerConfig",
    "MasterConfig",
    "ShortTermConfig",
    "LongTermConfig",
    "Settings",
    "CuisineConfig",
    "DEFAULT_SETTINGS_PATH",
    "DEFAULT_CUISINES_PATH",
    "load_settings",
    "load_cuisines",
    "list_enabled_cuisines",
    "get_setting",
    "reload",
]
