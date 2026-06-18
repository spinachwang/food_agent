# 02 - Architecture

> 整体架构。代码落地参考 [plan 文件](../../../../../../Users/PC/.claude/plans/agent-agent-agent-agent-1-golden-kahn.md)。

## 1. 设计原则

1. **可插拔优先** - 新增菜系/分析器不改 master 代码
2. **错误显式** - 工具失败不静默，自动降级但可观测
3. **MCP 抽象** - 外部数据走 MCP server，未来换 API 不动 Agent
4. **不可变数据** - 偏好/消息全 append-only，便于审计
5. **测试友好** - 所有 LLM 调用可 mock，CI 不消耗 token

## 2. 模块划分

```
src/food_agent/
├── master.py          # 主 Agent 入口（FoodAgent 类）
├── llm.py             # LLM 配置（MiniMax M3 OpenAI 兼容）
├── registry.py        # 动态加载菜系/分析器
├── cli.py / web.py    # 入口
├── config/
│   ├── settings.yaml  # 全局配置
│   ├── cuisines.yaml  # 菜系清单（plugin 入口）
│   └── prompts/       # system prompt 模板（git 版本管理）
├── agents/
│   ├── base.py        # BaseCuisineAgent 抽象
│   ├── cuisines/      # 14 个菜系专家
│   └── analyzers/     # 8 维分析器
├── tools/             # 自定义 Tool（含 RobustToolCaller）
├── skills/            # 复合能力（多步）
├── memory/            # 短期 + 长期 + 摘要
├── mcp/               # MCP server 实现 + 配置
├── data/              # Mock 数据 + 知识库
├── utils/             # retry / breaker / cache / tracing
└── exceptions.py
```

## 3. 数据流

### 3.1 单轮推荐

```
[用户输入]
   ↓
[CLI / Web]
   ↓
[FoodAgent.run(user_msg, history)]
   ↓
   ├─→ [extract_preference skill]  ← 短期记忆
   │     输出: {cuisine_hints, price, taste, mood, occasion, ...}
   │
   ├─→ [8 维 Analyzer 并行]
   │     ├─ price, taste, weather(MCP), mood,
   │     ├─ occasion, time, location, dietary
   │     输出: structured constraints
   │
   ├─→ [dispatch_cuisine skill]
   │     根据约束选 1-3 个菜系（按 category 过滤）
   │
   ├─→ [并行调用 1-3 个菜系专家]
   │     每个 expert 输出: top 3 候选餐厅 + 理由
   │
   ├─→ [synthesize_recommendation skill]
   │     综合 → Top 3 + 推荐理由 + 下一步建议
   │
   └─→ [持久化]
         ├─ 短期记忆追加
         └─ 长期偏好更新（用户反馈）
   ↓
[流式输出给用户]
```

### 3.2 工具失败处理流

```
[Tool Call]
   ↓
[RobustToolCaller.call]
   ↓
   ├─ [Circuit Breaker 通过？]
   │     NO  → [降级到 fallback tool]
   │     YES ↓
   ├─ [尝试调用] ── 失败 ──→ [重试 (指数退避)]
   │     ↑                       ↓
   │     └── 成功 ←────── 重试 ≤ max_retries
   ↓
[返回结果 / 部分结果]
```

## 4. 数据模型概览

详见 [03-data-model.md](03-data-model.md)。关键实体：

| 实体 | 存储 | 生命周期 |
|---|---|---|
| `Session` | 内存 + 可选持久化 | 单次会话 |
| `Message` | 短期记忆 | 会话内 |
| `UserPreference` | SQLite 长期 | 跨会话 |
| `Recommendation` | 短期 | 单次推荐 |
| `Cuisine` | YAML 配置 | 静态 |
| `Restaurant` | Mock JSON / MCP | 静态 |

## 5. 关键依赖

| 模块 | 依赖 |
|---|---|
| Master Agent | qwen-agent.Assistant, LLM cfg |
| Sub-Agent 包装 | qwen-agent.BaseTool |
| MCP | mcp (Python SDK) |
| 记忆 | SQLite (stdlib) |
| 缓存 | diskcache |
| 重试 | tenacity + pybreaker |
| Web | gradio |
| CLI | rich |

## 6. 部署形态

本地运行，无服务端：

```
food-agent (CLI)    ──→  本地 LLM API (MiniMax M3)
food-agent-web      ──→  本地 LLM API + Gradio 浏览器
```

## 7. 安全 / 隐私

- API key 仅在 `.env`（gitignored）
- 用户偏好本地 SQLite，不上传
- 输入校验防 prompt injection
- 输出脱敏防手机号/身份证泄漏

---

## 修订记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-06-18 | v0.1 | 初稿 |
