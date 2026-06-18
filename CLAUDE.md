# CLAUDE.md - Food Agent 项目指令

> 这是项目级指令，全局警示在 `~/.claude/CLAUDE.md`。

## 项目概览

`food-agent` 是一个基于 qwen-agent 的多 Agent 美食推荐系统。主 Agent（地球顶级美食家）调度 14 个菜系专家子 Agent，根据 8 维分析（价格/口味/天气/心情/场景/时段/位置/饮食限制）综合推荐。

**关键技术栈**：qwen-agent + MiniMax-M3 (OpenAI 兼容 API) + Gradio + SQLite + MCP

## 必读文件

开始任何任务前，先看：
- [plan 文件](C:/Users/PC/.claude/plans/agent-agent-agent-agent-1-golden-kahn.md) - 整体架构
- `specs/01-prd.md` - 产品需求
- `specs/02-architecture.md` - 架构设计
- `specs/07-development-phases.md` - 阶段拆分

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
