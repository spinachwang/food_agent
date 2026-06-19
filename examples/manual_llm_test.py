"""交互式 LLM 调用测试 - 你可以逐个跑或改.

每个测试是一个独立函数, 跑哪个就把其它的注释掉.
所有测试用真实 MiniMax M3 API, 限流时会失败.

用法:
    python examples/manual_llm_test.py          # 跑全部
    python examples/manual_llm_test.py t1       # 只跑 t1 (test_api_health)
    python examples/manual_llm_test.py t1 t3   # 跑 t1 和 t3
    python examples/manual_llm_test.py --list  # 列出所有
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def _check_key() -> bool:
    """检查 API key 是否就绪."""
    if not os.environ.get("MINIMAX_API_KEY"):
        print("❌ MINIMAX_API_KEY 未设置")
        return False
    return True


def _client():
    """构造 OpenAI 客户端."""
    from openai import OpenAI

    return OpenAI(
        api_key=os.environ["MINIMAX_API_KEY"],
        base_url=os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1"),
    )


def _safe_print(s: str) -> None:
    """安全打印, 避免 Windows gbk 报错."""
    try:
        print(s)
    except UnicodeEncodeError:
        # 把不能编码的字符替换为 ?
        encoding = sys.stdout.encoding or "utf-8"
        print(s.encode(encoding, errors="replace").decode(encoding))


# =============================================================================
# t1: API 健康检查 - 简单对话
# =============================================================================
def t1() -> bool:
    """最简单的 API 调用, 验证网络 + key + 模型可用."""
    print("\n" + "=" * 70)
    print("t1: API 健康检查 - 简单对话")
    print("=" * 70)

    if not _check_key():
        return False

    c = _client()
    start = time.time()
    try:
        r = c.chat.completions.create(
            model="MiniMax-M3",
            messages=[{"role": "user", "content": "用一句话介绍你自己"}],
            max_tokens=100,
            stream=False,
        )
        elapsed = time.time() - start
        content = r.choices[0].message.content
        print(f"\n[OK] 用时 {elapsed:.1f}s")
        print(f"模型: {r.model}")
        print(f"tokens: {r.usage.total_tokens if r.usage else '?'}")
        _safe_print(f"回复: {content}")
        return True
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n[FAIL] 用时 {elapsed:.1f}s: {e}")
        return False


# =============================================================================
# t2: 流式调用测试
# =============================================================================
def t2() -> bool:
    """流式响应, 验证 chunk 累积."""
    print("\n" + "=" * 70)
    print("t2: 流式调用")
    print("=" * 70)

    if not _check_key():
        return False

    c = _client()
    start = time.time()
    try:
        stream = c.chat.completions.create(
            model="MiniMax-M3",
            messages=[{"role": "user", "content": "用 3 句话介绍北京"}],
            max_tokens=200,
            stream=True,
        )
        full = ""
        chunks = 0
        for chunk in stream:
            chunks += 1
            if chunk.choices and chunk.choices[0].delta.content:
                full += chunk.choices[0].delta.content
        elapsed = time.time() - start
        print(f"\n[OK] 用时 {elapsed:.1f}s, {chunks} chunks")
        _safe_print(f"完整回复: {full}")
        return True
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n[FAIL] 用时 {elapsed:.1f}s: {e}")
        return False


# =============================================================================
# t3: 单轮 tool_call 测试
# =============================================================================
def t3() -> bool:
    """让 LLM 决定调一个 tool, 看返回的 tool_call 是否合法."""
    print("\n" + "=" * 70)
    print("t3: 单轮 tool_call")
    print("=" * 70)

    if not _check_key():
        return False

    c = _client()
    start = time.time()
    try:
        r = c.chat.completions.create(
            model="MiniMax-M3",
            messages=[{"role": "user", "content": "我想吃辣的, 一个人, 预算 100"}],
            tools=[{
                "type": "function",
                "function": {
                    "name": "consult_sichuan",
                    "description": "向川菜专家咨询. 适合: 想吃辣/重口味/聚餐/夜宵/天气冷.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_query": {
                                "type": "string",
                                "description": "用户问题",
                            },
                            "context": {
                                "type": "string",
                                "description": "8 维分析约束 JSON",
                            },
                        },
                        "required": ["user_query"],
                    },
                },
            }],
            stream=False,
        )
        elapsed = time.time() - start
        choice = r.choices[0]
        msg = choice.message

        print(f"\n[OK] 用时 {elapsed:.1f}s")
        print(f"finish_reason: {choice.finish_reason}")
        print(f"content: {msg.content!r}")
        print(f"tool_calls: {len(msg.tool_calls) if msg.tool_calls else 0}")

        if msg.tool_calls:
            for i, tc in enumerate(msg.tool_calls):
                args = tc.function.arguments
                print(f"\n--- tool_call[{i}] ---")
                print(f"  id: {tc.id}")
                print(f"  name: {tc.function.name}")
                print(f"  args raw: {args!r}")
                # 验证 JSON
                try:
                    parsed = json.loads(args)
                    print(f"  args parsed: {json.dumps(parsed, ensure_ascii=False)}")
                    print("  [VALID JSON ✅]")
                except Exception as ex:
                    print(f"  [INVALID JSON ❌] {ex}")
        return True
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n[FAIL] 用时 {elapsed:.1f}s: {e}")
        return False


# =============================================================================
# t4: 两轮 tool_call (call + result) - 这是 qwen-agent 第二轮做的事
# =============================================================================
def t4() -> bool:
    """完整两轮: LLM 调 tool → 我们塞结果 → LLM 综合回答.

    这模拟 qwen-agent 的关键路径. 如果这里过了说明 API + schema 都没问题.
    """
    print("\n" + "=" * 70)
    print("t4: 两轮 tool_call (call + result)")
    print("=" * 70)

    if not _check_key():
        return False

    c = _client()
    start = time.time()

    TOOL_SCHEMA = {
        "type": "function",
        "function": {
            "name": "consult_sichuan",
            "description": "向川菜专家咨询. 适合: 想吃辣/重口味/聚餐/夜宵/天气冷.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_query": {"type": "string", "description": "用户问题"},
                    "context": {"type": "string", "description": "约束 JSON"},
                },
                "required": ["user_query"],
            },
        },
    }

    try:
        # ---- turn 1: user → tool_call ----
        r1 = c.chat.completions.create(
            model="MiniMax-M3",
            messages=[
                {"role": "system", "content": "你是美食家. 需要时调用 consult_sichuan 工具. 综合后用中文回答."},
                {"role": "user", "content": "我想吃辣的"},
            ],
            tools=[TOOL_SCHEMA],
            stream=False,
        )
        msg1 = r1.choices[0].message
        print(f"\nturn 1 finish_reason: {r1.choices[0].finish_reason}")
        if not msg1.tool_calls:
            print(f"[FAIL] turn 1 没返回 tool_call, content: {msg1.content!r}")
            return False

        tc = msg1.tool_calls[0]
        args1 = json.loads(tc.function.arguments)
        print(f"turn 1 tool_call: {tc.function.name}({args1})")

        # ---- 模拟 tool 执行 ----
        tool_result = (
            "【川菜专家回复】\n"
            "推荐: 陈麻婆豆腐 (成都春熙路总店)\n"
            "必点: 麻婆豆腐、回锅肉、夫妻肺片\n"
            "辣度: 中辣 (3/5)\n"
            "人均: 80-120 元\n"
            "适合: 一个人, 预算 100"
        )
        print(f"\n[模拟 tool 执行] 返回: {tool_result[:50]}...")

        # ---- turn 2: tool_call + tool_result → final answer ----
        messages_2 = [
            {"role": "system", "content": "你是美食家. 需要时调用 consult_sichuan 工具. 综合后用中文回答."},
            {"role": "user", "content": "我想吃辣的"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }],
            },
            {
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_result,
            },
        ]
        r2 = c.chat.completions.create(
            model="MiniMax-M3",
            messages=messages_2,  # type: ignore[arg-type]
            tools=[TOOL_SCHEMA],
            stream=False,
        )
        msg2 = r2.choices[0].message
        elapsed = time.time() - start
        print(f"\nturn 2 finish_reason: {r2.choices[0].finish_reason}")
        print(f"turn 2 content: {msg2.content[:200] if msg2.content else None!r}")
        if msg2.content:
            print(f"\n[OK] 用时 {elapsed:.1f}s, 综合回答非空")
            _safe_print(f"回复预览: {msg2.content[:150]}...")
            return True
        print(f"\n[FAIL] turn 2 content 为空")
        return False
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n[FAIL] 用时 {elapsed:.1f}s: {e}")
        return False


# =============================================================================
# t5: qwen-agent 直接调用 (用我们修过的 use_raw_api=True)
# =============================================================================
def t5() -> bool:
    """用我们的 FoodAgent 跑一遍, 验证 use_raw_api + OpenAI schema 修复有效."""
    print("\n" + "=" * 70)
    print("t5: qwen-agent FoodAgent.run('我想吃辣的')")
    print("=" * 70)

    if not _check_key():
        return False

    from food_agent.master import FoodAgent

    agent = FoodAgent()  # 使用默认 get_llm_cfg() (已含 use_raw_api=True)
    start = time.time()
    try:
        result = agent.run("我想吃辣的")
        elapsed = time.time() - start
        print(f"\n[OK] 用时 {elapsed:.1f}s")
        _safe_print(f"老饕回复: {result[:300]}")
        return True
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n[FAIL] 用时 {elapsed:.1f}s: {e}")
        return False


# =============================================================================
# t6: Tool schema 静态检查 (不需要 API)
# =============================================================================
def t6() -> bool:
    """检查我们的 tool schema 是 OpenAI 标准 JSON Schema."""
    print("\n" + "=" * 70)
    print("t6: 静态检查 tool schema")
    print("=" * 70)

    from food_agent.master import FoodAgent
    from tests.test_cuisine_agent import FakeLLM

    agent = FoodAgent(llm=FakeLLM(["ok"]))
    if not agent.tools:
        print("[FAIL] 没有 tool")
        return False

    tool = agent.tools[0]
    schema = tool.function
    print(f"\n工具: {schema['name']}")
    print(f"parameters type: {type(schema['parameters']).__name__}")

    if not isinstance(schema["parameters"], dict):
        print(f"[FAIL] parameters 应为 dict, 实际 {type(schema['parameters']).__name__}")
        return False
    if schema["parameters"].get("type") != "object":
        print("[FAIL] 缺 type=object")
        return False
    if "user_query" not in schema["parameters"].get("properties", {}):
        print("[FAIL] 缺 user_query")
        return False
    if "user_query" not in schema["parameters"].get("required", []):
        print("[FAIL] user_query 不在 required")
        return False

    print("[OK] schema 是 OpenAI 标准 JSON Schema")
    return True


# =============================================================================
# t7: Tool schema 完整 dump (用 hex 看编码)
# =============================================================================
def t7() -> bool:
    """把 tool schema 完整 dump 出来, hex 看编码是否正确."""
    print("\n" + "=" * 70)
    print("t7: Tool schema hex dump")
    print("=" * 70)

    from food_agent.master import FoodAgent
    from tests.test_cuisine_agent import FakeLLM

    agent = FoodAgent(llm=FakeLLM(["ok"]))
    tool = agent.tools[0]
    schema = tool.function
    text = json.dumps(schema, ensure_ascii=False)
    print(f"\n--- schema (UTF-8) ---")
    _safe_print(text)
    print(f"\n--- hex dump (前 300 字节) ---")
    print(text.encode("utf-8")[:300].hex())
    return True


# =============================================================================
# 入口
# =============================================================================
ALL_TESTS = {
    "t1": ("API 健康检查 (单轮对话)", t1),
    "t2": ("流式调用", t2),
    "t3": ("单轮 tool_call", t3),
    "t4": ("两轮 tool_call (call + result)", t4),
    "t5": ("FoodAgent.run() 端到端", t5),
    "t6": ("静态检查 tool schema", t6),
    "t7": ("Tool schema hex dump", t7),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="手动 LLM 测试 (每个测试独立可跑, 限流时 t1-t5 会失败, t6/t7 不需要 API)",
    )
    parser.add_argument(
        "tests",
        nargs="*",
        help="要跑的测试 ID (e.g. t1 t3). 不传跑全部",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="列出所有测试",
    )
    args = parser.parse_args(argv)

    if args.list or not args.tests:
        print("\n可用测试:\n")
        for tid, (desc, _) in ALL_TESTS.items():
            api_note = "(不需要 API)" if tid in ("t6", "t7") else "(需要 API)"
            print(f"  {tid:5s}  {desc:35s} {api_note}")
        print("\n推荐顺序: t1 → t2 → t3 → t4 → t5")
        print("  t1 健康检查 → t2 流式 → t3 tool_call → t4 两轮 → t5 端到端")
        print("  t6/t7 静态检查, 不需要 API")
        if not args.tests:
            return 0

    selected = args.tests
    unknown = set(selected) - set(ALL_TESTS)
    if unknown:
        print(f"未知测试: {unknown}")
        return 1

    print(f"\n🥢 Food Agent - 手动 LLM 测试")
    print(f"   Mode: 真实 API (key: {'已设置' if os.environ.get('MINIMAX_API_KEY') else '未设置'})")
    print(f"   Tests: {', '.join(selected)}")

    results: dict[str, bool] = {}
    for tid in selected:
        desc, fn = ALL_TESTS[tid]
        try:
            results[tid] = fn()
        except KeyboardInterrupt:
            print(f"\n[{tid}] 中断")
            results[tid] = False
        except Exception as e:
            print(f"\n[{tid}] CRASH: {e}")
            import traceback
            traceback.print_exc()
            results[tid] = False

    print("\n" + "=" * 70)
    print("结果汇总")
    print("=" * 70)
    for tid, (desc, _) in ALL_TESTS.items():
        if tid in results:
            mark = "✅" if results[tid] else "❌"
            print(f"  {mark} {tid:5s}  {desc}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())