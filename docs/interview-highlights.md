# 面试亮点 — food-agent 项目踩坑与设计决策

> 适用场景: 后端 / AI Agent / Python / LLM 应用 方向技术面试  
> 项目一句话: 基于 qwen-agent 的多 Agent 美食推荐系统 — 主 Agent (老饕) 调度 14 个菜系专家 + 8 维分析 (天气/位置/饮食限制等), 用 MiniMax M3 (OpenAI 兼容 API) + Gradio + SQLite + MCP 落地。

下面 6 个点是 session 里实际解决过、可代码佐证、可量化的问题。每个点都能讲 1-2 分钟。

---

## 1. LLM 主动承诺没接入的能力 — "外卖凑单"幻觉

**场景**: 用户说"我在杭州市钱塘区义蓬购物中心, 想吃炸鸡", 我刚接入 agent 时, 模型主动回了"要不给个外卖 vs 到店建议？外卖直接送到购物中心里, 还常有满减。要的话我帮你拟个外卖凑单思路～" —— 但**系统里压根没有外卖 tool**。这是 LLM 在 prompt 没声明边界时, 默认自己万能的典型幻觉。

**根因**: master prompt (`src/food_agent/config/prompts/master_v1.md`) 只列了"有什么工具" (analyze_weather / analyze_location / analyze_dietary + 14 菜系 expert), 没说"没有什么"。LLM 看到"购物中心 + 炸鸡"就脑补出"用户可能想点外卖", 用美食博主语料里常见的"帮你凑单"话术承诺了一个不存在的服务。

**修复** (commit `ae90789`):
1. **新增"能力边界"段** (16 行), 显式列 5 类做不到的事 (外卖/订座/付款/实时菜单/推送), 每个都给一句"我转人工"的替代话术模板 (例如 "点外卖的话, 你打开美团搜 '购物中心名 + 炸鸡' 自己挑")
2. **硬规则加一条兜底**: "❌ 工具做不了的事直说做不到, 别编造流程或编数据糊弄用户"
3. **加 2 个防回归测试** (`tests/test_master_agent.py`): 断言 prompt 文件结构包含"能力边界"段 + 包含"做不到/直说"类关键词

**反思 / 通用启示**: LLM 产品化的核心反直觉 — **模型没有"边界感"**, 必须在 prompt 里显式声明。**漏检比过检更危险**: 跟过敏原识别同一个哲学 — 不确定的宁可让用户去美团搜, 也不要瞎承诺凑单。测试要钉死 prompt 的合同, 不能等模型"飘了"才发现。

---

## 2. 22 个 tool 把 LLM 撑爆, 倒推架构改造

**场景**: Phase 3.5 前, master LLM 看到 22 个 tool (14 菜系 + 5 location 原始 + 3 analyzer)。实测发现 LLM 选择混乱, 经常调错工具或漏调。

**根因**: Toolformer 论文建议 LLM function calling 一次性候选 ≤10 个。22 个远超过这个阈值, LLM 的 attention 分散, 选择质量断崖式下降。

**修复** (commit `ec8f74d`): **从 prompt 设计倒推架构改造**, 不是改 prompt 写得更好, 而是把架构本身改了:
- 5 个 location tool (geocode / regeocode / search_around / weather / route) **不再直接暴露给 master**
- 改由 3 个 analyzer 内部调 AmapClient, master 只看到 14 菜系 + 3 analyzer = 17 tool
- 测试断言: `assert "geocode" not in tool_names` —— 钉死这个边界

**反思 / 通用启示**: 当 prompt 优化遇到瓶颈, 考虑**架构层面的简化**。"工具太多 LLM 选不好"不是 prompt 问题, 是接口设计问题。同时理解 LLM 的物理能力上限 (Toolformer 的 10 阈值) 才能做出正确的工程取舍。

---

## 3. dict / BaseChatModel 类型契约漏洞 — 静默降级

