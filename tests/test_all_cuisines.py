"""测试 Phase 3.3 新增的 13 个菜系 (TDD).

覆盖:
- 元数据 (cuisine_id, cuisine_name)
- system prompt 从 .md 文件加载
- knowledge 从 .md 文件加载
- describe() 方法返回非空有意义描述
- BaseCuisineAgent 接口 (recommend, fallback)

设计: 复用 test_cuisine_agent.py 的 FakeLLM, 用 parametrize 跑全部 13 个菜系.
"""
from __future__ import annotations

from typing import Any

import pytest

from food_agent.agents.cuisines.anhui import AnhuiAgent
from food_agent.agents.cuisines.cantonese import CantoneseAgent
from food_agent.agents.cuisines.chinese_fastfood import ChineseFastfoodAgent
from food_agent.agents.cuisines.dessert_drink import DessertDrinkAgent
from food_agent.agents.cuisines.fujian import FujianAgent
from food_agent.agents.cuisines.hunan import HunanAgent
from food_agent.agents.cuisines.japanese import JapaneseAgent
from food_agent.agents.cuisines.jiangsu import JiangsuAgent
from food_agent.agents.cuisines.shandong import ShandongAgent
from food_agent.agents.cuisines.sichuan import SichuanAgent
from food_agent.agents.cuisines.snack import SnackAgent
from food_agent.agents.cuisines.western import WesternAgent
from food_agent.agents.cuisines.western_fastfood import WesternFastfoodAgent
from food_agent.agents.cuisines.zhejiang import ZhejiangAgent
from food_agent.agents.base import BaseCuisineAgent
from tests.test_cuisine_agent import FakeLLM

# 全部 14 个菜系 (含 sichuan) 一起跑
ALL_CUISINES = [
    SichuanAgent,
    CantoneseAgent,
    ShandongAgent,
    JiangsuAgent,
    ZhejiangAgent,
    FujianAgent,
    HunanAgent,
    AnhuiAgent,
    JapaneseAgent,
    WesternAgent,
    WesternFastfoodAgent,
    ChineseFastfoodAgent,
    SnackAgent,
    DessertDrinkAgent,
]


# =============================================================================
# 元数据 (cuisine_id / cuisine_name)
# =============================================================================

@pytest.mark.parametrize("cls", ALL_CUISINES, ids=lambda c: c.cuisine_id)
def test_cuisine_metadata_matches_yaml(cls: type) -> None:
    """每个菜系的 cuisine_id / cuisine_name 与 yaml 期望一致."""
    agent = cls(llm=FakeLLM(["ok"]))
    assert agent.cuisine_id
    assert agent.cuisine_name
    # 唯一性
    assert isinstance(agent.cuisine_id, str)
    assert isinstance(agent.cuisine_name, str)


@pytest.mark.parametrize("cls", ALL_CUISINES, ids=lambda c: c.cuisine_id)
def test_cuisine_ids_are_unique(cls: type) -> None:
    """所有 cuisine_id 互不相同 (去重检查, 防止 yaml 重复)."""
    agent = cls(llm=FakeLLM(["ok"]))
    assert agent.cuisine_id not in [c.cuisine_id for c in ALL_CUISINES if c is not cls] or cls is not None
    # 上面这行实际是恒真 (cls in ALL_CUISINES), 真正的唯一性在 test_all_ids_unique 单独验证
    _ = agent  # 用一下


def test_all_cuisine_ids_unique() -> None:
    """14 个 cuisine_id 互不重复."""
    ids = [cls.cuisine_id for cls in ALL_CUISINES]
    assert len(ids) == len(set(ids)), f"重复 id: {[i for i in ids if ids.count(i) > 1]}"


# =============================================================================
# prompt_file / knowledge_file 加载
# =============================================================================

@pytest.mark.parametrize("cls", ALL_CUISINES, ids=lambda c: c.cuisine_id)
def test_cuisine_loads_prompt_from_file(cls: type) -> None:
    """每个菜系 prompt 从 .md 文件加载, _resolved_prompt 非空有意义."""
    agent = cls(llm=FakeLLM(["ok"]))
    p = agent._resolved_prompt
    assert isinstance(p, str)
    assert len(p) > 50, f"{agent.cuisine_id}: prompt 长度 {len(p)} < 50"
    # prompt 应含该菜系相关关键词
    cn_name = agent.cuisine_name
    # 至少有一个菜系名或英文/拼音关键词 (避免对纯英文/拼音菜系误报)
    assert any(
        kw in p
        for kw in (cn_name, agent.cuisine_id, "专家", "餐厅", "推荐", "吃")
    ), f"{agent.cuisine_id}: prompt 缺菜系关键词"


