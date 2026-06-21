# Progress - Food Agent 当前进度

> **这个文件的目的是**：让你（或未来的 Claude）打开新会话时，**30 秒内接上上下文**。
>
> 更新规则：每次完成一个 Phase / 修完一个 bug，**直接改这里**，然后在 git commit 一起提交。

最后更新: 2026-06-19

---

## TL;DR

| 项 | 状态 | 备注 |
|---|---|---|
| Phase 0 (项目初始化) | ✅ 完成 | commit `9f3e9a5` |
| Phase 1 (单菜系 E2E) | ✅ 完成 | commit `034cfca` |
| qwen-agent tool_call_id bug fix | ✅ 已修 | `src/food_agent/llm.py` 启动时 patch |
| Phase 2 (多菜系 + 记忆) | ✅ 完成 | 5 个子任务全部 commit |
| **Phase 3.1 (高德地图 MCP)** | ✅ 完成 | commit `02bbf87`, 3 个子任务 |
| **Phase 3.2 (3 维分析器)** | ✅ 完成 | commit `57d6937`, 3 个 analyzer tool |
| **Phase 3.3 (补齐 13 菜系)** | ✅ 完成 | commit TBD, 13 菜系 × 3 文件 + 160 测试 |
| **流式输出 (3.7 polish)** | ✅ 完成 | commit `e741356` (master) + `df99f5c` (cli) |
| **CLI AmapClient 集成修复** | ✅ 完成 | commit `df99f5c` (含在 cli 改动一起) |
| **Phase 3.5 Web UI (Gradio)** | ✅ 完成 | qwen_agent.gui.WebUI 包装 FoodAgent._assistant |
| **Phase 3.5 master tool 精简** | ✅ 完成 | 22 → 17 tool (location tool 收进 analyzer 内部) |
| 测试 | ✅ 427 个全过 | 整体覆盖率 ~83% (本次新增 6 个测试) |

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
- **Phase 3.5: 不再直接暴露给 master LLM**, 改由 analyzer 内部调. 类保留
  供单元测试 + 未来可能直接调用.

### FoodAgent 集成 (Phase 3.5 改造)
- 新增 `amap_client: AmapClient | None = None` 参数
- 传了之后: amap_client 注入到模块单例 (供 analyzer 内部用)
- **5 个 location tool 不再自动加到 master.tools** — 改由 analyzer 内部调 AmapClient
- master LLM 可见工具数: 22 (14 菜系 + 5 location + 3 analyzer) → **17 (14 菜系 + 3 analyzer)**
- 理由: Toolformer 论文建议 LLM 同时可见 ≤10 个 tool, 17 仍有压力但比 22 好
- 周边搜索 (search_around) 能力合并进 `analyze_location`: user_msg 含 "附近/找/搜"
  + 食物关键词 (川菜/咖啡/火锅/...) 时自动 search_around, POI 列表放在返回 pois 字段.
  master LLM 不再需要二次调 search_around, 调用链简化.
- `master_v1.md` 删"位置与天气工具"段, 改写 `analyze_location` 描述包含周边搜索触发条件

### CLI 集成 (commit `df99f5c` 修复)
- **Bug**: 之前 CLI 的 `_build_agent()` 没构造 `AmapClient`,
  导致 `FoodAgent._amap_client = None` → `set_amap_client()` 没调 →
  `tools/location` 模块级单例是 None → 3 个 analyzer (天气/位置/饮食)
  全部返回 `{"confidence": 0.0, "error": "AmapClient 未配置..."}`.
- 单元测试都直接 `FoodAgent(amap_client=AmapClient(...))`, 只有 CLI
  走 `_build_agent()` 这条路径会触发, 所以单测全过但 E2E 失败.
- **修复**: 新增 `_build_amap_client()` 函数, 默认从 env 读
  (`AMAP_USE_MOCK` / `AMAP_API_KEY`), 缺 key 时 stderr 警告 + 关闭.
- 新增 CLI flags: `--amap-mock` (强制 mock, 覆盖 env, 省 key 配额),
  `--no-amap` (关闭 amap, analyzer 返 confidence=0 不阻塞主流程).

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

