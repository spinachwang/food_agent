"""短期记忆: 滑动窗口 + token 阈值触发 LLM 摘要.

Phase 2.5.

职责:
- 维护会话内最近的消息
- 超过 max_messages 自动截断最早的
- 超过 summarize_after_tokens 自动调 LLM 摘要前段
- 摘要失败 → 降级硬截断 (不抛异常给上层)

Token 估算: chars/4 (不引入 tiktoken, 跨语言粗估足够).

集成: FoodAgent.run(session_id=...) 每次 run 自动 add user/assistant
消息到 ShortTermMemory, 并在 should_summarize 时触发摘要.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ShortTermMemory:
    """会话级短期记忆.

    Attributes:
        max_messages: 滑动窗口上限. 超出会自动截断最早.
        summarize_after_tokens: token 估算阈值. 超出会触发 summarize().
        keep_last_n_after_summary: 摘要后保留的最近 N 条消息.
    """

    max_messages: int = 30
    summarize_after_tokens: int = 6000
    keep_last_n_after_summary: int = 6

    _messages: list[dict] = field(default_factory=list, init=False, repr=False)
    _summary: str | None = field(default=None, init=False, repr=False)

    # ---- 读写 ----

    def add(self, msg: dict) -> None:
        """添加一条消息.

        Args:
            msg: {"role": "user|assistant|system|tool", "content": str, ...}

        Raises:
            TypeError: msg 不是 dict.
            ValueError: msg 缺 role 字段.
        """
        if not isinstance(msg, dict):
            raise TypeError(f"msg must be dict, got {type(msg).__name__}")
        if "role" not in msg:
            raise ValueError(f"msg must have 'role' field: {msg!r}")
        self._messages.append(msg)
        # 滑动窗口: 超 max_messages 截断最早
        if len(self._messages) > self.max_messages:
            self._messages = self._messages[-self.max_messages:]

    def get_messages(self) -> list[dict]:
        """返回完整 messages.

        有 summary 时, 第一个元素是 system summary, 后面是 _messages.
        无 summary 时, 就是 _messages 副本.
        """
        if self._summary:
            return [{"role": "system", "content": self._summary}, *self._messages]
        return list(self._messages)

    def clear(self) -> None:
        """清空消息和 summary."""
        self._messages = []
        self._summary = None

    def __len__(self) -> int:
        return len(self._messages)

    # ---- token 估算 ----

    def _estimate_tokens(self) -> int:
        """粗估: 所有消息的 content 字符数 / 4."""
        total = 0
        for m in self._messages:
            content = m.get("content", "")
            if isinstance(content, str):
                total += len(content)
            elif isinstance(content, list):
                # 多模态: 拼所有 text
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        total += len(str(item["text"]))
                    elif hasattr(item, "text"):
                        total += len(str(item.text))
        # summary 也算 token (因为会作为 system 消息发出去)
        if self._summary:
            total += len(self._summary)
        return total // 4

    def should_summarize(self) -> bool:
        """token 估算超阈值 → True."""
        return self._estimate_tokens() >= self.summarize_after_tokens

    # ---- 摘要 ----

    def summarize(self, llm_cfg: Any) -> None:
        """调 LLM 摘要前段消息, 保留最近 N 条.

        行为:
        - 消息数 ≤ keep_last_n_after_summary → noop (不调 LLM)
        - 调 LLM 成功 → 设置 self._summary, 截断 _messages 到最近 N
        - 调 LLM 失败 → logger.warning + 硬截断到最近 N, _summary 保持 None

        Args:
            llm_cfg: qwen-agent LLM 配置 (dict) 或 BaseChatModel 实例.
        """
        if len(self._messages) <= self.keep_last_n_after_summary:
            return

        to_summarize = self._messages[:-self.keep_last_n_after_summary]
        keep = list(self._messages[-self.keep_last_n_after_summary:])

        convo_text = "\n".join(
            f"[{m.get('role', '?')}] {m.get('content', '')}" for m in to_summarize
        )
        prompt = (
            "请用 200 字以内总结以下对话的关键信息。"
            "重点: 用户偏好、决定的餐厅或菜品、重要约束条件（预算/场景/忌口）。\n\n"
            f"{convo_text}"
        )

        try:
            summary = self._call_llm_for_summary(llm_cfg, prompt)
            if summary:
                self._summary = summary
            self._messages = keep
        except Exception as e:
            logger.warning("summarize failed, hard-truncating: %s", e)
            self._messages = keep
            # 不设置 _summary

    def _call_llm_for_summary(self, llm_cfg: Any, prompt: str) -> str:
        """调 LLM 拿摘要文本. 失败抛异常 (给 summarize 处理)."""
        from qwen_agent.llm import get_chat_model
        from qwen_agent.llm.schema import Message

        # llm_cfg 可能是 dict 配置或 BaseChatModel 实例
        if isinstance(llm_cfg, dict):
            llm = get_chat_model(llm_cfg)
        else:
            llm = llm_cfg

        msgs = [Message(role="user", content=prompt)]
        # chat 返回 generator of [Message]
        responses = list(llm.chat(msgs, stream=False))
        if not responses:
            return ""
        # responses[0] 是 list[Message], 取第一个 assistant content
        batch = responses[0]
        if isinstance(batch, list) and batch:
            return self._extract_content(batch[0])
        if isinstance(batch, Message):
            return self._extract_content(batch)
        return ""

    @staticmethod
    def _extract_content(msg: Any) -> str:
        """从 qwen-agent Message 提取 content 文本."""
        if isinstance(msg, str):
            return msg
        if isinstance(msg, dict):
            return msg.get("content", "") or ""
        content = getattr(msg, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    parts.append(str(item["text"]))
                elif hasattr(item, "text"):
                    parts.append(str(item.text))
            return "".join(parts)
        return str(content)


__all__ = ["ShortTermMemory"]
