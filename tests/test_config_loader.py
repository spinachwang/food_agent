"""测试 src/food_agent/config/loader.py (TDD).

Phase 2.1: yaml 配置加载器.
"""
from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from food_agent.config import loader
from food_agent.exceptions import ConfigurationError


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def tmp_settings_yaml(tmp_path: Path) -> Path:
    """写一个合法的 settings.yaml 到临时目录."""
    p = tmp_path / "settings.yaml"
    p.write_text(
        dedent(
            """\
            environment: development

            llm:
              model: MiniMax-M3
              base_url: https://api.minimaxi.com/v1
              max_tokens: 4096
              temperature: 0.7
              timeout_seconds: 30

            tool_caller:
              max_retries: 3
              base_delay_seconds: 1.0
              max_delay_seconds: 30.0
              jitter_ratio: 0.2
              circuit_breaker:
                fail_max: 5
                reset_timeout_seconds: 60

            master:
              max_rounds: 10
              parallel_cuisines: 3
              stream_output: true
              cost_budget_tokens: 8000

            memory:
              short_term:
                max_messages: 30
                summarize_after_tokens: 6000
                keep_last_n_after_summary: 6
              long_term:
                sqlite_path: ./data/food_agent.db
                decay_lambda: 0.01
            """
        ),
        encoding="utf-8",
    )
    return p


@pytest.fixture
def tmp_cuisines_yaml(tmp_path: Path) -> Path:
    """写一个合法的 cuisines.yaml (3 个菜系, 其中 1 个 disabled)."""
    p = tmp_path / "cuisines.yaml"
    p.write_text(
        dedent(
            """\
            cuisines:
              - id: sichuan
                name: 川菜
                category: formal_cn
                subcategory: sichuan
                prompt_file: sichuan_v1.md
                knowledge_file: sichuan.md
                enabled: true
                tags: [辣, 重口味]

              - id: cantonese
                name: 粤菜
                category: formal_cn
                subcategory: cantonese
                prompt_file: cantonese_v1.md
                knowledge_file: cantonese.md
                enabled: true
                tags: [清淡, 鲜]

              - id: disabled_cuisine
                name: 隐身菜系
                category: snack
                subcategory: x
                prompt_file: x_v1.md
                knowledge_file: x.md
                enabled: false
                tags: [test]
            """
        ),
        encoding="utf-8",
    )
    return p


@pytest.fixture(autouse=True)
def _reset_singletons():
    """每个测试前后清空 loader 的 module-level singleton."""
    loader._settings = None
    loader._cuisines = None
    yield
    loader._settings = None
    loader._cuisines = None


# =============================================================================
# load_settings() - 合法 yaml
# =============================================================================

def test_load_settings_returns_settings_dataclass(tmp_settings_yaml: Path) -> None:
    """合法 yaml 返回 Settings dataclass."""
    s = loader.load_settings(tmp_settings_yaml)
    assert s.environment == "development"
    assert s.llm.model == "MiniMax-M3"
    assert s.llm.max_tokens == 4096
    assert s.llm.temperature == 0.7
    assert s.tool_caller.max_retries == 3
    assert s.tool_caller.circuit_breaker_fail_max == 5
    assert s.master.max_rounds == 10
    assert s.master.cost_budget_tokens == 8000
    assert s.short_term.max_messages == 30
    assert s.long_term.decay_lambda == 0.01


def test_load_settings_is_cached(tmp_settings_yaml: Path) -> None:
    """重复调用返回同一对象 (singleton)."""
    s1 = loader.load_settings(tmp_settings_yaml)
    s2 = loader.load_settings(tmp_settings_yaml)
    assert s1 is s2


def test_load_settings_default_path() -> None:
    """不传 path 时用项目内置的 settings.yaml."""
    s = loader.load_settings()
    assert s.environment in ("development", "production", "test")
    assert s.llm.model  # 非空


# =============================================================================
# load_settings() - 缺字段 / 类型错 → ConfigurationError
# =============================================================================