### 3.3 补齐菜系 ✅ 完成

**所有 13 个菜系独立文件, 复用 Phase 2.3 模板 (prompt .md + knowledge .md + agent .py)**:

| 菜系 | 性格人物 | 特色 emoji | 代表菜 |
|---|---|---|---|
| 粤菜 cantonese | 何伯（广州西关老饕） | 🦐 鲜度 | 白切鸡、烧鹅、老火汤、早茶虾饺 |
| 鲁菜 shandong | 鲁师傅（济南人） | 🧂 咸度 | 糖醋鲤鱼、九转大肠、葱烧海参 |
| 苏菜 jiangsu | 沈先生（扬州文人） | 🍃 浓淡 | 蟹粉狮子头、松鼠鳜鱼、扬州炒饭 |
| 浙菜 zhejiang | 杭伯（杭州人） | 🌱 鲜甜 | 西湖醋鱼、龙井虾仁、东坡肉 |
| 闽菜 fujian | 林伯（福州马尾渔民） | 🦪 鲜度 | 佛跳墙、海蛎煎、沙茶面 |
| 湘菜 hunan | 毛家阿婆（长沙坡子街） | 🌶️ 辣度 | 剁椒鱼头、毛氏红烧肉、辣椒炒肉 |
| 徽菜 anhui | 胡掌柜（徽州歙县） | 🧀 油度 | 臭鳜鱼、火腿炖甲鱼、毛豆腐 |
| 日料 japanese | 佐藤先生（京都老职人） | 🍣 鲜度 | 寿司、刺身、怀石、天妇罗、拉面 |
| 西餐 western | Jean-Pierre（巴黎侍酒师） | 🥩 火候 | 牛排、鹅肝、生蚝、惠灵顿 |
| 西式快餐 western_fastfood | 麦麦叔（前麦当劳经理） | 🍔 套餐 | 巨无霸、原味鸡、必胜客披萨 |
| 中式快餐 chinese_fastfood | 老张（CBD 拉面老板） | 🍜 主食 | 沙县拌面、兰州拉面、黄焖鸡 |
| 小吃 snack | 夜行阿杰（20 年夜市） | 🥟 品类 | 各地代表小吃 + 夜宵 |
| 甜品饮品 dessert_drink | 小甜（小红书 10w 粉） | 🍰 品类 | 喜茶、瑞幸、糖水、烘焙 |

**新增文件 (39 个)**:
- `src/food_agent/agents/cuisines/<id>.py` × 13 (每个 30 行, 照 sichuan.py 模板)
- `src/food_agent/config/prompts/<id>_v1.md` × 13 (每个 50-60 行)
- `src/food_agent/data/cuisines/<id>.md` × 13 (每个 50-65 行)
- `tests/test_all_cuisines.py` (160 测试, 覆盖元数据/prompt 加载/knowledge 加载/describe/recommend/fallback/yaml 一致性)
- `examples/all_cuisines_smoke.py` (端到端 smoke)
- `src/food_agent/agents/cuisines/__init__.py` (新增, eager import 所有子模块)
- `tests/__init__.py` (新增, 让 `from tests.X import Y` 可用)

**改动**:
- `src/food_agent/registry.py` — `_discover_cuisine_classes()` 主动 import cuisines 包, 确保子模块加载

**关键设计点**:
- **性格人物差异化**: 13 个菜系 13 个不同人物, 跟老陈(川菜)地区/方言/专长都不重叠
- **emoji 反映菜系特色**: 川菜 🌶️(辣度)/粤 🦐(鲜度)/鲁 🧂(咸度)/苏 🍃(浓淡)/浙 🌱(鲜甜)/闽 🦪(海味)/湘 🌶️(辣)/徽 🧀(油度)/日 🍣(鲜度)/西 🥩(火候)
- **真实餐厅**: 包含陶陶居/利苑/丰泽园/冶春/楼外楼/聚春园/玉楼东/同庆楼/鮨一/莫尔顿/麦当劳等
- **覆盖 8 维分析**: 每个 prompt 的"能力"段都对接价格/口味/天气/心情/场景/时段/位置/饮食限制
- **慎选互补**: 粤菜"重口味嗜辣者→改推湘川"、湘菜"怕辣→改推粤苏浙"形成互补矩阵
- **西餐明确排除快餐**: western.py 顶部 docstring/prompt/知识库多处写明"必胜客/麦当劳/肯德基不算西餐"
- **场景导向非味道导向** (快餐/小吃/饮品): 突出"赶时间/夜宵/下午茶/解辣", 不是"商务宴请"

