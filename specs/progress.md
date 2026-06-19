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
| Phase 2 (多菜系 + 记忆) | ✅ 完成 | 5 个子任务全部 commit |
| **Phase 3.1 (高德地图 MCP)** | ✅ 完成 | commit `02bbf87`, 3 个子任务 |
| **Phase 3.2 (3 维分析器)** | ✅ 完成 | commit TBD, 3 个 analyzer tool |
| 测试 | ✅ 222 个全过 | 整体覆盖率 83.88% |

---

## Phase 3.1 已完成项（高德地图 MCP）

**所有子任务独立 commit：**

| 子任务 | commit | 新增测试 |
|---|---|---|
| 3.1 AmapClient (mcp/amap_client.py) | TBD | 24 |
| 3.2 LocationTool (tools/location.py) | TBD | 22 |
| 3.3 master 集成 + 提示词更新 | TBD | 8 |
| **合计** | | **54 新增** |

### 接入方式
- 使用**高德官方 MCP server** (streamable HTTP, URL 模式)
- URL: `https://mcp.amap.com/mcp?key=<AMAP_API_KEY>`
- 实际提供 **15 个 tool** (含 `maps_geo`, `maps_around_search`, `maps_weather`, `maps_direction_*` 等)
- 用 `mcp` Python SDK 1.12.4 的 `streamablehttp_client` + `ClientSession`

### AmapClient (`src/food_agent/mcp/amap_client.py`)
- 6 个 sync 公共方法: `geocode / regeocode / search_around / text_search / weather / route`
- 内部用 `asyncio.run()` 跑 mcp SDK (每次 call 新建 session, 200ms 开销)
- **mock 模式** (`AMAP_USE_MOCK=true`): 返回假数据, CI 不消耗 key
- **真模式**: 连 mcp.amap.com, 含 1 天 TTL 缓存
- **fail-soft**: 任何异常 → `logger.warning` + 返回空
- geocode v2 schema 兼容: 把 `"lng,lat"` 字符串解析为 `{lng, lat}` dict
- context manager (`__enter__/__exit__`)
- 顶部 `load_dotenv()`, 独立可用 (不依赖 FoodAgent)

### LocationTool (`src/food_agent/tools/location.py`)
- 5 个 `qwen_agent.tools.base.BaseTool` 子类: `Geocode / Regeocode / SearchAround / Weather / Route`
- 每个都有 OpenAI JSON Schema `parameters` (qwen-agent 透传给 LLM)
- `.call(params)` 接收 JSON 字符串, 返回 JSON 字符串
- 共享模块级 AmapClient (用 `set_amap_client()` / `get_amap_client()`)
- 参数解析失败 / AmapClient 失败 → 错误 JSON, 不挂上层

### FoodAgent 集成
- 新增 `amap_client: AmapClient | None = None` 参数
- 传了之后: 5 个 location tool 自动加入 `self.tools`
- `master_v1.md` 新增"位置与天气工具"段, 描述典型用法流程

### .env 配置
```bash
AMAP_API_KEY=<your_key>      # 高德 key
AMAP_USE_MOCK=true|false     # 默认 true (mock), 手动开真
```

### 用法
```python
from food_agent.mcp.amap_client import AmapClient
from food_agent.master import FoodAgent

with AmapClient() as amap:  # 默认 mock 模式 (或读 .env)
    agent = FoodAgent(amap_client=amap)
    agent.run("我在北京海淀, 找附近 2km 的川菜")
```

### Smoke test 验证
- `examples/amap_real_smoke.py`: 真实 key, 验证 list_tools (15 个) / geocode / search_around
- `examples/amap_master_smoke.py`: FoodAgent + 真 amap 端到端 (mock LLM)

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

### 2.2 registry 动态加载 (`registry.py`)
- `load_all_cuisines(llm_cfg, fallback_text, cuisines_yaml_path, strict=False)`
- 扫 `sys.modules` 找 `food_agent.agents.cuisines.*` 子模块的 `BaseCuisineAgent` 子类
- 默认 `strict=False`: yaml 里有但未实现的菜系 → 跳过 (log warning)
- `strict=True`: fail-fast (`ConfigurationError`)
- 用 `sys.modules` 而非 `pkgutil.iter_modules`, 支持测试动态注入
- `master.py._default_cuisines` 改调 `load_all_cuisines`

### 2.3 川菜 prompt 搬出
- 新增 `config/prompts/sichuan_v1.md` + `data/cuisines/sichuan.md`
- `BaseCuisineAgent` 加 `prompt_file` / `knowledge_file` 类属性
- 优先级: 显式传入 > `prompt_file` 文件 > 内联 `system_prompt`
- 向后兼容: 纯类属性子类仍能用

### 2.5 短期记忆 (`memory/short_term.py`)
- `ShortTermMemory` dataclass (max_messages=30 / summarize_after_tokens=6000)
- token 估算: `chars/4`
- `summarize(llm_cfg)` 调 LLM, 失败 → 硬截断
- `FoodAgent.run(session_id=...)` 自动用 STM 管理

### 2.6 长期记忆 (`memory/long_term.py`)
- `LongTermMemory(db_path, decay_lambda=0.01)` + 启动自动应用 schema.sql
- API: `save_preference / get_preferences / recall_for_query / record_recommendation`
- 置信度衰减: `effective = stored * exp(-lambda * days)`
- 召回: 1-3 字符 substring + 长度加权 + 衰减后 confidence
- fail-soft + `FoodAgent.run(user_id="default", ...)` 召回偏好注入 system msg

