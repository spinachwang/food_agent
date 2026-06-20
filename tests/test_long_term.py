"""测试 src/food_agent/memory/long_term.py (TDD).

Phase 2.6: 长期记忆 - SQLite + 偏好/推荐 + 关键词召回.

设计:
- 单 LongTermMemory 实例 = 单 sqlite3 connection
- schema.sql 启动时自动应用 (4 表: sessions / messages / user_preferences / recommendations)
- 置信度衰减: effective = stored * exp(-lambda * days_since_update)
- 召回: 简化版关键词匹配 (query 拆 substrings + 命中数 * effective_confidence)
- fail-soft: sqlite 错误不挂上层 (logger.warning + return)
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from food_agent.memory.long_term import LongTermMemory, Preference


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def ltm(tmp_path: Path):
    """临时 db, 测试后关闭."""
    db_path = tmp_path / "long_term_test.db"
    inst = LongTermMemory(db_path)
    yield inst
    inst.close()


# =============================================================================
# 生命周期
# =============================================================================

def test_creates_db_and_applies_schema(tmp_path: Path) -> None:
    """创建 db 时自动应用 schema (4 表)."""
    db = tmp_path / "fresh.db"
    assert not db.exists()
    inst = LongTermMemory(db)
    try:
        assert db.exists()
        # schema 应用: 4 张表都存在
        cur = inst._conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [r[0] for r in cur.fetchall()]
        assert "sessions" in tables
        assert "messages" in tables
        assert "user_preferences" in tables
        assert "recommendations" in tables
    finally:
        inst.close()


def test_close_then_reopen_persists(tmp_path: Path) -> None:
    """close 后重开 → 数据持久."""
    db = tmp_path / "persist.db"
    inst1 = LongTermMemory(db)
    inst1.save_preference("u1", "spicy", "不吃辣", 1.0)
    inst1.close()

    inst2 = LongTermMemory(db)
    try:
        prefs = inst2.get_preferences("u1")
        assert len(prefs) == 1
        assert prefs[0].key == "spicy"
    finally:
        inst2.close()


def test_context_manager(tmp_path: Path) -> None:
    """__enter__/__exit__ 可用."""
    db = tmp_path / "ctx.db"
    with LongTermMemory(db) as inst:
        inst.save_preference("u1", "k", "v", 1.0)
        prefs = inst.get_preferences("u1")
        assert len(prefs) == 1


# =============================================================================
# save_preference / get_preferences
# =============================================================================

def test_save_and_get_preference(ltm: LongTermMemory) -> None:
    """写入 + 读出."""
    ltm.save_preference("u1", "spicy", "不吃辣", 1.0)
    prefs = ltm.get_preferences("u1")
    assert len(prefs) == 1
    p = prefs[0]
    assert p.key == "spicy"
    assert p.value == "不吃辣"
    assert p.confidence == 1.0
    assert p.source == "explicit"


def test_save_preference_default_source(ltm: LongTermMemory) -> None:
    """source 默认 'explicit'."""
    ltm.save_preference("u1", "k", "v", 0.5)
    prefs = ltm.get_preferences("u1")
    assert prefs[0].source == "explicit"


def test_save_preference_upserts_on_same_key(ltm: LongTermMemory) -> None:
    """同 (user, key) 二次写入 → 覆盖 value, confidence 取 max."""
    ltm.save_preference("u1", "spicy", "不吃辣", 0.5)
    ltm.save_preference("u1", "spicy", "完全不碰", 0.8)
    prefs = ltm.get_preferences("u1")
    assert len(prefs) == 1
    assert prefs[0].value == "完全不碰"
    assert prefs[0].confidence == 0.8  # max(0.5, 0.8)


def test_save_preference_takes_max_confidence(ltm: LongTermMemory) -> None:
    """upsert 时 confidence 取 max(旧, 新)."""
    ltm.save_preference("u1", "k", "v1", 0.9)
    ltm.save_preference("u1", "k", "v2", 0.3)  # 较小
    prefs = ltm.get_preferences("u1")
    assert prefs[0].value == "v2"  # value 仍更新
    assert prefs[0].confidence == 0.9  # 但 confidence 保留更大的


def test_get_preferences_filters_by_user(ltm: LongTermMemory) -> None:
    """不同 user 的偏好互不串."""
    ltm.save_preference("alice", "k1", "v1", 1.0)
    ltm.save_preference("bob", "k2", "v2", 1.0)
    a = ltm.get_preferences("alice")
    b = ltm.get_preferences("bob")
    assert [p.key for p in a] == ["k1"]
    assert [p.key for p in b] == ["k2"]


def test_get_preferences_top_k(ltm: LongTermMemory) -> None:
    """top_k 截断."""
    for i in range(5):
        ltm.save_preference("u1", f"k{i}", f"v{i}", 1.0 - i * 0.1)
    prefs = ltm.get_preferences("u1", top_k=3)
    assert len(prefs) == 3


def test_get_preferences_min_confidence(ltm: LongTermMemory) -> None:
    """min_confidence 过滤掉低于阈值的 (考虑衰减后)."""
    ltm.save_preference("u1", "high", "v", 1.0)
    ltm.save_preference("u1", "low", "v", 0.05)
    prefs = ltm.get_preferences("u1", min_confidence=0.1)
    keys = [p.key for p in prefs]
    assert "high" in keys
    assert "low" not in keys  # 0.05 < 0.1


def test_get_preferences_empty_user(ltm: LongTermMemory) -> None:
    """不存在的 user → 空 list."""
    prefs = ltm.get_preferences("nonexistent")
    assert prefs == []


# =============================================================================
# 置信度衰减
# =============================================================================

def test_confidence_decay_with_mock_time(ltm: LongTermMemory, monkeypatch) -> None:
    """effective_confidence = stored * exp(-lambda * days)."""
    import math

    # 写一条偏好 (time.time = 1000)
    monkeypatch.setattr(time, "time", lambda: 1000.0)
    ltm.save_preference("u1", "k", "v", 1.0)

    # 现在 1000 + 70*86400 (70 天后), lambda=0.01
    monkeypatch.setattr(time, "time", lambda: 1000.0 + 70 * 86400)
    # 直接看 effective_confidence (从 get_preferences 走的是衰减后)
    # 但 get_preferences 返回 Preference.confidence (stored). 衰减只在 recall 时应用?
    # 设计: get_preferences 返回 stored (含原始 confidence),
    # 衰减在 recall_for_query 排序时使用.
    # 这里直接测内部衰减函数.
    eff = ltm._effective_confidence(stored=1.0, updated_at=1000.0, now=1000.0 + 70 * 86400)
    expected = math.exp(-0.01 * 70)
    assert abs(eff - expected) < 0.001


def test_recall_uses_decayed_confidence(ltm: LongTermMemory, monkeypatch) -> None:
    """recall 排序时用衰减后 confidence, 旧偏好排后."""
    ltm.save_preference("u1", "spicy", "不吃辣", 1.0)  # 0 秒前
    # 手动改 updated_at 让它变老
    cur = ltm._conn.cursor()
    cur.execute(
        "UPDATE user_preferences SET updated_at = ? WHERE key = ?",
        (1000.0, "spicy"),
    )
    ltm._conn.commit()
    # 此时再 recall, spicy 应该是衰减后的分数
    recalled = ltm.recall_for_query("u1", "我不吃辣", top_k=3)
    # spicy 仍能召回, 但分数低
    assert any(p.key == "spicy" for p in recalled)


# =============================================================================
# recall_for_query
# =============================================================================

def test_recall_returns_empty_when_no_match(ltm: LongTermMemory) -> None:
    """关键词无命中 → 返回空."""
    ltm.save_preference("u1", "spicy", "不吃辣", 1.0)
    recalled = ltm.recall_for_query("u1", "完全不相关", top_k=3)
    assert recalled == []


def test_recall_keyword_match(ltm: LongTermMemory) -> None:
    """关键词命中."""
    ltm.save_preference("u1", "spicy", "不吃辣", 1.0)
    ltm.save_preference("u1", "budget", "100 元以内", 1.0)
    recalled = ltm.recall_for_query("u1", "我不吃辣", top_k=2)
    keys = [p.key for p in recalled]
    assert "spicy" in keys
    assert "budget" not in keys  # 关键词不命中


def test_recall_sorted_by_score(ltm: LongTermMemory) -> None:
    """按 score (命中数 * effective_confidence) 降序."""
    ltm.save_preference("u1", "spicy_heavy", "辣味重, 辣度超辣", 1.0)  # 多次命中
    ltm.save_preference("u1", "spicy_light", "微辣", 1.0)  # 命中 1 次
    recalled = ltm.recall_for_query("u1", "我想吃辣的", top_k=2)
    # spicy_heavy 应该排第一 (命中更多)
    assert recalled[0].key == "spicy_heavy"


def test_recall_top_k_limits(ltm: LongTermMemory) -> None:
    """top_k 限制数量."""
    for i in range(5):
        ltm.save_preference("u1", f"辣{i}", f"辣味{i}", 1.0)
    recalled = ltm.recall_for_query("u1", "辣", top_k=3)
    assert len(recalled) <= 3


def test_recall_filters_unrelated_user(ltm: LongTermMemory) -> None:
    """recall 不串其他 user 的偏好."""
    ltm.save_preference("alice", "spicy", "不吃辣", 1.0)
    recalled = ltm.recall_for_query("bob", "辣", top_k=3)
    assert recalled == []


# =============================================================================
# record_recommendation
# =============================================================================

def test_record_recommendation_returns_id(ltm: LongTermMemory) -> None:
    """record_recommendation 返回 int id."""
    rid = ltm.record_recommendation(
        session_id="s1",
        user_msg="我想吃辣",
        result="陈麻婆豆腐",
    )
    assert isinstance(rid, int)
    assert rid > 0


def test_record_recommendation_stores_data(ltm: LongTermMemory) -> None:
    """写入的数据可读出 (直接 SQL 验证)."""
    rid = ltm.record_recommendation(
        session_id="s1",
        user_msg="我想吃辣",
        result="陈麻婆豆腐",
        cuisine_ids=["sichuan"],
        token_usage=150,
        latency_ms=1234,
    )
    cur = ltm._conn.cursor()
    cur.execute("SELECT * FROM recommendations WHERE id = ?", (rid,))
    row = cur.fetchone()
    assert row is not None
    # 列序: id, session_id, user_msg, result, tool_calls, cuisine_ids, token_usage, latency_ms, created_at
    assert row[1] == "s1"
    assert row[2] == "我想吃辣"
    assert row[3] == "陈麻婆豆腐"
    assert "sichuan" in row[5]  # cuisine_ids JSON
    assert row[6] == 150
    assert row[7] == 1234


def test_record_recommendation_optional_fields(ltm: LongTermMemory) -> None:
    """可选字段 (cuisine_ids / token_usage / latency_ms) 缺省 None."""
    rid = ltm.record_recommendation(
        session_id=None,
        user_msg="x",
        result="y",
    )
    cur = ltm._conn.cursor()
    cur.execute("SELECT session_id, cuisine_ids, token_usage FROM recommendations WHERE id = ?", (rid,))
    row = cur.fetchone()
    assert row[0] is None
    assert row[1] is None
    assert row[2] is None


# =============================================================================
# Fail-soft
# =============================================================================

def test_save_preference_fails_soft_on_sqlite_error(ltm: LongTermMemory, monkeypatch) -> None:
    """sqlite 错误不抛 — logger.warning + return."""

    class _FakeConn:
        def execute(self, *args, **kwargs):
            raise sqlite3.OperationalError("db locked")
        def close(self) -> None:
            pass
        def commit(self) -> None:
            pass
        def fetchall(self):
            return []
        def fetchone(self):
            return None

    monkeypatch.setattr(ltm, "_conn", _FakeConn())
    # 不抛
    ltm.save_preference("u1", "k", "v", 1.0)


def test_get_preferences_fails_soft_on_sqlite_error(ltm: LongTermMemory, monkeypatch) -> None:
    """get 失败 → 返回空 list."""

    class _FakeConn:
        def execute(self, *args, **kwargs):
            raise sqlite3.OperationalError("db locked")
        def close(self) -> None:
            pass
        def commit(self) -> None:
            pass

    monkeypatch.setattr(ltm, "_conn", _FakeConn())
    prefs = ltm.get_preferences("u1")
    assert prefs == []


# =============================================================================
# 防御式
# =============================================================================

def test_save_preference_validates_user_id(ltm: LongTermMemory) -> None:
    """user_id 空 → raise."""
    with pytest.raises(ValueError):
        ltm.save_preference("", "k", "v", 1.0)


def test_save_preference_validates_key(ltm: LongTermMemory) -> None:
    """key 空 → raise."""
    with pytest.raises(ValueError):
        ltm.save_preference("u1", "", "v", 1.0)


def test_save_preference_clamps_confidence(ltm: LongTermMemory) -> None:
    """confidence 越界 (负数 / >1) → clamp 到 [0, 1]."""
    ltm.save_preference("u1", "k1", "v1", -0.5)
    p = ltm.get_preferences("u1", min_confidence=0.0)[0]
    assert p.confidence == 0.0
    ltm.save_preference("u1", "k2", "v2", 5.0)
    p = ltm.get_preferences("u1", min_confidence=0.0)
    assert {pp.key: pp.confidence for pp in p}["k2"] == 1.0


# =============================================================================
# FoodAgent 集成
# =============================================================================

class FakeLLM:
    """测试用 mock LLM, 暴露 last_messages."""

    def __init__(self, canned_responses: list[str]) -> None:
        self.canned_responses = canned_responses
        self.model = "fake"
        self.model_type = "fake"
        self.generate_cfg: dict = {}
        self.max_retries = 0
        self.cache = None
        self.use_raw_api = False
        self.call_count = 0
        self.last_messages: list = []

    def chat(self, messages, functions=None, stream=True, **kwargs):
        self.call_count += 1
        self.last_messages = list(messages)
        from qwen_agent.llm.schema import Message as QMessage

        def _gen():
            resp = self.canned_responses[(self.call_count - 1) % len(self.canned_responses)]
            yield [QMessage(role="assistant", content=resp)]
        return _gen()


def test_foodagent_recall_injects_prefs_to_messages(tmp_path) -> None:
    """long_term 存在时, FoodAgent.run 把偏好召回注入到 messages (作为 system msg)."""
    from food_agent.master import FoodAgent
    from food_agent.memory.long_term import LongTermMemory

    db = tmp_path / "ltm.db"
    with LongTermMemory(db) as ltm:
        ltm.save_preference("u1", "spicy", "不吃辣", 0.9)
        fake = FakeLLM(["推荐川菜"])
        agent = FoodAgent(llm=fake, long_term=ltm)  # type: ignore[arg-type]
        agent.run("我不吃辣, 想知道还有啥", user_id="u1")

        # 验证: 召回的偏好应出现在发送给 LLM 的消息里
        combined = " ".join(str(m) for m in fake.last_messages)
        assert "不吃辣" in combined


def test_foodagent_no_long_term_works(tmp_path) -> None:
    """不传 long_term 时仍能跑通 (Phase 1 兼容)."""
    from food_agent.master import FoodAgent

    fake = FakeLLM(["ok"])
    agent = FoodAgent(llm=fake)  # type: ignore[arg-type]
    result = agent.run("hello", user_id="u1")
    assert "ok" in result


def test_foodagent_writes_recommendation_to_long_term(tmp_path) -> None:
    """FoodAgent.run 完后, record_recommendation 自动写入 long_term."""
    from food_agent.master import FoodAgent
    from food_agent.memory.long_term import LongTermMemory

    db = tmp_path / "ltm.db"
    with LongTermMemory(db) as ltm:
        fake = FakeLLM(["推荐陈麻婆"])
        agent = FoodAgent(llm=fake, long_term=ltm)  # type: ignore[arg-type]
        agent.run("我想吃川菜", user_id="u1", session_id="s1")

        # 验证: recommendations 表有 1 条
        cur = ltm._conn.execute("SELECT COUNT(*) FROM recommendations")
        count = cur.fetchone()[0]
        assert count == 1

        cur = ltm._conn.execute(
            "SELECT user_msg, result, session_id FROM recommendations"
        )
        row = cur.fetchone()
        assert row[0] == "我想吃川菜"
        assert row[1] == "推荐陈麻婆"
        assert row[2] == "s1"


def test_foodagent_long_term_failure_fails_soft(tmp_path) -> None:
    """long_term 操作失败不挂上层."""
    from food_agent.master import FoodAgent
    from food_agent.memory.long_term import LongTermMemory

    db = tmp_path / "ltm.db"
    ltm = LongTermMemory(db)
    ltm.close()  # 关闭后所有操作 fail-soft

    fake = FakeLLM(["ok"])
    agent = FoodAgent(llm=fake, long_term=ltm)  # type: ignore[arg-type]
    # 不抛
    result = agent.run("test", user_id="u1")
    assert "ok" in result


def test_foodagent_recall_uses_user_id(tmp_path) -> None:
    """recall_for_query 用 user_id 隔离不同用户."""
    from food_agent.master import FoodAgent
    from food_agent.memory.long_term import LongTermMemory

    db = tmp_path / "ltm.db"
    with LongTermMemory(db) as ltm:
        ltm.save_preference("alice", "spicy", "不吃辣", 1.0)
        # bob 没有偏好
        fake = FakeLLM(["r1"])
        agent = FoodAgent(llm=fake, long_term=ltm)  # type: ignore[arg-type]
        agent.run("我不吃辣", user_id="bob")
        combined = " ".join(str(m) for m in fake.last_messages)
        # bob 没有偏好, "用户偏好" 这段不应出现
        # (master prompt 里不含 "用户偏好" 这字符串, 用它作 marker)
        assert "用户偏好" not in combined


# =============================================================================
# Phase B: master.run 自动 save_preference
# =============================================================================

def test_foodagent_auto_saves_sweet_preference(tmp_path) -> None:
    """run() 说完 '我不喜欢甜的' 后, long_term 自动写 avoid_甜."""
    from food_agent.master import FoodAgent
    from food_agent.memory.long_term import LongTermMemory

    db = tmp_path / "ltm.db"
    with LongTermMemory(db) as ltm:
        agent = FoodAgent(llm=FakeLLM(["ok"]), long_term=ltm)  # type: ignore[arg-type]
        agent.run("我不喜欢甜的", user_id="alice")

        prefs = ltm.get_preferences("alice")
        assert any(p.key == "avoid_甜" and p.confidence == 0.7 for p in prefs), \
            f"expected avoid_甜, got {[(p.key, p.value, p.confidence) for p in prefs]}"


def test_foodagent_auto_saves_allergy(tmp_path) -> None:
    """run() 说完 '我对花生过敏' 后, long_term 自动写 allergy_花生."""
    from food_agent.master import FoodAgent
    from food_agent.memory.long_term import LongTermMemory

    db = tmp_path / "ltm.db"
    with LongTermMemory(db) as ltm:
        agent = FoodAgent(llm=FakeLLM(["ok"]), long_term=ltm)  # type: ignore[arg-type]
        agent.run("我对花生过敏", user_id="bob")

        prefs = ltm.get_preferences("bob")
        assert any(p.key == "allergy_花生" and p.confidence == 0.9 for p in prefs), \
            f"expected allergy_花生, got {[(p.key, p.value, p.confidence) for p in prefs]}"


def test_foodagent_second_run_recalls_saved_preference(tmp_path) -> None:
    """端到端: 第一轮说偏好 → 第二轮 (有关键词 query) 召回注入 messages.

    注: recall_for_query 用 keyword substring 匹配, 跨无关联 query 召回
    要 Phase C 的 embedding 升级, 这里只验证链路本身.
    """
    from food_agent.master import FoodAgent
    from food_agent.memory.long_term import LongTermMemory

    db = tmp_path / "ltm.db"
    with LongTermMemory(db) as ltm:
        fake = FakeLLM(["r1", "r2"])
        agent = FoodAgent(llm=fake, long_term=ltm)  # type: ignore[arg-type]
        # 第一轮: save 偏好
        agent.run("我不喜欢甜的", user_id="carol")
        # 第二轮: 含 "甜" 的 query, 应能召回
        agent.run("别给我推荐甜的", user_id="carol")
        combined = " ".join(str(m) for m in fake.last_messages)
        assert "甜" in combined
        assert "用户偏好" in combined


def test_foodagent_auto_save_fails_soft_on_long_term_error(tmp_path) -> None:
    """long_term 关闭/出错时, auto_save 不挂上层."""
    from food_agent.master import FoodAgent
    from food_agent.memory.long_term import LongTermMemory

    db = tmp_path / "ltm.db"
    ltm = LongTermMemory(db)
    ltm.close()  # 关闭后所有 sqlite 操作都报错

    fake = FakeLLM(["ok"])
    agent = FoodAgent(llm=fake, long_term=ltm)  # type: ignore[arg-type]
    # 不抛
    result = agent.run("我对花生过敏", user_id="dave")
    assert "ok" in result