**踩坑**:
1. `cuisines/` 包没有 `__init__.py`, registry 扫不到子模块 → 加 `__init__.py` 用 pkgutil 主动 import + registry 主动 import 包
2. `tests/` 同样没 `__init__.py`, `from tests.X import Y` 失败 → 加 `__init__.py` (空文件)
3. smoke test 必须 `PYTHONIOENCODING=utf-8` (Windows GBK console 中文乱码)

### 3.4 接外卖平台（接了 location 后, 这是下一步）
- 美团 / 饿了么 (H5 跳转 → 路径 B, 推荐)
- 或接 Open API (路径 C, 全流程)

### 3.5 Web UI (Gradio) ✅ 完成
- `web.py` 顶层 try/except import `qwen_agent.gui.WebUI` (避免 gradio
  deprecation warning 在 pytest `--strict-config` 下被升级为 error)
- 复用 `cli._build_agent()` 构造 FoodAgent (amap/long_term 自动配好)
- `WebUI(agent._assistant, chatbot_config=...)` + `.run(server_name, server_port)`
- 环境变量: `FOOD_AGENT_WEB_HOST` (默认 127.0.0.1), `FOOD_AGENT_WEB_PORT` (默认 7860)
- Trade-off (vs 走 FoodAgent.run()):
  - ✅ 14 菜系调度 + 高德 MCP (assistant 已含这些 tools)
  - ❌ 短期/长期记忆 (WebUI 自己管 history, 不走 STM/LTM)
  - ❌ 饮食偏好自动保存 (FoodAgent.run() 才触发)
  - ❌ on_event 流式进度 (WebUI 是黑盒)
- Phase 6 计划: 自定义 gr.ChatInterface + FoodAgent.run() + 流式 on_event
- 跑法: `PYTHONIOENCODING=utf-8 conda run -n qwenagent-mcp python -m food_agent.web`
  → 浏览器 http://127.0.0.1:7860

### 3.6 记忆升级
- FTS5 / embedding 替换 keyword 召回

### 3.7 Polish
- 启动时 13 个菜系 skip warning 改 `logger.debug`
- ✅ **流式分阶段输出** (commit `e741356` + `df99f5c`):
  - `master.run(on_event=...)` 回调接口, 迭代 `Assistant.run()` batches
  - CLI `--verbose/-v` flag, REPL 默认开启
  - 工具调用 / 结果用 rich + emoji 实时显示 (🌦️ 查天气 / 🍜 请教川菜专家 / ✅ 预览)
- CLI 改进 (--no-memory / --user-id / --reset)

---

## 设计 vs 现状 (重要)

> **`specs/02-architecture.md` 是未来理想态**。当前代码远没那么完整。改代码前先看 `04-architecture-current.md`。

| 设计目标 | 当前状态 | 距离 |
|---|---|---|
| 14 个菜系专家 | ✅ 14 个 (川粤鲁苏浙闽湘徽 + 日料西餐 + 快餐×2 + 小吃 + 饮品) | 全部完成 (Phase 3.3) |
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
11. **mcp SDK 顶层 import** — `amap_client.py` 顶部 import, 便于 test patch (`food_agent.mcp.amap_client.streamablehttp_client`)
12. **mcp SDK 加载 dotenv** — `amap_client.py` 顶部 `load_dotenv()`, 独立可用
13. **CLI 不构造 AmapClient** — 修复 commit `df99f5c`. 见 "Phase 3.1 / CLI 集成" 段

---

## 修改本文件

完成 Phase 子任务后，更新本文件对应的小节（加完成日期 + commit hash），然后在 git commit 信息里用 `progress: phaseN-X.Y done` 标识。