**场景**: CLI 默认用 `get_llm_cfg()` 返 `dict` (qwen-agent config), master 传给 dietary 工具时, dict 没 `.chat()` 方法。dietary 工具悄悄走了 **keyword fallback**, `like_preferences` 永远返回空数组。用户说"我喜欢吃辣, 干辣尤其喜欢" — 工具提示"like_preferences 是空的", 长期记忆里查不到偏好。

**根因**: type contract 没在 boundary 强制。`_llm` 可以是 dict 也可以是 BaseChatModel 实例, 但代码假设它是后者, 缺 .chat() 时**静默降级**到关键词匹配, 没报错也没日志。

**修复** (Phase B-2): 在 `master.py` 加 `_resolve_llm_instance()`, 在 init 时**统一包装**成 BaseChatModel 实例:
```python
def _resolve_llm_instance(llm: Any) -> Any:
    if isinstance(llm, dict):
        return get_chat_model(llm)
    return llm
```
+ 测试 `test_food_agent_dict_llm_wrapped_for_dietary`: monkey-patch `get_chat_model`, 验证 dict 进来、BaseChatModel 实例出去, 钉死 `dietary._llm is fake_instance`。

**反思 / 通用启示**: **静默降级是 bug 滋生的温床**。"工具失败要降级"是对的 (面向用户), 但**类型契约失败必须 loud failure**, 不能因为兼容 dict 就假装能跑。这种边界处的 runtime 类型差异, 单元测试断言 type 而不是行为更重要。

---

## 4. 第三方库的协议 bug — 启动时 monkey-patch 优雅兜底

**场景**: master → tool → master 第二轮 LLM 调用, MiniMax API 报 `invalid params, tool result's tool id() not found (2013)`, HTTP 400。整个多轮对话链路在第一轮 tool 调用后就崩。

**根因**: qwen-agent 0.0.34 在 `BaseChatModel._conv_qwen_agent_messages_to_oai()` 里, 把内部 `function` 角色转 OpenAI `tool` 角色时, 把 link id 写到了 `id` 字段; 而 OpenAI / MiniMax / GPT 等兼容 API 期望的是 `tool_call_id` 字段 —— 协议不一致。

**修复** (在 `src/food_agent/llm.py:31-66`):
```python
def _patch_qwen_agent_tool_call_id():
    """模块导入时自动执行 — 升级 qwen-agent 时必须回归验证."""
    # monkey-patch BaseChatModel._conv_qwen_agent_messages_to_oai
    # 转换后把 msg['id'] 重命名为 msg['tool_call_id']
    # 防御式: 若 upstream 已修, 自动变 no-op (不覆盖已有 tool_call_id)
    # 标记 _food_agent_tool_call_id_patched, 防止重复 patch
```
**为什么不动 vendor source**: 
1. `pip install --force-reinstall qwen-agent` 会冲掉所有本地修改
2. monkey-patch 改的是"我们与 qwen-agent 的集成层", 不是 vendor 代码
3. 升级时 diff 清晰, 一眼能看出 patch 是否还有必要

+ 5 个 patch 回归测试 (`tests/test_llm.py`): 钉死 patch 行为 + 幂等性 + 防御 upstream 已修的场景。

**反思 / 通用启示**: **升级依赖时踩坑, 优先在集成层打补丁, 不要 fork 改 vendor**。patch 要幂等、要防御式 (upstream 修了自动变 no-op)、要可观测 (有 `_patched` 标记)。这种"上游已知 bug 等不及"的情况, monkey-patch 是比 fork / 替换依赖都更可控的方案。

---

## 5. 用户没给地址时怎么办 — 缺数据场景的两层降级设计

**场景**: 用户说"今天想吃川菜"但没说在哪, 我之前会反复追问"你在哪个城市"。用户感觉烦, 体验差。

**根因**: 缺数据时直接问是最差的方案 —— 它打断了用户的思考流, 让对话变成"被盘问"。但完全不问, 又是基于模糊假设推荐 (全国通用推荐没意义)。

