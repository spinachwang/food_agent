"""Smoke test: 长期记忆真实 SQLite 操作."""
from food_agent.memory.long_term import LongTermMemory
import os
import tempfile

# 用临时目录
tmpdir = tempfile.mkdtemp()
db = os.path.join(tmpdir, "ltm_smoke.db")

try:
    with LongTermMemory(db) as ltm:
        ltm.save_preference("alice", "spicy", "不吃辣", 0.9)
        ltm.save_preference("alice", "budget", "100 元以内", 0.7)
        ltm.record_recommendation("s1", "我想吃辣", "陈麻婆豆腐")

        print("alice prefs:", [(p.key, p.value, p.confidence) for p in ltm.get_preferences("alice")])
        print("recall '我不吃辣' →", [(p.key, p.value) for p in ltm.recall_for_query("alice", "我不吃辣")])
        print("recommendations count:", ltm._conn.execute("SELECT COUNT(*) FROM recommendations").fetchone()[0])

    # 重开 db 验证持久
    with LongTermMemory(db) as ltm2:
        print("after reopen, alice prefs count:", len(ltm2.get_preferences("alice")))

    print("OK")
finally:
    if os.path.exists(db):
        os.remove(db)
    os.rmdir(tmpdir)
