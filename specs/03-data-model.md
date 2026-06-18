# 03 - Data Model

> 持久化数据模型。所有表都用 SQLite（stdlib `sqlite3`），便于单机部署。

## 1. 实体关系

```
┌──────────────┐ 1    N ┌──────────────┐
│   sessions   │────────│   messages   │
└──────────────┘        └──────────────┘
       │ 1
       │ N
       ▼
┌──────────────────┐
│ recommendations  │
└──────────────────┘

┌──────────────────┐
│ user_preferences │ (独立表, 按 user_id 索引)
└──────────────────┘

┌──────────────────┐  (静态 YAML, 不入库)
│     cuisines     │
└──────────────────┘

┌──────────────────┐  (静态 JSON, 不入库)
│   restaurants    │
└──────────────────┘
```

## 2. 表结构

### 2.1 sessions（会话）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | UUID v4 |
| user_id | TEXT | 匿名用户 ID（v1 不做登录） |
| started_at | REAL | Unix 时间戳 |
| ended_at | REAL NULL | 会话结束时间 |
| summary | TEXT NULL | 会话摘要（> 30 轮时生成） |

### 2.2 messages（消息历史）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增 |
| session_id | TEXT FK | → sessions.id |
| role | TEXT | `user` / `assistant` / `system` / `tool` |
| content | TEXT | 消息内容（tool 时为 JSON） |
| name | TEXT NULL | 工具名（role=tool 时） |
| tool_call_id | TEXT NULL | 工具调用 ID |
| created_at | REAL | Unix 时间戳 |

索引：`(session_id, created_at)`

### 2.3 user_preferences（用户偏好）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增 |
| user_id | TEXT |  |
| key | TEXT | 偏好键，如 `spice_tolerance` / `allergies` / `disliked_cuisines` |
| value | TEXT | JSON 序列化的值 |
| confidence | REAL | 0-1，1.0=显式 / <1.0=推断 |
| source | TEXT | `explicit` / `inferred` |
| created_at | REAL |  |
| updated_at | REAL |  |

唯一索引：`(user_id, key)`

衰减公式：`confidence *= exp(-lambda * days_since_update)`，lambda=0.01（≈ 100 天半衰期）

### 2.4 recommendations（推荐历史）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增 |
| session_id | TEXT FK NULL |  |
| user_msg | TEXT | 原始用户消息 |
| result | TEXT | 最终 LLM 回复 |
| tool_calls | TEXT NULL | JSON 数组，工具调用链路 |
| cuisine_ids | TEXT NULL | 逗号分隔，调用的菜系专家 |
| token_usage | INTEGER NULL | 累计 token |
| latency_ms | INTEGER NULL | 端到端延迟 |
| created_at | REAL |  |

## 3. 静态数据（不入库）

### 3.1 cuisines（菜系清单）— YAML

见 [cuisines.yaml](../../src/food_agent/config/cuisines.yaml)

字段：
- `id` / `name` / `category` / `subcategory`
- `prompt_file` / `knowledge_file`
- `enabled` / `tags`

### 3.2 restaurants（餐厅数据）— JSON

字段：
- `id` / `name` / `cuisine_id` / `price_range` / `address` / `rating` / `tags`

Phase 1-2 用 mock JSON；Phase 5 后改 MCP server。

## 4. 内存数据（不持久化）

### 4.1 Context Constraints（实时约束）

由 8 维分析器产出，**不**入库。每轮新：

```python
@dataclass(frozen=True)
class UserConstraints:
    price: PriceRange | None
    taste: TasteProfile | None
    weather: WeatherInfo | None
    mood: MoodInfo | None
    occasion: OccasionInfo | None
    time_slot: TimeSlot | None
    location: LocationInfo | None
    dietary: DietaryInfo | None
```

## 5. 数据生命周期

| 实体 | 创建 | 保留 |
|---|---|---|
| session | 用户开始对话 | 30 天 |
| message | 每轮 | 同 session |
| user_preference | 显式或推断 | 永久（或用户删除） |
| recommendation | 每次推荐 | 90 天（用于学习） |
| cuisine | 启动加载 | 静态 |
| restaurant | 启动加载 | 静态（Phase 1-2） |

## 6. 隐私

- 所有数据本地 SQLite，不上传
- 提供 `clear_user_data(user_id)` API
- 提供 `export_user_data(user_id) -> JSON` API
- session_id 匿名生成，不绑定任何 PII

## 7. SQLite Schema（DDL）

```sql
-- sessions
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    started_at REAL NOT NULL,
    ended_at REAL,
    summary TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, started_at DESC);

-- messages
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL,
    name TEXT,
    tool_call_id TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);

-- user_preferences
CREATE TABLE IF NOT EXISTS user_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    source TEXT DEFAULT 'explicit',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(user_id, key)
);
CREATE INDEX IF NOT EXISTS idx_prefs_user ON user_preferences(user_id);

-- recommendations
CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    user_msg TEXT NOT NULL,
    result TEXT NOT NULL,
    tool_calls TEXT,
    cuisine_ids TEXT,
    token_usage INTEGER,
    latency_ms INTEGER,
    created_at REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_recs_session ON recommendations(session_id, created_at DESC);
```

## 8. 数据模型变更策略

- 任何 schema 变更必须：
  1. 在 `memory/schema.sql` 中更新
  2. 写 `memory/migrations/v<N>.py` 迁移脚本
  3. 启动时按版本号自动应用
- **禁止** 直接 ALTER 生产表

---

## 修订记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-06-18 | v0.1 | 初稿 |