---

## Phase 3 任务清单（推荐顺序）

### 3.1 高德地图 MCP ✅ 完成 (`02bbf87`)
### 3.2 3 维分析器 ✅ 完成
**精简决策**: 原 8 维里只有 3 个真正需要 tool, 其余让 master LLM 在 system prompt 里直接分析 (避免冗余).

**只做的 3 个 analyzer**:

| Analyzer | 必要性 | 实现 |
|---|---|---|
| `analyze_weather` | ✅ 必须 (外部数据) | 调 amap `maps_weather` + 规则推导饮食建议 |
| `analyze_location` | ✅ 必须 (外部数据) | 优先 `maps_ip_location` (web 场景), 降级到 `maps_geo` (CLI 场景) |
| `analyze_dietary` | ✅ 必须 (安全关键) | 硬约束 (过敏/宗教) 100% 排除 + 软偏好 + 长期记忆整合 |
| ~~price/taste/mood/occasion/time~~ | ❌ LLM 自做 | 价格/口味/情绪/场合/时间, LLM 直接从消息抽取 |

**新增文件**:
- `src/food_agent/agents/analyzers/__init__.py` — `list_analyzer_tools()` 工厂
- `src/food_agent/agents/analyzers/base.py` — `_AnalyzerToolBase` 公共基类
- `src/food_agent/agents/analyzers/weather.py` — `WeatherAnalyzerTool`
- `src/food_agent/agents/analyzers/location.py` — `LocationAnalyzerTool`
- `src/food_agent/agents/analyzers/dietary.py` — `DietaryAnalyzerTool` (含 long_term 整合)
- `tests/test_analyzers.py` — 20 个测试
- `examples/analyzer_master_smoke.py` — 端到端验证

**改动**:
- `AmapClient` 加 `ip_location()` 方法
- `master.py` 加 `enable_analyzers=True` 参数, 默认注入 3 个 analyzer
- `master_v1.md` 精简: 8 维 → 3 维, 5 个 LLM 自做维度列在 prompt 里
- `test_master_agent.py` 更新 (analyzer tool 不是 CuisineConsultTool)

**Dietary 关键设计**:
- 硬约束 (过敏/宗教) 必须 100% 排除, 不能 LLM 推测
- 软偏好 regex 匹配 `不爱吃|不喜欢|不爱|不吃|不要|讨厌|嫌|拒绝`
- 整合 long_term: key 以 `allergy_/no_/religion_/avoid_` 开头的视为已知偏好

**踩坑**:
- Regex 字符类 `[北京]` 只匹配单字符, 要 alternation `[北京|上海|...]`
- "我在北京" vs "今天北京": `(?:在|...)` 前缀要可空, 避免误匹配

### 3.3 补齐菜系 (用户 Phase 2 明确不要, 重新评估)
- 必做 8 大: 粤 / 鲁 / 苏 / 浙 / 闽 / 湘 / 徽
- 复用 2.3 模板

### 3.4 接外卖平台（接了 location 后, 这是下一步）
- 美团 / 饿了么 (H5 跳转 → 路径 B, 推荐)
- 或接 Open API (路径 C, 全流程)

### 3.5 Web UI (Gradio)
- 接入 `web.py` (目前 stub)

### 3.6 记忆升级
- FTS5 / embedding 替换 keyword 召回

### 3.7 Polish
- 启动时 13 个菜系 skip warning 改 `logger.debug`
- CLI 改进 (--no-memory / --user-id / --reset)

---

## 设计 vs 现状 (重要)

> **`specs/02-architecture.md` 是未来理想态**。当前代码远没那么完整。改代码前先看 `04-architecture-current.md`。

| 设计目标 | 当前状态 | 距离 |
|---|---|---|
| 14 个菜系专家 | 1 个 (SichuanAgent) | 缺 13 个 (Phase 3.3) |
| 8 维分析器 | 0 个 (`agents/analyzers/` 空) | 缺 8 个 (Phase 3.2) |
| 短期记忆 | ✅ 完成 | — |
| 长期记忆 | ✅ 完成 (keyword 召回) | FTS5 升级 (Phase 3.6) |
| 高德地图 (位置 / 天气) | ✅ 完成 (15 tools) | 升级 IP 定位 (Phase 3.6) |
| 餐厅搜索 / 外卖 | ❌ | 缺 (Phase 3.4) |
| 动态菜系加载 (`registry.py`) | ✅ 完成 | — |
| settings.yaml loader | ✅ 完成 | — |
| Web UI (Gradio) | stub (`web.py` 15 行) | 缺 (Phase 3.5) |
| Skill 系统 | 空目录 | 缺 |

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
8. **AmapClient 真模式** — 每次 call 新建 mcp session (200ms 开销). 高德限频 3 QPS, 一次推荐流程 2-3 次 location call 不会触限
9. **geocode v2 schema** — 高德实际返回 `"location": "lng,lat"` 字符串, AmapClient 内部规范化成 `{lng, lat}` dict
10. **mcp SDK 顶层 import** — `amap_client.py` 顶部 import, 便于 test patch (`food_agent.mcp.amap_client.streamablehttp_client`)
11. **mcp SDK 加载 dotenv** — `amap_client.py` 顶部 `load_dotenv()`, 独立可用

---

## 修改本文件

完成 Phase 子任务后，更新本文件对应的小节（加完成日期 + commit hash），然后在 git commit 信息里用 `progress: phaseN-X.Y done` 标识。