"""测试 src/food_agent/registry.py (TDD).

Phase 2.2: 从 cuisines.yaml + 扫描 cuisines 包动态加载菜系.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from textwrap import dedent
from types import ModuleType
from typing import Any

import pytest

from food_agent.agents.base import BaseCuisineAgent
from food_agent.config import loader as config_loader
from food_agent.exceptions import ConfigurationError
from food_agent.registry import load_all_cuisines


# =============================================================================
# Fake LLM
# =============================================================================

class FakeLLM:
    """测试用 mock LLM (与 test_cuisine_agent.py 一致)."""

    def __init__(self, canned_responses: list[str]) -> None:
        self.canned_responses = canned_responses
        self.model = "fake"
        self.model_type = "fake"
        self.generate_cfg: dict = {}
        self.max_retries = 0
        self.cache = None
        self.use_raw_api = False
        self.call_count = 0

    def chat(self, messages, functions=None, stream=True, **kwargs):
        self.call_count += 1
        from qwen_agent.llm.schema import Message as QMessage

        def _gen():
            resp = self.canned_responses[(self.call_count - 1) % len(self.canned_responses)]
            yield [QMessage(role="assistant", content=resp)]
        return _gen()


# =============================================================================
# Fake 菜系类 (定义在 tests 文件, 通过 sys.modules 动态注入 cuisines 包)
# =============================================================================

class FakeCuisineA(BaseCuisineAgent):
    cuisine_id = "fake_a"
    cuisine_name = "Fake A"
    system_prompt = "fake A prompt"

    def describe(self) -> str:
        return "fake A"


class FakeCuisineB(BaseCuisineAgent):
    cuisine_id = "fake_b"
    cuisine_name = "Fake B"
    system_prompt = "fake B prompt"

    def describe(self) -> str:
        return "fake B"


class DisabledFakeCuisine(BaseCuisineAgent):
    cuisine_id = "disabled_fake"
    cuisine_name = "Disabled Fake"
    system_prompt = "x"

    def describe(self) -> str:
        return "x"


FAKE_CLASSES = [FakeCuisineA, FakeCuisineB, DisabledFakeCuisine]


def _add_fake_submodule(cls: type, monkeypatch) -> str:
    """动态创建 food_agent.agents.cuisines.<id> 子模块, 含 cls."""
    mod_name = f"food_agent.agents.cuisines.{cls.cuisine_id}"
    mod = ModuleType(mod_name)
    mod.__file__ = "(synthetic)"
    setattr(mod, cls.__name__, cls)
    monkeypatch.setitem(sys.modules, mod_name, mod)
    return mod_name


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def tmp_cuisines_yaml(tmp_path: Path) -> Path:
    """只含 fake_a, fake_b (enabled) + disabled_fake."""
    p = tmp_path / "cuisines.yaml"
    p.write_text(
        dedent(
            """\
            cuisines:
              - id: fake_a
                name: Fake A
                category: test
                subcategory: a
                prompt_file: fake_a_v1.md
                knowledge_file: fake_a.md
                enabled: true
                tags: [test]

              - id: fake_b
                name: Fake B
                category: test
                subcategory: b
                prompt_file: fake_b_v1.md
                knowledge_file: fake_b.md
                enabled: true
                tags: [test]

              - id: disabled_fake
                name: Disabled Fake
                category: test
                subcategory: d
                prompt_file: d_v1.md
                knowledge_file: d.md
                enabled: false
                tags: [test]
            """
        ),
        encoding="utf-8",
    )
    return p


@pytest.fixture(autouse=True)
def _setup_fake_cuisines(monkeypatch):
    """每个测试: 注入 fake 子模块, 测试后清理."""
    config_loader.reload()
    fake_mods = [_add_fake_submodule(cls, monkeypatch) for cls in FAKE_CLASSES]
    yield
    for mod_name in fake_mods:
        sys.modules.pop(mod_name, None)
    config_loader.reload()


# =============================================================================
# load_all_cuisines() - 基本功能
# =============================================================================

def test_load_all_cuisines_returns_agents_for_enabled(tmp_cuisines_yaml: Path) -> None:
    """返回所有 enabled=true 的 agent 实例."""
    agents = load_all_cuisines(
        llm_cfg=FakeLLM(["x"]),
        cuisines_yaml_path=tmp_cuisines_yaml,
    )
    ids = [a.cuisine_id for a in agents]
    assert "fake_a" in ids
    assert "fake_b" in ids
    assert "disabled_fake" not in ids
    assert len(agents) == 2


def test_load_all_cuisines_instances_are_cuisine_agents(tmp_cuisines_yaml: Path) -> None:
    """返回的是 BaseCuisineAgent 实例."""
    agents = load_all_cuisines(
        llm_cfg=FakeLLM(["x"]),
        cuisines_yaml_path=tmp_cuisines_yaml,
    )
    for a in agents:
        assert isinstance(a, BaseCuisineAgent)


def test_load_all_cuisines_passes_fallback(tmp_cuisines_yaml: Path) -> None:
    """fallback_text 透传给每个 agent."""
    agents = load_all_cuisines(
        llm_cfg=FakeLLM(["x"]),
        cuisines_yaml_path=tmp_cuisines_yaml,
        fallback_text="通用降级",
    )
    for a in agents:
        assert a._fallback == "通用降级"


def test_load_all_cuisines_preserves_yaml_order(tmp_cuisines_yaml: Path) -> None:
    """agents 顺序与 yaml 一致."""
    agents = load_all_cuisines(
        llm_cfg=FakeLLM(["x"]),
        cuisines_yaml_path=tmp_cuisines_yaml,
    )
    ids = [a.cuisine_id for a in agents]
    assert ids == ["fake_a", "fake_b"]


# =============================================================================
# 失败模式
# =============================================================================

def test_load_all_cuisines_missing_implementation_raises(tmp_path: Path) -> None:
    """yaml 里有但没实现 + strict=True → ConfigurationError."""
    p = tmp_path / "cuisines.yaml"
    p.write_text(
        dedent(
            """\
            cuisines:
              - id: not_implemented
                name: Not Implemented
                category: test
                subcategory: x
                prompt_file: x_v1.md
                knowledge_file: x.md
                enabled: true
                tags: []
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="not_implemented|未实现"):
        load_all_cuisines(
            llm_cfg=FakeLLM(["x"]),
            cuisines_yaml_path=p,
            strict=True,
        )