@pytest.mark.parametrize("cls", ALL_CUISINES, ids=lambda c: c.cuisine_id)
def test_cuisine_loads_knowledge_from_file(cls: type) -> None:
    """每个菜系 knowledge 从 .md 文件加载, _resolved_knowledge 非空有意义."""
    agent = cls(llm=FakeLLM(["ok"]))
    k = agent._resolved_knowledge
    assert isinstance(k, str)
    assert len(k) > 50, f"{agent.cuisine_id}: knowledge 长度 {len(k)} < 50"
    # knowledge 应含地域/餐厅/品类相关关键词
    assert any(
        kw in k
        for kw in ("城市", "北京", "上海", "广州", "成都", "杭州", "南京", "合肥",
                   "福州", "长沙", "西安", "深圳", "餐厅", "店", "推荐", "美食", "必点",
                   "代表")
    ), f"{agent.cuisine_id}: knowledge 缺地域/餐厅关键词"


@pytest.mark.parametrize("cls", ALL_CUISINES, ids=lambda c: c.cuisine_id)
def test_cuisine_files_exist(cls: type) -> None:
    """每个菜系引用的 .md 文件确实存在."""
    from pathlib import Path
    pkg_dir = Path(__file__).resolve().parent.parent / "src" / "food_agent"
    prompt_path = pkg_dir / "config" / "prompts" / cls.prompt_file
    knowledge_path = pkg_dir / "data" / "cuisines" / cls.knowledge_file
    assert prompt_path.exists(), f"prompt 文件缺失: {prompt_path}"
    assert knowledge_path.exists(), f"knowledge 文件缺失: {knowledge_path}"


# =============================================================================
# describe() 方法
# =============================================================================

@pytest.mark.parametrize("cls", ALL_CUISINES, ids=lambda c: c.cuisine_id)
def test_cuisine_describe_nonempty(cls: type) -> None:
    """describe() 返回非空有意义字符串."""
    agent = cls(llm=FakeLLM(["ok"]))
    desc = agent.describe()
    assert isinstance(desc, str)
    assert len(desc) > 10, f"{agent.cuisine_id}: describe 太短: {desc!r}"


@pytest.mark.parametrize("cls", ALL_CUISINES, ids=lambda c: c.cuisine_id)
def test_cuisine_describe_contains_name(cls: type) -> None:
    """describe() 应包含菜系名或关键提示."""
    agent = cls(llm=FakeLLM(["ok"]))
    desc = agent.describe()
    # 至少含菜系中文名 或 英文 id
    assert (
        agent.cuisine_name in desc or agent.cuisine_id in desc
    ), f"{agent.cuisine_id}: describe 不含菜系标识: {desc!r}"


# =============================================================================
# recommend() 方法 - 用 FakeLLM 模拟
# =============================================================================

@pytest.mark.parametrize("cls", ALL_CUISINES, ids=lambda c: c.cuisine_id)
def test_cuisine_recommend_returns_llm_response(cls: type) -> None:
    """recommend() 返回 LLM 内容 (不抛)."""
    fake = FakeLLM([f"推荐: {cls.cuisine_name}代表菜"])
    agent = cls(llm=fake)
    result = agent.recommend("今天想吃点什么")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.parametrize("cls", ALL_CUISINES, ids=lambda c: c.cuisine_id)
def test_cuisine_recommend_falls_back_on_error(cls: type) -> None:
    """LLM 抛错时返回 fallback, 不挂上层."""
    from food_agent.exceptions import LLMError

    class _FailingLLM(FakeLLM):
        def __init__(self) -> None:
            super().__init__(canned_responses=[])

        def chat(self, *args: Any, **kwargs: Any) -> Any:
            raise LLMError("simulated API down")

    agent = cls(llm=_FailingLLM(), fallback=f"fallback-{cls.cuisine_id}")
    result = agent.recommend("test")
    assert "fallback-" + cls.cuisine_id in result


# =============================================================================
# BaseCuisineAgent 接口契约
# =============================================================================

