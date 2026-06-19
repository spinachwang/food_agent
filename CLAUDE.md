# CLAUDE.md - Food Agent 项目指令

> 这是项目级指令，全局警示在 `~/.claude/CLAUDE.md`。

## 项目概览

`food-agent` 是一个基于 qwen-agent 的多 Agent 美食推荐系统。主 Agent（地球顶级美食家）调度 14 个菜系专家子 Agent，根据 8 维分析（价格/口味/天气/心情/场景/时段/位置/饮食限制）综合推荐。

**关键技术栈**：qwen-agent + MiniMax-M3 (OpenAI 兼容 API) + Gradio + SQLite + MCP

## 必读文件

开始任何任务前，先看：
- [plan 文件](C:/Users/PC/.claude/plans/agent-agent-agent-agent-1-golden-kahn.md) - 整体架构
- `specs/01-prd.md` - 产品需求
- `specs/02-architecture.md` - 架构设计（未来设计）
- `specs/04-architecture-current.md` - 当前已落地的架构（**实际改这个**）
- `specs/progress.md` - **当前进度快照**（每次开新会话先看这里）

## 当前进度 (2026-06-18)

```
✅ Phase 0: 项目初始化
✅ Phase 1: 单菜系 E2E (川菜)
   ├─ 60 个测试全过 (test_llm + test_master_agent + test_cuisine_*)
   ├─ Master ↔ Tool ↔ 子 Agent 链路跑通
   └─ 关键 bug 已修: qwen-agent tool_call_id patch
🚧 Phase 2: 多菜系 + 记忆系统 (下一步)
```

**关键事实（重要）**：
- 提示词位置：master → `config/prompts/master_v1.md`（文件），sichuan → `agents/cuisines/sichuan.py` 类属性（内联）
- 当前 8 维分析器是**空目录**（`agents/analyzers/` 还没文件）
- `config/settings.yaml` / `cuisines.yaml` 都还没 loader，Phase 2 任务
- 唯一接入的真实 LLM：MiniMax M3 (OpenAI 兼容)，用 `use_raw_api=True` 走原生 tool_call 协议
- Web UI 是 stub，`python -m food_agent.web` 还没真接 Gradio

**新会话开起来**：
1. 读 `specs/progress.md`（自动包含本节更详细的清单）
2. 读 `specs/04-architecture-current.md`（理解实际代码怎么连）
3. 如果跑 `python -m food_agent "..."` 报 `tool result's tool id() not found`，**不要重新打补丁**——已在 `src/food_agent/llm.py` 启动时自动应用，详见 memory `qwen-agent-tool-call-id-patch`

## 开发约定

### TDD 工作流
1. **RED**: 先写失败的测试
2. **GREEN**: 写最小实现让测试通过
3. **REFACTOR**: 重构保持测试通过
4. **覆盖率**: `pytest --cov` ≥ 80%

### Git 工作流
- 分支命名：`feat/<scope>-<desc>` / `fix/<scope>` / `docs/...` / `refactor/...` / `test/...`
- 提交规范：Conventional Commits（`feat(memory): 添加短期摘要压缩`）
- 严禁：`git filter-repo`、`git filter-branch`、`git push --force`（参考全局警示）

### Python 环境
- 始终用 `conda run -n qwenagent-mcp python`（已在该 env 装好所有依赖）
- **禁止** 直接 `python` / `pip install` 到 base 或系统 Python

### 代码规范
- 不可变数据优先
- 函数 < 50 行，文件 < 800 行
- 错误显式处理（不静默吞）
- 公开函数加 docstring
- 中文注释可以，但标识符必须英文

## 目录约定

| 目录 | 用途 |
|---|---|
| `specs/` | SDD 文档（PRD/架构/数据模型/Skill 清单） |
| `src/food_agent/` | 主代码 |
| `src/food_agent/agents/cuisines/` | 14 个菜系专家 |
| `src/food_agent/agents/analyzers/` | 8 维分析器 |
| `src/food_agent/config/prompts/` | System prompt 版本管理 |
| `tests/` | pytest + mock LLM + VCR.py |
| `examples/` | 可运行的示例脚本 |

## 实施进度

详细进度见 TodoWrite。当前完成 Phase 0 部分。
