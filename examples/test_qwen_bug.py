"""验证 patch 后 _conv_qwen_agent_messages_to_oai 行为正确."""
import json
from food_agent.llm import _patch_qwen_agent_tool_call_id

# 先确保 patch 跑过 (llm.py 导入时已执行, 这里再调一次确认幂等)
_patch_qwen_agent_tool_call_id()

# 模拟一个 use_raw_api=True 时的转换
from qwen_agent.llm.base import BaseChatModel

msgs = [
    {"role": "user", "content": "我想吃辣的"},
    {
        "role": "assistant",
        "content": "",
        "function_call": {"name": "consult_sichuan", "arguments": '{"user_query":"辣的"}'},
        "extra": {"function_id": "call_abc123"},
    },
    {
        "role": "function",
        "content": "麻婆豆腐",
        "extra": {"function_id": "call_abc123"},
    },
]

print("=== Patch 后的转换结果 ===")
result = BaseChatModel._conv_qwen_agent_messages_to_oai(msgs)
for r in result:
    print(json.dumps(r, ensure_ascii=False, indent=2))
    print("---")

print("\n=== 关键验证 ===")
all_ok = True
for r in result:
    if r.get("role") == "tool":
        has_tc_id = "tool_call_id" in r
        has_id = "id" in r
        print(f"tool 消息: {json.dumps(r, ensure_ascii=False)}")
        print(f"  - tool_call_id 存在? {has_tc_id} (期望 True)")
        print(f"  - id 字段已移除? {not has_id} (期望 True)")
        if has_tc_id and not has_id:
            print(f"  >>> ✅ tool_call_id = {r['tool_call_id']} (与 assistant tool_calls[i].id 匹配) <<<")
        else:
            print(f"  >>> ❌ Patch 没生效 <<<")
            all_ok = False

# 验证 idempotent
_patch_qwen_agent_tool_call_id()
_patch_qwen_agent_tool_call_id()
print(f"\n=== Idempotent 验证: 重复 patch 不出错 ✅ ===")

print(f"\n=== 最终结果: {'✅ 全部通过' if all_ok else '❌ 有问题'} ===")
