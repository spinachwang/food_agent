# Progress - Food Agent 当前进度

> **这个文件的目的是**：让你（或未来的 Claude）打开新会话时，**30 秒内接上上下文**。
>
> 更新规则：每次完成一个 Phase / 修完一个 bug，**直接改这里**，然后在 git commit 一起提交。

最后更新: 2026-06-18

---

## TL;DR

| 项 | 状态 | 备注 |
|---|---|---|
| Phase 0 (项目初始化) | ✅ 完成 | commit `9f3e9a5` |
| Phase 1 (单菜系 E2E) | ✅ 完成 | commit `034cfca` |
| qwen-agent tool_call_id bug fix | ✅ 已修 | `src/food_agent/llm.py` 启动时 patch |
| Phase 2 (多菜系 + 记忆) | ✅ 完成 | 5 个子任务全部 commit, 见下 |
| Phase 3 (MCP + 分析器 + Web) | 🚧 下一个 | 见下 |
| 测试 | ✅ 143 个全过 | 整体覆盖率 85.86% |

---

## Phase 2 已完成项（详细）

**所有子任务独立 commit，可单独 revert：**

| 子任务 | commit | 新增测试 |
|---|---|---|
| 2.1 config/loader.py | `7e3c701` | 20 |
| 2.2 registry.py 动态加载 | `b155c11` | 9 |
| 2.3 川菜 prompt → .md | `ed970ac` | 7 |
| 2.5 短期记忆 | `0919a5b` | 16 |
| 2.6 长期记忆 (SQLite) | `0dcef60` | 31 |
| **合计** | | **83 新增** |

### 2.1 yaml 配置加载器 (`config/loader.py`)

- 5 个 frozen dataclass: `LLMConfig` / `ToolCallerConfig` / `MasterConfig` / `ShortTermConfig` / `LongTermConfig`
- `Settings` + `CuisineConfig` 各 1 个
- `load_settings(path=None)` / `load_cuisines(path=None)` — module-level singleton
- `get_setting("a.b.c", default=None)` — 嵌套取值
- `list_enabled_cuisines()` — 过滤 `enabled=false`
- `reload()` — 清空缓存
- fail-fast: 缺字段 / 类型错 → `ConfigurationError`
- 测试覆盖: 合法 yaml / 缺字段 / 类型错 / 文件不存在 / yaml 语法错 / 嵌套 get_setting / reload 生效 / 14 菜系 / enabled 过滤 / 重复 id / 不变性

### 2.2 registry 动态加载 (`registry.py`)

- `load_all_cuisines(llm_cfg, fallback_text, cuisines_yaml_path, strict=False)`
- 扫 `sys.modules` 找 `food_agent.agents.cuisines.*` 子模块的 `BaseCuisineAgent` 子类
- 默认 `strict=False`: yaml 里有但未实现的菜系 → 跳过 (log warning)
- `strict=True`: fail-fast (`ConfigurationError`)
- 用 `sys.modules` 而非 `pkgutil.iter_modules`, 支持测试动态注入
- `master.py._default_cuisines` 改调 `load_all_cuisines`
- 测试覆盖: enabled 过滤 / fallback 透传 / yaml 顺序 / strict fail / 默认 skip / yaml 不存在 / FoodAgent 集成

### 2.3 川菜 prompt 搬出

- 新增 `config/prompts/sichuan_v1.md` (川菜 system prompt)
- 新增 `data/cuisines/sichuan.md` (知识库)
- `BaseCuisineAgent` 加 `prompt_file` / `knowledge_file` 类属性
- 优先级: 显式传入 > `prompt_file` 文件 > 内联 `system_prompt` 类属性
- 文件不存在 → `logger.warning` + 降级到内联
- 向后兼容: 纯类属性子类 (不设 `prompt_file`) 仍能用
- `SichuanAgent` 删内联, 改用 `prompt_file="sichuan_v1.md"` / `knowledge_file="sichuan.md"`

### 2.5 短期记忆 (`memory/short_term.py`)

- `ShortTermMemory` dataclass
  - `max_messages=30` / `summarize_after_tokens=6000` / `keep_last_n_after_summary=6`
- token 估算: `chars/4` (不引入 tiktoken)
- `summarize(llm_cfg)` 调 LLM 摘要, 失败 → 硬截断到最近 N
- `FoodAgent.run(session_id=...)` 自动用 STM 管理 history
- 显式 `history` 参数优先于 `session_id` (向后兼容)
- 多 `session_id` 隔离 (lazy 加载)

### 2.6 长期记忆 (`memory/long_term.py`)

- `LongTermMemory(db_path, decay_lambda=0.01)` 类
- 启动自动应用 `schema.sql` (4 表: sessions / messages / user_preferences / recommendations)
- API:
  - `save_preference(user_id, key, value, confidence=1.0, source="explicit")` — upsert, confidence 取 max, clamp [0, 1]
  - `get_preferences(user_id, top_k=None, min_confidence=0.1)` — 排序 confidence DESC
  - `recall_for_query(user_id, query, top_k=3)` — 1-3 字符 substring 抽取 + 长度加权 + 衰减后 confidence
  - `record_recommendation(session_id, user_msg, result, cuisine_ids=None, ...)` — 写推荐历史
  - context manager (`__enter__/__exit__`)
