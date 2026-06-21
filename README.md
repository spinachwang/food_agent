# 🍜 Food Agent — 多 Agent 美食推荐系统

> "老饕" 调度 14 位菜系专家 + 3 维分析器 (天气/位置/饮食限制)，根据用户当下状态综合推荐。
> 基于 **qwen-agent** + **MiniMax M3** (OpenAI 兼容) + **Gradio** + **SQLite** + **MCP**。

---

## 这是什么

一个完整跑通的多 Agent 美食推荐项目，包含：

- **主 Agent ("老饕")** 调度菜系专家子 Agent — 川、粤、鲁、苏、浙、闽、湘、徽、日料、西餐、西式快餐、中式快餐、小吃、甜品饮品 (共 14 个)
- **3 维分析器** — 天气 (`analyze_weather`) / 位置 (`analyze_location`) / 饮食限制 (`analyze_dietary`)
- **两层 LLM 调用** — master 调度 → 子 Agent 出专业意见 → master 综合输出
- **短期 + 长期记忆** — 第二次会话自动避开海鲜过敏；置信度衰减 + keyword 召回
- **流式输出** — CLI REPL 实时显示工具调用进度 (rich + emoji)
- **Web UI** — Gradio 包装 FoodAgent 的 `assistant`

适用人群：

- 想看多 Agent 编排 **真实可跑代码** 的人 (非 toy demo)
- 学习 qwen-agent + OpenAI 兼容 API + MCP 集成的人
- 想做类似垂直领域多 Agent 产品的人 (代码可作为参考实现)

---

## 5 分钟跑起来

### 1. 安装依赖 (conda)

```bash
conda activate qwenagent-mcp   # 项目根 pyproject.toml 已装好所有依赖
pip install -e .
```

### 2. 配置 API key

项目根 `.env` 文件：

```bash
# 必需
MINIMAX_API_KEY=<your_minimax_key>
MINIMAX_BASE_URL=https://api.minimaxi.com/v1   # 默认

# 可选: 高德地图 (位置/天气), 缺 key 设 mock=true
AMAP_API_KEY=<your_amap_key>
AMAP_USE_MOCK=true
```

### 3. 跑

**CLI 单次**：

```bash
PYTHONIOENCODING=utf-8 python -m food_agent "今天下雨, 一个人, 想吃辣的, 预算 100"
```

**CLI REPL** (带流式输出 + 长期记忆)：

```bash
PYTHONIOENCODING=utf-8 python -m food_agent --user-id=me
> 我海鲜过敏
> 推荐点菜   ← 自动避开海鲜
```

**Web UI (Gradio)**：

```bash
PYTHONIOENCODING=utf-8 python -m food_agent.web
# 浏览器打开 http://127.0.0.1:7860
```

---

## 演示

```
> 我在杭州市钱塘区义蓬购物中心, 想吃炸鸡, 你帮我推荐
[🌦️ analyze_weather]   杭州市: 25°C 多云, 建议清爽
[📍 analyze_location]  义蓬购物中心 (lng, lat) + 周边 1km POI
[🥗 analyze_dietary]   无硬约束
[🍗 consult_western_fastfood] 麦麦叔: 购物中心 1 楼麦当劳, 原味鸡 yyds
[🥟 consult_snack]     夜行阿杰: B1 有家 "老王炸鸡", 现炸出锅

🎯 推荐: 老王炸鸡 (小吃 / 现炸)
📍 位置: 义蓬购物中心 B1 美食街
💰 人均: 35
🍽️ 必点: 原味炸鸡半只、椒盐鸡柳、蜂蜜黄油
💡 理由: 现炸出锅, 比连锁更新鲜; 旁边电影院, 可打包边走边吃
⚠️ 注意: 高峰排队 10-15 分钟, 建议先取号

还合适吗?
```

---

## 架构

```
用户 ─▶ cli / web ─▶ FoodAgent (master)
                          │
                          ├─ Assistant (master_v1.md 提示词)
                          │   14 菜系 + 3 analyzer = 17 tool
                          │
                          ├─▶ analyze_weather  ─┐
                          ├─▶ analyze_location ─┼─▶ AmapClient ─▶ 高德 MCP
                          └─▶ analyze_dietary  ─┘     (mock-first, 1 天 TTL)

                          └─▶ consult_<cuisine> ─▶ CuisineConsultTool
                                                        │
                                                        └─▶ <Cuisine>Agent (子 Assistant)
                                                              system: cuisines/<id>_v1.md
                                                              knowledge: data/cuisines/<id>.md
                                                              │
                                                              └─▶ MiniMax M3 (OpenAI 兼容 API)
```

详细架构: [specs/04-architecture-current.md](specs/04-architecture-current.md)

---

## 项目结构