def test_load_settings_missing_required_field_raises(tmp_path: Path) -> None:
    """缺 master.max_rounds 字段 → ConfigurationError."""
    p = tmp_path / "bad.yaml"
    p.write_text(
        dedent(
            """\
            environment: development
            llm:
              model: x
              base_url: http://x
              max_tokens: 100
              temperature: 0.7
              timeout_seconds: 10
            tool_caller:
              max_retries: 1
              base_delay_seconds: 0.1
              max_delay_seconds: 1.0
              jitter_ratio: 0.1
              circuit_breaker:
                fail_max: 3
                reset_timeout_seconds: 30
            master:
              parallel_cuisines: 2
              stream_output: true
              cost_budget_tokens: 100
            memory:
              short_term:
                max_messages: 5
                summarize_after_tokens: 100
                keep_last_n_after_summary: 2
              long_term:
                sqlite_path: ./x.db
                decay_lambda: 0.01
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="master.*max_rounds"):
        loader.load_settings(p)


def test_load_settings_wrong_type_raises(tmp_path: Path) -> None:
    """max_tokens 是字符串而非 int → ConfigurationError."""
    p = tmp_path / "bad.yaml"
    p.write_text(
        dedent(
            """\
            environment: development
            llm:
              model: x
              base_url: http://x
              max_tokens: "not_a_number"
              temperature: 0.7
              timeout_seconds: 10
            tool_caller:
              max_retries: 1
              base_delay_seconds: 0.1
              max_delay_seconds: 1.0
              jitter_ratio: 0.1
              circuit_breaker:
                fail_max: 3
                reset_timeout_seconds: 30
            master:
              max_rounds: 5
              parallel_cuisines: 2
              stream_output: true
              cost_budget_tokens: 100
            memory:
              short_term:
                max_messages: 5
                summarize_after_tokens: 100
                keep_last_n_after_summary: 2
              long_term:
                sqlite_path: ./x.db
                decay_lambda: 0.01
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="llm.*max_tokens"):
        loader.load_settings(p)


def test_load_settings_file_not_found_raises(tmp_path: Path) -> None:
    """不存在的 yaml → ConfigurationError."""
    with pytest.raises(ConfigurationError, match="not found|not readable"):
        loader.load_settings(tmp_path / "nope.yaml")


def test_load_settings_malformed_yaml_raises(tmp_path: Path) -> None:
    """yaml 语法错 → ConfigurationError."""
    p = tmp_path / "bad.yaml"
    p.write_text("environment: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="yaml|YAML|parse"):
        loader.load_settings(p)


# =============================================================================
# get_setting() - 嵌套字段访问
# =============================================================================

def test_get_setting_nested_path(tmp_settings_yaml: Path) -> None:
    """'llm.max_tokens' 嵌套取值返回 int."""
    loader.load_settings(tmp_settings_yaml)
    assert loader.get_setting("llm.max_tokens") == 4096
    assert loader.get_setting("master.max_rounds") == 10
    assert loader.get_setting("short_term.max_messages") == 30


def test_get_setting_top_level(tmp_settings_yaml: Path) -> None:
    """顶层 key 也支持."""
    loader.load_settings(tmp_settings_yaml)
    assert loader.get_setting("environment") == "development"


def test_get_setting_missing_path_returns_default(tmp_settings_yaml: Path) -> None:
    """不存在的路径返回 default."""
    loader.load_settings(tmp_settings_yaml)
    assert loader.get_setting("nonexistent.path", default="fallback") == "fallback"
    assert loader.get_setting("llm.does_not_exist", default=42) == 42


def test_get_setting_auto_loads(tmp_settings_yaml: Path) -> None:
    """没显式 load_settings 时, get_setting 自动触发 load."""
    val = loader.get_setting("llm.model", default="default-model")
    assert val != "default-model"
    assert isinstance(val, str)
    assert len(val) > 0


# =============================================================================
# reload()
# =============================================================================

def test_reload_picks_up_changes(tmp_path: Path) -> None:
    """修改 yaml + reload() 后, 新值生效."""
    p = tmp_path / "settings.yaml"
    p.write_text(
        dedent(
            """\
            environment: development
            llm:
              model: orig
              base_url: http://x
              max_tokens: 100
              temperature: 0.7
              timeout_seconds: 10
            tool_caller:
              max_retries: 1
              base_delay_seconds: 0.1
              max_delay_seconds: 1.0
              jitter_ratio: 0.1
              circuit_breaker:
                fail_max: 3
                reset_timeout_seconds: 30
            master:
              max_rounds: 5
              parallel_cuisines: 2
              stream_output: true
              cost_budget_tokens: 100
            memory:
              short_term:
                max_messages: 5
                summarize_after_tokens: 100
                keep_last_n_after_summary: 2
              long_term:
                sqlite_path: ./x.db
                decay_lambda: 0.01
            """
        ),
        encoding="utf-8",
    )
    s1 = loader.load_settings(p)
    assert s1.llm.model == "orig"

    p.write_text(p.read_text(encoding="utf-8").replace("model: orig", "model: modified"))

    s2 = loader.load_settings(p)
    assert s2.llm.model == "orig"

    loader.reload()
    s3 = loader.load_settings(p)
    assert s3.llm.model == "modified"


# =============================================================================
# load_cuisines()
# =============================================================================

def test_load_cuisines_returns_list(tmp_cuisines_yaml: Path) -> None:
    """cuisines.yaml 加载返回 list[CuisineConfig]."""
    cuisines = loader.load_cuisines(tmp_cuisines_yaml)
    assert len(cuisines) == 3
    ids = [c.id for c in cuisines]
    assert ids == ["sichuan", "cantonese", "disabled_cuisine"]


def test_load_cuisines_fields(tmp_cuisines_yaml: Path) -> None:
    """CuisineConfig 字段正确填充."""
    cuisines = loader.load_cuisines(tmp_cuisines_yaml)
    sichuan = cuisines[0]
    assert sichuan.id == "sichuan"
    assert sichuan.name == "川菜"
    assert sichuan.category == "formal_cn"
    assert sichuan.prompt_file == "sichuan_v1.md"
    assert sichuan.knowledge_file == "sichuan.md"
    assert sichuan.enabled is True
    assert "辣" in sichuan.tags


def test_list_enabled_cuisines_filters_disabled(tmp_cuisines_yaml: Path) -> None:
    """list_enabled_cuisines() 过滤掉 enabled=false 的."""
    loader.load_cuisines(tmp_cuisines_yaml)
    enabled = loader.list_enabled_cuisines()
    assert len(enabled) == 2
    ids = [c.id for c in enabled]
    assert "disabled_cuisine" not in ids
    assert "sichuan" in ids
    assert "cantonese" in ids


def test_load_cuisines_duplicate_id_raises(tmp_path: Path) -> None:
    """重复的 id → ConfigurationError."""
    p = tmp_path / "bad.yaml"
    p.write_text(
        dedent(
            """\
            cuisines:
              - id: dup
                name: 菜 A
                category: x
                subcategory: x
                prompt_file: a.md
                knowledge_file: a.md
                enabled: true
                tags: []
              - id: dup
                name: 菜 B
                category: x
                subcategory: x
                prompt_file: b.md
                knowledge_file: b.md
                enabled: true
                tags: []
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="duplicate.*dup"):
        loader.load_cuisines(p)


def test_load_cuisines_missing_id_raises(tmp_path: Path) -> None:
    """缺 id 字段 → ConfigurationError."""
    p = tmp_path / "bad.yaml"
    p.write_text(
        dedent(
            """\
            cuisines:
              - name: 无 id 菜
                category: x
                subcategory: x
                prompt_file: a.md
                knowledge_file: a.md
                enabled: true
                tags: []
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="id|missing"):
        loader.load_cuisines(p)


def test_load_cuisines_default_path_has_14() -> None:
    """默认 cuisines.yaml 含 14 个菜系."""
    cuisines = loader.load_cuisines()
    assert len(cuisines) == 14
    enabled = [c for c in cuisines if c.enabled]
    assert len(enabled) == 14


# =============================================================================
# 不变性 (frozen)
# =============================================================================

def test_settings_is_frozen(tmp_settings_yaml: Path) -> None:
    """Settings 是 frozen, 改属性 → FrozenInstanceError."""
    s = loader.load_settings(tmp_settings_yaml)
    with pytest.raises(Exception):
        s.environment = "production"  # type: ignore[misc]


def test_cuisine_config_is_frozen(tmp_cuisines_yaml: Path) -> None:
    """CuisineConfig 是 frozen."""
    cuisines = loader.load_cuisines(tmp_cuisines_yaml)
    with pytest.raises(Exception):
        cuisines[0].enabled = False  # type: ignore[misc]