**修复** (commit `d95ba77`): **分两层降级**, 不是"二选一":
1. **有地址**: `analyze_location(用户消息, 可选 client_ip)` → IP 定位优先, 降级到地址解析 → 返回 `{city, lng, lat, 可选周边 POI}`, 一次拿全
2. **无地址**: `detect_location()` → web 场景高德根据访问者 HTTP IP 自动定位 (真实位置), CLI 场景用本机/出口 IP → 返回 `{city, lng, lat, source: 'ip', confidence}`, lng/lat 是城市中心近似值

明确写在 prompt 里: "都试过但 confidence=0 → 不强求, 用全国推荐 + 问用户所在城市"。

**反思 / 通用启示**: **数据缺失不是非黑即白**, 是连续的 confidence 值。好的产品要:
1. **能猜就猜** (IP 定位 / 上下文推断), 给出 best-effort 结果
2. **猜不准就明说** (标 confidence=0), 不要装权威
3. **最后才追问** (用户实在不给), 让对话尽量不中断

这是经典的多模态输入处理: 多源 fallback 比单源追问更优雅。

---

## 6. 意图抽取: 关键词正则不够, 走 LLM 抽取为主

**场景**: 用户说"我对花生过敏, 不喜欢甜的" / "我喜欢吃辣, 干辣尤其喜欢"。旧版 dietary 工具走纯关键词正则, "尤其喜欢" / "特别爱" 这类强调词没匹配, `like_preferences` 漏检率 50%+。

**根因**: 中文意图表达太灵活。"喜欢""爱吃""常点""必吃""我最爱" 都是同义, 关键词正则要枚举几十种变体, 还会跟"不喜欢"语义冲突。

**修复** (Phase B-2):
1. **走 LLM 抽取为主** (`DietaryAnalyzerTool.analyze()` 调用 self.llm.chat())
2. **关键词兜底为辅** (LLM 不可用时降级, 至少能跑通)
3. 抽取结构分 3 类: **硬约束** (allergy / religion, confidence=0.9) / **软偏好** (avoid, 0.7) / **喜欢偏好** (like, 0.7)
4. 写回 long_term 时带 `source="msg"` 标记, **不重复写已召回的偏好** (避免长期记忆膨胀)

**反思 / 通用启示**: **意图抽取是 LLM 比 regex 强得多的领域**, 不要为了"省 token"或"可控"硬走正则。漏检和过检要分等级:
- **硬约束漏检 → 出大事** (过敏用户被推荐含过敏原, 可能住院)
- **软偏好漏检 → 小事** (用户没看到喜欢的菜, 下次再说)
- **过检 → 一般** (多了个候选, 不致命)

所以**过敏/宗教必须 LLM 抽取 + 多轮验证**, **像喜欢这种可以 LLM 一次抽取**, **通用口味可以关键词**。分级处理是工程艺术。

---

## 7. REPL 自己管 history, 绕开了 STM 的压缩 — 已有基建要会用

**场景**: REPL (`python -m food_agent --chat`) 用户聊到第 20 轮, messages 列表已经塞了几十条, 但 `FoodAgent.run(history=history, ...)` 走的是调用方传 history 的路径, **没走 STM**, token 阈值 + LLM 摘要全失效。STM (`ShortTermMemory`) 这套本来能用的基建, 在用户最常接触的 REPL 入口完全闲置。

**根因**: master.py 的 `run()` 有两条历史注入路径 ——
```python
if history is not None:
    messages.extend(list(history))       # 调用方传, CLI REPL 走这条
elif session_id:
    stm = self._get_or_create_stm(session_id)
    messages.extend(stm.get_messages())  # STM 接管 + 摘要
```
CLI REPL 之前传 `history=`, 直接走第一条, **第二条连试都不试**。这不是 STM 的 bug, 是 CLI 没用对接口。**基建齐了没人用, 比没建更糟**。