```
src/food_agent/
├── master.py           # FoodAgent 主类 (调度核心)
├── llm.py              # LLM 配置 + qwen-agent tool_call_id patch
├── cli.py              # CLI / REPL (rich 流式输出)
├── web.py              # Gradio Web UI
├── agents/
│   ├── cuisines/       # 14 个菜系专家 (川粤鲁苏浙闽湘徽 + 日料西餐 + 快餐×2 + 小吃 + 饮品)
│   └── analyzers/      # 3 维分析器 (weather / location / dietary)
├── tools/              # Tool 实现 (cuisine_consult + location)
├── memory/             # ShortTermMemory + LongTermMemory (SQLite)
├── mcp/                # AmapClient (高德地图 MCP)
├── config/             # yaml loader + 提示词 .md 文件
└── data/cuisines/      # 菜系知识库 .md

tests/                  # 430+ 个测试, 覆盖率 ~83%
specs/                  # PRD / 架构 / 数据模型 / 进度文档 (SDD)
examples/               # 可运行的示例脚本
docs/                   # 项目其他文档 (面试亮点等)
```

---

## 当前进度

| Phase | 状态 | 备注 |
|---|---|---|
| Phase 0 项目初始化 | ✅ | |
| Phase 1 单菜系 E2E (川菜) | ✅ | qwen-agent tool_call_id patch |
| Phase 2 多菜系 + 记忆 | ✅ | 14 菜系 + STM/LTM |
| Phase 3.1 高德 MCP | ✅ | 15 tools 接入 |
| Phase 3.2 3 维分析器 | ✅ | weather / location / dietary |
| Phase 3.3 补齐 13 菜系 | ✅ | |
| Phase 3.5 Web UI (Gradio) | ✅ | qwen_agent.gui.WebUI 包装 |
| Phase 3.5 master tool 精简 | ✅ | 22 → 17 tool (Toolformer ≤10 阈值) |
| Phase 3.7 流式输出 | ✅ | on_event 回调 + rich |
| **Phase 3.4 外卖/餐厅搜索** | ❌ | 下一步 |
| Phase 3.6 记忆升级 (FTS5) | 🚧 | |

详细进度: [specs/progress.md](specs/progress.md)

---

## 测试

```bash
PYTHONIOENCODING=utf-8 pytest --cov=src --cov-report=term-missing
```

- **430+ 个测试全过** (含 qwen-agent patch 回归 + 防幻觉 prompt 合同测试)
- 覆盖率 **~83%** (目标 ≥80%)
- `FakeLLM` 不走真 API, CI 不消耗 token

---

## 关键设计决策

| 决策 | 理由 |
|---|---|
| 14 菜系 + 3 analyzer = 17 tool | Toolformer 建议 ≤10, 超过 LLM 选择混乱 |
| location tool 收进 analyzer 内部 | 不直接暴露给 master, 减少 master 选择压力 |
| 长期记忆走 SQLite + keyword 召回 | 简单可调试, Phase 3.6 升级 FTS5 |
| AmapClient mock-first | CI 不消耗 key, 真模式只用于 smoke test |
| master prompt 文件化 (`master_v1.md`) | git diff 可视化, 版本管理 |
| 防幻觉 prompt 合同测试 | 钉死能力边界声明 + 硬规则, 防 LLM 升级时退化 |

---

## 已知坑

- **Windows GBK console**: 测试和示例脚本必须 `PYTHONIOENCODING=utf-8` 前缀, 否则中文乱码
- **qwen-agent 0.0.34 有 tool_call_id 协议 bug**, 在 `src/food_agent/llm.py` 启动时 monkey-patch; **升级 qwen-agent 时必须跑 `tests/test_llm.py` 验证 patch 仍生效** (5 个回归测试钉死)
- **MiniMax M3 必须 `use_raw_api=True`**, 否则走 text template 协议, model 不会原生调工具
- **mcp SDK 顶层 import** — 便于测试时 monkey-patch (`food_agent.mcp.amap_client.streamablehttp_client`)

---

## 文档导航

| 文档 | 用途 |
|---|---|
| [CLAUDE.md](CLAUDE.md) | 项目级 Claude 指令 (每次新会话先看) |
| [specs/01-prd.md](specs/01-prd.md) | 产品需求 (做什么 + 为什么) |
| [specs/02-architecture.md](specs/02-architecture.md) | 未来架构设计 (目标态) |
| [specs/04-architecture-current.md](specs/04-architecture-current.md) | 当前实际架构 (改代码看这个) |
| [specs/progress.md](specs/progress.md) | 进度快照 + 踩坑清单 |
| [docs/interview-highlights.md](docs/interview-highlights.md) | 6 个面试亮点总结 |

---

## 致谢

- [qwen-agent](https://github.com/QwenLM/Qwen-Agent) — 多 Agent 框架
- [MiniMax M3](https://api.minimaxi.com/) — OpenAI 兼容 LLM API
- [Gradio](https://gradio.app/) — Web UI
- [高德地图 MCP](https://lbs.amap.com/) — 位置 / 天气数据

---

## License

MIT