def test_load_all_cuisines_skips_unimplemented_by_default(tmp_path: Path) -> None:
    """strict=False (默认): 跳过未实现菜系, 不抛异常."""
    # fake_a 由 autouse fixture _setup_fake_cuisines 注入到 sys.modules
    p = tmp_path / "cuisines.yaml"
    p.write_text(
        dedent(
            """\
            cuisines:
              - id: fake_a
                name: Fake A
                category: test
                subcategory: x
                prompt_file: x_v1.md
                knowledge_file: x.md
                enabled: true
                tags: []
              - id: not_implemented
                name: Not Implemented
                category: test
                subcategory: x
                prompt_file: x_v1.md
                knowledge_file: x.md
                enabled: true
                tags: []
            """
        ),
        encoding="utf-8",
    )
    agents = load_all_cuisines(
        llm_cfg=FakeLLM(["x"]),
        cuisines_yaml_path=p,
        # strict 不传, 默认 False
    )
    assert [a.cuisine_id for a in agents] == ["fake_a"]


def test_load_all_cuisines_yaml_not_found_raises(tmp_path: Path) -> None:
    """yaml 路径不存在 → ConfigurationError."""
    with pytest.raises(ConfigurationError, match="not found"):
        load_all_cuisines(
            llm_cfg=FakeLLM(["x"]),
            cuisines_yaml_path=tmp_path / "nope.yaml",
        )


# =============================================================================
# 与 FoodAgent 集成 (回归保护)
# =============================================================================

def test_foodagent_default_cuisines_uses_registry() -> None:
    """FoodAgent() 默认构造走 registry, 仍能拿到 SichuanAgent."""
    from food_agent.agents.cuisines.sichuan import SichuanAgent
    from food_agent.master import FoodAgent

    # 默认 cuisines.yaml 含 14 个菜系但只实现了 sichuan,
    # 所以要 monkeypatch: 加一个临时 yaml 让 registry 顺利返回
    # 这里用最简的: 只放 sichuan
    from food_agent.config import loader as cfg
    cfg.reload()
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        f.write("cuisines:\n  - id: sichuan\n    name: 川菜\n    category: formal_cn\n    subcategory: s\n    prompt_file: x\n    knowledge_file: x\n    enabled: true\n    tags: []\n")
        tmp_yaml = f.name
    try:
        # 临时把默认 yaml 路径覆盖
        from food_agent import registry
        original_func = registry.load_all_cuisines
        registry.load_all_cuisines = lambda **kw: original_func(
            llm_cfg=kw.get("llm_cfg"),
            fallback_text=kw.get("fallback_text"),
            cuisines_yaml_path=tmp_yaml,
        )
        agent = FoodAgent(llm=FakeLLM(["x"]))
        ids = [a.cuisine_id for a in agent.cuisine_agents]
        assert "sichuan" in ids
        assert any(isinstance(a, SichuanAgent) for a in agent.cuisine_agents)
        registry.load_all_cuisines = original_func
    finally:
        Path(tmp_yaml).unlink(missing_ok=True)
        cfg.reload()


def test_foodagent_with_custom_cuisines_unchanged() -> None:
    """显式传 cuisine_agents 时不走 registry."""
    from food_agent.agents.cuisines.sichuan import SichuanAgent
    from food_agent.master import FoodAgent

    custom = SichuanAgent(llm=FakeLLM(["x"]))
    agent = FoodAgent(llm=FakeLLM(["x"]), cuisine_agents=[custom])
    assert agent.cuisine_agents == [custom]