**修复** (commit TBD):
1. CLI REPL 改传 `session_id=f"repl-{user_id}"`, 让 STM 接管 — 同一 user 复用同一 session, 不同 user 隔离
2. 加 `FoodAgent.clear_stm(session_id)` 方法 (幂等), CLI `reset` 命令调它清空会话
3. + 6 个测试钉死行为: REPL 不再传 history / session_id 复用 / 跨 user_id 隔离 / `clear_stm` 幂等 + 不影响其他 session

**反思 / 通用启示**: **代码可读性 vs 正确路径选择是两件事**。`history is not None` 这条路径存在是合理的 (给上层最大灵活度), 但 CLI 走错就是 bug。**接口设计的反模式: 多个互斥的 "我用这个" 入口, 没文档说哪个是默认**。修这种 bug 关键是写测试钉死"应该走哪条", 不靠 code review 偶发抓。**REPL 的 `reset` 也是典型的 "看似用户功能, 实际是开发者信号"** — 清空 STM 等于告诉你 "之前的设计错了"。

---

## 通用方法论收尾

这 7 个 case 共同体现了几个我反复用的工作习惯:

1. **先定位根因, 再写代码**: "外卖幻觉" 不是改一行 prompt 就完事, 是要理解 LLM 的认知边界 (没有边界感)。"22 tool 撑爆" 不是改 prompt 让模型更聪明, 是改架构让接口更简单。"REPL 没压缩" 不是给 REPL 加摘要逻辑, 是改 CLI 改用已有 STM。
2. **测试钉死 prompt 合同 + 路径选择**: prompt 是产品行为的一部分, "REPL 走 STM" 是接口合同的一部分, 都不是"配置文件随便改"。结构化测试 (断言 prompt 含/不含某些关键词, 断言 REPL 传哪个 kwarg) 能防升级/重构时悄悄退化。
3. **静默降级是 bug 滋生的温床**: 类型契约、库协议、意图抽取、接口选择 —— 任何"假装能用"或"用错接口假装没事"的地方, 都要么 loud failure, 要么有可观测的降级路径。
4. **vendor 代码别动, 集成层打补丁**: monkey-patch 是被低估的设计模式, 关键是幂等 + 防御 + 可观测。
5. **数据缺失是连续 confidence 值**: 不要二选一 (问 vs 不问), 多源 fallback + best-effort + 明说 confidence。
6. **基建齐了要会用**: STM/LTM/Amap/Analyzer — 这些模块都在, 但 CLI/REPL/Web 三条入口各自走什么路径, 必须有清晰约定。否则就是 "看起来啥都有, 实际 REPL 跑的还是裸奔"。

---

## 项目代码佐证 (按亮点编号)

| # | 文件 | Commit |
|---|---|---|
| 1 | `src/food_agent/config/prompts/master_v1.md:50-65` (能力边界段) + `tests/test_master_agent.py` (防回归) | `ae90789` |
| 2 | `src/food_agent/master.py:127-139` (tools 暴露控制) + `tests/test_master_agent.py` (assert geocode not in tools) | `ec8f74d` |
| 3 | `src/food_agent/master.py:59-77` (`_resolve_llm_instance`) + `tests/test_master_agent.py` (dict 包装断言) | Phase B-2 |
| 4 | `src/food_agent/llm.py:31-66` (`_patch_qwen_agent_tool_call_id`) + `tests/test_llm.py` (5 个 patch 回归) | Phase 1 bug fix |
| 5 | `src/food_agent/agents/analyzers/detect_location.py` + `master_v1.md:18-21` (调用策略) | `d95ba77` |
| 6 | `src/food_agent/agents/analyzers/dietary.py` (`analyze()` 走 LLM) + master.py:203-250 (写入 long_term) | Phase B-2 |
| 7 | `src/food_agent/cli.py:243-265` (REPL session_id) + `src/food_agent/master.py:186-193` (`clear_stm`) + 6 个测试钉死路径选择 | TBD |