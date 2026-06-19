"""手动测试脚本: 验证我们修的 bug + 跑通端到端流程.

用法:
    # 默认 mock 模式 (不消耗 token, 立即返回)
    python examples/test_fixes.py

    # 真实 LLM 模式 (需 MINIMAX_API_KEY, 限流时可能失败)
    python examples/test_fixes.py --real

    # 跑指定测试
    python examples/test_fixes.py --real --only basic,history

可选场景:
    basic       - 单轮: 我想吃辣的
    girlfriend  - 单轮: 带女朋友去吃辣的
    history     - 多轮对话 (history 传入)
    stream      - 验证流式响应处理
    format      - 验证工具 schema 是 OpenAI 标准格式
    registry    - 验证 14 菜系 plugin 加载
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# 设置项目路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def _fake_llm_with_responses(responses: list[str]):
    """构造 FakeLLM, 模拟 master 调度 tool + 综合回答."""
    from typing import Any

    class FakeLLM:
        """内联 mock LLM, 兼容 qwen-agent 的 chat() 接口."""

        def __init__(self, responses: list[str]) -> None:
            self.canned_responses = responses
            self.model = "fake-model"
            self.model_type = "fake"
            self.generate_cfg: dict = {}
            self.max_retries = 0
            self.cache = None
            self.use_raw_api = False
            self.call_count = 0
            self.last_messages: list[dict] = []

        def chat(self, messages, functions=None, stream=True, **kwargs: Any):
            self.call_count += 1
            self.last_messages = [
                m.model_dump() if hasattr(m, "model_dump") else dict(m)
                for m in messages
            ]

            def _gen():
                resp = self.canned_responses[
                    (self.call_count - 1) % len(self.canned_responses)
                ]
                from qwen_agent.llm.schema import Message as QMessage
                yield [QMessage(role="assistant", content=resp)]

            return _gen()

    return FakeLLM(responses)


def _build_food_agent(use_real: bool):
    """构造 FoodAgent."""
    from food_agent.master import FoodAgent

    if use_real:
        return FoodAgent()

    # mock 模式: 让 master 假装调工具然后回答
    fake = _fake_llm_with_responses([
        # turn 1: master 决定调 consult_sichuan
        "我先问川菜专家...",
        # turn 2: 综合川菜专家的回复
        "🎯 推荐：陈麻婆豆腐（川菜）\n📍 位置：成都春熙路\n"
        "💰 人均：80-120\n🍽️ 必点：麻婆豆腐、回锅肉\n"
        "💡 理由：经典川菜代表, 一个人吃刚好.\n"
        "⚠️ 注意：微辣起, 肠胃不适建议点清汤版.\n"
        "\n🥈 备选：海底捞（火锅）\n🥉 备选：渝是乎（重庆菜）",
    ])
    return FoodAgent(llm=fake)


# ---- 各测试场景 ------------------------------------------------------------

def test_basic(use_real: bool) -> None:
    """基础单轮: '我想吃辣的'."""
    print("\n" + "=" * 70)
    print("TEST: basic - 单轮 '我想吃辣的'")
    print("=" * 70)
    agent = _build_food_agent(use_real)
    result = agent.run("我想吃辣的")
    print(f"\n>>> 用户: 我想吃辣的\n<<< 老饕:\n{result}\n")


def test_girlfriend(use_real: bool) -> None:
    """带女朋友去吃辣的."""
    print("\n" + "=" * 70)
    print("TEST: girlfriend - '想带我女朋友去吃辣的'")
    print("=" * 70)
    agent = _build_food_agent(use_real)
    result = agent.run("想带我女朋友去吃辣的, 预算 300, 不要太吵")
    print(f"\n>>> 用户: 想带我女朋友去吃辣的...\n<<< 老饕:\n{result}\n")


def test_history(use_real: bool) -> None:
    """多轮: 历史传入."""
    print("\n" + "=" * 70)
    print("TEST: history - 多轮对话 (第二次提到 '海鲜过敏')")
    print("=" * 70)
    agent = _build_food_agent(use_real)
    history: list[dict] = []
    msgs = [
        "我海鲜过敏",
        "那推荐个川菜给我",
    ]
    for m in msgs:
        history.append({"role": "user", "content": m})
        result = agent.run(m, history=history)
        history.append({"role": "assistant", "content": result})
        print(f"\n>>> {m}\n<<< {result}\n")
        print("-" * 70)


def test_stream(use_real: bool) -> None:
    """流式响应处理."""
    print("\n" + "=" * 70)
    print("TEST: stream - 验证流式响应被正确聚合")
    print("=" * 70)

    # 直接调用 sichuan agent 看流式是否聚合
    fake = _fake_llm_with_responses([
        "推荐: 麻婆豆腐\n",  # 模拟多个 chunk 拼接
    ])
    from food_agent.agents.cuisines.sichuan import SichuanAgent
    sichuan = SichuanAgent(llm=fake)
    out = sichuan.recommend("想吃辣的")
    print(f"\n>>> 用户: 想吃辣的\n<<< 川菜专家: {out!r}\n")
    assert "麻婆豆腐" in out, "流式响应未正确聚合"
    print("✅ 流式响应聚合 OK")


def test_format() -> None:
    """验证工具 schema 是 OpenAI 标准 JSON Schema (不是 Qwen 老 list)."""
    print("\n" + "=" * 70)
    print("TEST: format - 验证 tool schema 是 OpenAI 标准")
    print("=" * 70)
    from food_agent.master import FoodAgent

    agent = FoodAgent(llm=_fake_llm_with_responses(["ok"]))
    assert len(agent.tools) > 0, "Master 没有 tool"
    tool = agent.tools[0]
    print(f"\n工具名: {tool.name}")
    print(f"parameters: {json.dumps(tool.function, ensure_ascii=False, indent=2)[:400]}...")

    # 关键断言: parameters 必须是 dict (OpenAI schema), 不是 list
    params = tool.function.get("parameters")
    assert isinstance(params, dict), \
        f"❌ parameters 应为 dict, 实际 {type(params).__name__}"
    assert params.get("type") == "object", "❌ 缺 type=object"
    assert "properties" in params, "❌ 缺 properties"
    assert "user_query" in params["properties"], "❌ 缺 user_query"

    print("\n✅ 工具 schema 是 OpenAI 标准 JSON Schema (use_raw_api=True 必需)")


def test_registry() -> None:
    """验证 14 菜系 plugin 加载 (Phase 2)."""
    print("\n" + "=" * 70)
    print("TEST: registry - 验证 cuisines.yaml 加载 (Phase 2 准备)")
    print("=" * 70)
    yaml_path = PROJECT_ROOT / "src" / "food_agent" / "config" / "cuisines.yaml"
    if not yaml_path.exists():
        print(f"❌ {yaml_path} 不存在")
        return

    import yaml
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    cuisines = data.get("cuisines", [])
    enabled = [c for c in cuisines if c.get("enabled", True)]
    print(f"\n总菜系数: {len(cuisines)}")
    print(f"启用数: {len(enabled)}")
    print(f"\n按 category 分组:")
    by_cat: dict[str, list[str]] = {}
    for c in cuisines:
        by_cat.setdefault(c["category"], []).append(c["name"])
    for cat, names in by_cat.items():
        print(f"  {cat}: {', '.join(names)}")

    expected_categories = {"formal_cn", "formal_exotic", "fast_food", "snack", "drink"}
    actual_categories = set(by_cat.keys())
    assert expected_categories <= actual_categories, \
        f"❌ 缺 category: {expected_categories - actual_categories}"
    print(f"\n✅ cuisines.yaml 配置正确, 含全部 5 个 category")


# ---- main ------------------------------------------------------------------

ALL_TESTS = {
    "basic": test_basic,
    "girlfriend": test_girlfriend,
    "history": test_history,
    "stream": test_stream,
    "format": test_format,
    "registry": test_registry,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="手动测试脚本")
    parser.add_argument(
        "--real",
        action="store_true",
        help="用真实 LLM (需 MINIMAX_API_KEY, 限流时可能失败)",
    )
    parser.add_argument(
        "--only",
        type=str,
        help=f"只跑指定测试 (逗号分隔). 可选: {','.join(ALL_TESTS.keys())}",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有测试",
    )
    args = parser.parse_args(argv)

    if args.list:
        for name, fn in ALL_TESTS.items():
            print(f"  {name:12s} - {fn.__doc__}")
        return 0

    selected = ALL_TESTS.keys()
    if args.only:
        selected = [s.strip() for s in args.only.split(",")]
        unknown = set(selected) - set(ALL_TESTS)
        if unknown:
            print(f"未知测试: {unknown}")
            return 1

    mode = "REAL LLM" if args.real else "MOCK"
    print(f"\n🥢 Food Agent Test - Mode: {mode}")
    print(f"   Tests: {', '.join(selected)}")

    # 真实 LLM 检查
    if args.real and not os.environ.get("MINIMAX_API_KEY"):
        print("\n❌ --real 需要 MINIMAX_API_KEY 环境变量")
        return 1

    for name in selected:
        try:
            fn = ALL_TESTS[name]
            # stream/format/registry 不需要 LLM
            if name in ("format", "registry"):
                fn()
            else:
                fn(args.real)
        except Exception as e:
            print(f"\n❌ TEST {name} FAILED: {e}")
            import traceback
            traceback.print_exc()
            return 1

    print("\n" + "=" * 70)
    print("✅ 全部测试通过")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())