- 置信度衰减: `effective = stored * exp(-lambda * days_since_update)`, `lambda=0.01` ≈ 70 天衰减到 1/e
- 召回算法: `score = sum(doc.count(kw) * len(kw) for kw in keywords)`, `hits < 2` 视为无命中
- fail-soft: sqlite 错误 `logger.warning` + return (不挂上层)
- `FoodAgent.run(user_id="default", ...)` 召回偏好 → system msg 注入, 调完 LLM 自动 `record_recommendation`

---

## Phase 3 任务清单（推荐顺序）

### 3.1 8 维分析器 (`agents/analyzers/`)
- `analyze_price / analyze_taste / analyze_weather / analyze_mood / analyze_occasion / analyze_time / analyze_location / analyze_dietary`
- 类似菜系, 继承 `BaseAnalyzer` 抽象
- 注册到 `cuisines.yaml` 同款 yaml

### 3.2 补齐菜系 (用户 Phase 2 明确不要, Phase 3 重新评估)
- 必做 8 大: 粤 / 鲁 / 苏 / 浙 / 闽 / 湘 / 徽
- 复用 2.3 模板 (`prompt_file` + `knowledge_file`)

### 3.3 MCP 真实工具
- `mcp_servers.json` 配 mock server
- `mcp/client.py` 包 MCP 协议
- 接通 `analyze_weather` (高德 / OpenWeather) 和 `analyze_location` (高德 POI)

### 3.4 Web UI (Gradio)
- 接入 `web.py` (目前 stub)
- 支持单条消息 / REPL / 流式输出
- 8 维可视化 (展示 master 调度过程)

### 3.5 记忆升级
- FTS5 / embedding 替换 keyword 召回
- `long_term.py` 同 API 换内部实现

### 3.6 Polish
- 启动时 13 个菜系 skip warning 噪声 (改 `logger.debug`)
- CLI 改进 (--no-memory / --user-id / --reset)

---

## 设计 vs 现状 (重要)

> **`specs/02-architecture.md` 是未来理想态**。当前代码远没那么完整。改代码前先看 `04-architecture-current.md`。

| 设计目标 | 当前状态 | 距离 |
|---|---|---|
| 14 个菜系专家 | 1 个 (SichuanAgent) | 缺 13 个 (Phase 3) |
| 8 维分析器 | 0 个 (`agents/analyzers/` 空) | 缺 8 个 (Phase 3) |
| 短期记忆 | ✅ 完成 | — |
| 长期记忆 | ✅ 完成 (keyword 召回) | FTS5 升级 (Phase 3) |
| MCP 工具 (天气/位置) | 空目录 | 缺 (Phase 3) |
| 动态菜系加载 (`registry.py`) | ✅ 完成 | — |
| settings.yaml loader | ✅ 完成 | — |
| Web UI (Gradio) | stub (`web.py` 15 行) | 缺 (Phase 3) |
| Skill 系统 | 空目录 | 缺 (Phase 3) |

---

## 关键 bug fix (历史, 仍要回归)

**`tool result's tool id() not found (2013)`** 来自 qwen-agent 0.0.34 在 `_conv_qwen_agent_messages_to_oai()` 中把 function → tool 时把 link id 写到 `id` 字段而非 `tool_call_id` 字段。

修复：在 `src/food_agent/llm.py:31-66` 加 `_patch_qwen_agent_tool_call_id()`，模块加载时自动执行，monkey-patch `BaseChatModel` 的静态方法。**升级 qwen-agent 时必须验证 patch 仍生效**（见 `tests/test_llm.py::test_tool_message_has_tool_call_id_not_id`）。

详见 `specs/04-architecture-current.md` §4。

---

## 已知坑（避免重复踩）

1. **qwen-agent tool_call_id bug** — 见上方"关键 bug fix"
2. **qwen-agent 流式 tool_call 在 oai.py 累积有 bug** → `master.py:_assistant_call_kwargs` 强制 `stream=False`
3. **MiniMax M3 必须 `use_raw_api=True`** — 否则走 text template 协议，model 不会原生调工具
4. **Windows GBK console 编码** — 测试和示例脚本需设 `PYTHONIOENCODING=utf-8`
5. **`use_raw_api` 与 `stream` 的限制** — `assert stream and (not delta_stream)` in `oai.py:222`，必须全量流式
6. **conda run + 长输出** — 中文会被 GBK codec 拒绝, 用 `PYTHONIOENCODING=utf-8` 前缀
7. **sqlite3.Connection.execute read-only** — `monkeypatch.setattr(conn, "execute", ...)` 不行, 改 mock 整个 `_conn` 对象

---

## 修改本文件

完成 Phase 子任务后，更新本文件对应的小节（加完成日期 + commit hash），然后在 git commit 信息里用 `progress: phaseN-X.Y done` 标识。
