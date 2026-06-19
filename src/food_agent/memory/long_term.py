"""长期记忆: SQLite 持久化用户偏好 / 推荐历史 / 消息.

Phase 2.6.

设计:
- schema.sql 启动时自动应用 (4 表: sessions / messages /
  user_preferences / recommendations)
- 置信度衰减: effective = stored * exp(-lambda * days_since_update)
- 召回: 简化版关键词匹配 (query 拆 substrings + 命中数 * effective_confidence)
- fail-soft: sqlite 错误 logger.warning + return, 不挂上层
- 单 LongTermMemory 实例 = 单 sqlite3 connection

不引入 FTS5 / embedding — 留给 Phase 3.
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def _apply_schema(conn: sqlite3.Connection) -> None:
    """读 schema.sql 用 executescript 一次性应用 (含索引和约束)."""
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(sql)


@dataclass(frozen=True)
class Preference:
    """用户偏好条目 (来自 user_preferences 表)."""
    key: str
    value: str
    confidence: float
    source: str
    updated_at: float


class LongTermMemory:
    """长期记忆主类.

    用法:
        >>> ltm = LongTermMemory("./data/food_agent.db")
        >>> ltm.save_preference("alice", "spicy", "不吃辣", confidence=0.9)
        >>> prefs = ltm.recall_for_query("alice", "我不吃辣")
        >>> ltm.close()

    或 with 语句:
        >>> with LongTermMemory(db_path) as ltm:
        ...     ltm.save_preference(...)
    """

    def __init__(
        self,
        db_path: Path | str,
        decay_lambda: float = 0.01,
    ) -> None:
        """打开/创建 db, 应用 schema.

        Args:
            db_path: SQLite 文件路径. 父目录必须存在.
            decay_lambda: 置信度衰减系数. 0.01 ≈ 70 天衰减到 1/e.
        """
        self._db_path = Path(db_path)
        self._decay_lambda = decay_lambda
        # isolation_level=None: autocommit 模式 (我们显式管理事务)
        self._conn = sqlite3.connect(str(self._db_path), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        _apply_schema(self._conn)

    def close(self) -> None:
        """关闭 db connection."""
        try:
            self._conn.close()
        except Exception as e:
            logger.warning("close failed: %s", e)

    def __enter__(self) -> "LongTermMemory":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # =================================================================
    # 偏好
    # =================================================================

    def save_preference(
        self,
        user_id: str,
        key: str,
        value: str,
        confidence: float = 1.0,
        source: str = "explicit",
    ) -> None:
        """保存/更新用户偏好.

        - 同 (user_id, key) 二次写入 → upsert
        - confidence 取 max(旧, 新) (高置信度不衰减)
        - value 总是被新值覆盖
        - 越界 confidence → clamp 到 [0, 1]

        Args:
            user_id: 用户 ID (非空).
            key: 偏好 key (非空).
            value: 偏好 value.
            confidence: 置信度, 默认 1.0.
            source: 来源标记 ("explicit" / "inferred" / ...), 默认 "explicit".

        Raises:
            ValueError: user_id 或 key 为空.
        """
        if not user_id:
            raise ValueError("user_id required")
        if not key:
            raise ValueError("key required")
        confidence = max(0.0, min(1.0, float(confidence)))
        now = time.time()

        try:
            cur = self._conn.execute(
                "SELECT confidence FROM user_preferences WHERE user_id = ? AND key = ?",
                (user_id, key),
            )
            row = cur.fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO user_preferences "
                    "(user_id, key, value, confidence, source, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (user_id, key, value, confidence, source, now, now),
                )
            else:
                new_conf = max(row["confidence"], confidence)
                self._conn.execute(
                    "UPDATE user_preferences "
                    "SET value = ?, confidence = ?, source = ?, updated_at = ? "
                    "WHERE user_id = ? AND key = ?",
                    (value, new_conf, source, now, user_id, key),
                )
        except sqlite3.Error as e:
            logger.warning("save_preference failed: %s", e)

    def get_preferences(
        self,
        user_id: str,
        top_k: int | None = None,
        min_confidence: float = 0.1,
    ) -> list[Preference]:
        """获取用户偏好 (按 confidence DESC, updated_at DESC).

        Args:
            user_id: 用户 ID.
            top_k: 限制返回条数. None = 全部.
            min_confidence: 最低 confidence 阈值.

        Returns:
            Preference 列表. 失败/无 → [].
        """
        try:
            cur = self._conn.execute(
                "SELECT key, value, confidence, source, updated_at "
                "FROM user_preferences "
                "WHERE user_id = ? AND confidence >= ? "
                "ORDER BY confidence DESC, updated_at DESC",
                (user_id, min_confidence),
            )
            rows = cur.fetchall()
        except sqlite3.Error as e:
            logger.warning("get_preferences failed: %s", e)
            return []

        prefs = [
            Preference(
                key=r["key"],
                value=r["value"],
                confidence=r["confidence"],
                source=r["source"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]
        if top_k is not None:
            prefs = prefs[:top_k]
        return prefs

    def recall_for_query(
        self,
        user_id: str,
        query: str,
        top_k: int = 3,
    ) -> list[Preference]:
        """基于 query 关键词召回相关偏好 (按 score DESC).

        算法 (简化版):
        1. 把 query 拆为 1-3 字符 substrings
        2. 对每条 preference: hits = keyword 命中数 (在 key + value 拼起来的 doc 中)
        3. score = hits * effective_confidence
           effective = stored * exp(-decay_lambda * days)
        4. 按 score 降序, 取 top_k

        Args:
            user_id: 用户 ID.
            query: 当前用户消息 (用于匹配).
            top_k: 召回条数.

        Returns:
            Preference 列表. 失败/无命中 → [].
        """
        if not query or not query.strip():
            return []
        try:
            prefs = self.get_preferences(user_id, min_confidence=0.0)
        except Exception as e:
            logger.warning("recall: get_preferences failed: %s", e)
            return []
        if not prefs:
            return []

        keywords = self._extract_keywords(query)
        if not keywords:
            return []

        now = time.time()
        scored: list[tuple[float, Preference]] = []
        for p in prefs:
            doc = f"{p.key} {p.value}"
            # hits = keyword 在 doc 中的累计出现次数, 加权 keyword 长度
            # (单字 keyword 权重低, 长 keyword 权重高; 长 kw 表示更具体语义)
            hits = sum(doc.count(kw) * len(kw) for kw in keywords)
            # 要求至少 2 分 (单字命中不足, 避免噪声)
            if hits < 2:
                continue
            eff = self._effective_confidence(p.confidence, p.updated_at, now)
            scored.append((hits * eff, p))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored[:top_k]]

    @staticmethod
    def _extract_keywords(text: str) -> set[str]:
        """拆 query 为 1-3 字符 substrings (简化版, 不引 jieba).

        用 hits ≥ 2 + 长度加权来过滤噪声 (单字不会单独够阈值).
        """
        keywords: set[str] = set()
        q = text.strip()
        for i in range(len(q)):
            for j in range(i + 1, min(i + 4, len(q) + 1)):
                kw = q[i:j]
                if kw.strip():
                    keywords.add(kw)
        return keywords

    def _effective_confidence(
        self,
        stored: float,
        updated_at: float,
        now: float | None = None,
    ) -> float:
        """计算衰减后置信度.

        effective = stored * exp(-lambda * days_since_update)
        """
        if now is None:
            now = time.time()
        days = max(0.0, (now - updated_at) / 86400.0)
        return stored * math.exp(-self._decay_lambda * days)

    # =================================================================
    # 推荐历史
    # =================================================================

    def record_recommendation(
        self,
        session_id: str | None,
        user_msg: str,
        result: str,
        cuisine_ids: list[str] | None = None,
        token_usage: int | None = None,
        latency_ms: int | None = None,
    ) -> int:
        """记录一次推荐 (写 recommendations 表).

        Args:
            session_id: 会话 ID, 可为 None.
            user_msg: 用户消息.
            result: Master Foodie 返回的推荐文本.
            cuisine_ids: 涉及的菜系 ID 列表.
            token_usage: LLM token 消耗.
            latency_ms: 端到端延迟 (毫秒).

        Returns:
            新记录的 id. 失败 → -1.
        """
        now = time.time()
        cuisine_json = (
            json.dumps(cuisine_ids, ensure_ascii=False) if cuisine_ids else None
        )
        try:
            cur = self._conn.execute(
                "INSERT INTO recommendations "
                "(session_id, user_msg, result, cuisine_ids, token_usage, latency_ms, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, user_msg, result, cuisine_json, token_usage, latency_ms, now),
            )
            return cur.lastrowid
        except sqlite3.Error as e:
            logger.warning("record_recommendation failed: %s", e)
            return -1


__all__ = ["LongTermMemory", "Preference"]