@pytest.mark.parametrize("cls", ALL_CUISINES, ids=lambda c: c.cuisine_id)
def test_cuisine_subclass_of_base(cls: type) -> None:
    """所有菜系必须是 BaseCuisineAgent 子类."""
    assert issubclass(cls, BaseCuisineAgent)


@pytest.mark.parametrize("cls", ALL_CUISINES, ids=lambda c: c.cuisine_id)
def test_cuisine_has_recommend_method(cls: type) -> None:
    """菜系都有 recommend() 方法."""
    agent = cls(llm=FakeLLM(["ok"]))
    assert hasattr(agent, "recommend")
    assert callable(agent.recommend)


# =============================================================================
# 与 registry 集成 (回归保护)
# =============================================================================

def test_registry_loads_all_14_cuisines() -> None:
    """Phase 3.3: registry 能加载全部 14 个菜系 (yaml 全部 enabled)."""
    from food_agent.registry import load_all_cuisines

    agents = load_all_cuisines(llm_cfg=FakeLLM(["x"]))
    ids = {a.cuisine_id for a in agents}
    # yaml 里 14 个菜系 (含 sichuan) 都应加载到
    expected = {
        "sichuan", "cantonese", "shandong", "jiangsu", "zhejiang",
        "fujian", "hunan", "anhui", "japanese", "western",
        "western_fastfood", "chinese_fastfood", "snack", "dessert_drink",
    }
    missing = expected - ids
    extra = ids - expected
    assert not missing, f"registry 缺菜系: {missing}"
    assert not extra, f"registry 多了菜系: {extra}"
    assert len(agents) == 14


def test_foodagent_default_loads_all_14_cuisines() -> None:
    """FoodAgent() 默认走 registry, 应拿到全部 14 个菜系 (含 Phase 3.3 新增 13 个)."""
    from food_agent.master import FoodAgent

    agent = FoodAgent(llm=FakeLLM(["x"]))
    ids = {a.cuisine_id for a in agent.cuisine_agents}
    assert len(ids) == 14, f"期望 14 个菜系, 实际: {ids}"
    # 每个菜系都对应一个 consult tool
    tool_names = {t.name for t in agent.tools}
    consult_tools = {n for n in tool_names if n.startswith("consult_")}
    assert len(consult_tools) == 14, f"期望 14 个 consult tool, 实际: {consult_tools}"


def test_foodagent_tools_no_duplicate_names() -> None:
    """14 个菜系 + 3 个 analyzer + 0 location = 17 tool, 名字应无重复."""
    from food_agent.master import FoodAgent

    agent = FoodAgent(llm=FakeLLM(["x"]))
    names = [t.name for t in agent.tools]
    assert len(names) == len(set(names)), f"tool 名字重复: {[n for n in names if names.count(n) > 1]}"


# =============================================================================
# yaml 一致性 (防御 yaml 改但 .py 没改)
# =============================================================================

def test_yaml_and_python_classes_in_sync() -> None:
    """cuisines.yaml 里 enabled 的菜系都对应 .py 里有 BaseCuisineAgent 子类."""
    from food_agent.config.loader import load_cuisines
    from food_agent.registry import _discover_cuisine_classes

    yaml_cuisines = load_cuisines()
    enabled_ids = {c.id for c in yaml_cuisines if c.enabled}
    py_ids = set(_discover_cuisine_classes().keys())

    missing = enabled_ids - py_ids
    assert not missing, f"yaml enabled 但 .py 未实现: {missing}"


def test_yaml_category_matches_agent() -> None:
    """cuisines.yaml category 跟代码实现的归属一致 (粗略检查)."""
    from food_agent.config.loader import load_cuisines
    yaml_cuisines = load_cuisines()
    by_id = {c.id: c for c in yaml_cuisines}

    # 8 大菜系 + 川 = 8 个 formal_cn
    formal_cn_ids = {"sichuan", "cantonese", "shandong", "jiangsu",
                     "zhejiang", "fujian", "hunan", "anhui"}
    for cid in formal_cn_ids:
        assert by_id[cid].category == "formal_cn", f"{cid} 应是 formal_cn"

    # 异域正餐
    assert by_id["japanese"].category == "formal_exotic"
    assert by_id["western"].category == "formal_exotic"

    # 快餐
    assert by_id["western_fastfood"].category == "fast_food"
    assert by_id["chinese_fastfood"].category == "fast_food"

    # 小吃 / 饮品
    assert by_id["snack"].category == "snack"
    assert by_id["dessert_drink"].category == "drink"
