"""上下文管理 - 支持持久化 + 自动裁剪 + 摘要注入"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Callable

try:
    from .context_store import get_context_store
except ImportError:
    from context_store import get_context_store


@dataclass
class Message:
    """消息 - OpenAI 格式"""
    role: str  # system, user, assistant
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Context:
    """
    会话上下文 - 支持持久化 + 自动裁剪 + 摘要注入

    功能:
    1. 内存管理对话历史
    2. 自动保存到 SQLite
    3. 初始化时恢复历史
    4. 自动裁剪超限历史，返回被裁剪的消息
    5. 上下文摘要注入（裁剪时生成摘要替换被裁剪内容）

    CowAgent 中有两个 "Context" 概念:
    1. bridge/context.py 的 Context - 单条消息的容器 (type, content, kwargs)
    2. Agent.messages - 会话级别的对话历史

    这里简化为单一 Context 类，管理会话消息历史
    """
    session_id: str
    messages: List[Message] = field(default_factory=list)
    user_id: Optional[str] = None
    max_turns: int = 20  # 最大对话轮数
    auto_save: bool = True  # 自动保存
    db_path: Optional[str] = None  # 数据库路径（可选，默认使用全局 store）

    # 上下文摘要注入
    _context_summary: Optional[str] = field(default=None, repr=False)

    def __post_init__(self):
        """初始化后恢复历史"""
        self._restore_history()

    def add_message(self, role: str, content: str, **metadata) -> Optional[List[Message]]:
        """
        添加消息

        Returns:
            如果触发了裁剪，返回被裁剪的消息列表；否则返回 None
        """
        self.messages.append(Message(role, content, metadata))

        # 检查是否需要裁剪
        discarded = None
        if self._needs_trim():
            discarded = self._trim_messages()

        if self.auto_save:
            self._save_history()

        return discarded

    def get_openai_messages(self) -> List[Dict]:
        """获取 OpenAI 格式的消息列表"""
        return [{"role": m.role, "content": m.content} for m in self.messages]

    def get_messages_with_summary(self) -> List[Dict]:
        """
        获取带上下文摘要的消息列表

        如果有上下文摘要，会在历史消息前插入摘要
        """
        result = []

        # 如果有上下文摘要，注入到消息列表
        if self._context_summary:
            result.append({
                "role": "system",
                "content": f"## 历史对话摘要\n\n{self._context_summary}"
            })

        result.extend(self.get_openai_messages())
        return result

    def inject_context_summary(self, summary: str):
        """
        注入上下文摘要

        当对话被裁剪时，用摘要替换被裁剪的内容，
        保持对话连续性而不丢失上下文
        """
        self._context_summary = summary

    def clear(self):
        """清空历史（内存 + 数据库）"""
        self.messages.clear()
        self._context_summary = None
        try:
            store = get_context_store()
            store.clear_session(self.session_id)
        except Exception:
            pass

    # ==================== 裁剪逻辑 ====================

    def _needs_trim(self) -> bool:
        """检查是否需要裁剪"""
        turns = self._count_turns()
        return turns > self.max_turns

    def _count_turns(self) -> int:
        """计算对话轮次（user 消息数量）"""
        count = 0
        for msg in self.messages:
            if msg.role == "user":
                count += 1
        return count

    def _trim_messages(self) -> List[Message]:
        """
        裁剪消息历史

        策略：保留后一半轮次，返回被裁剪的前一半

        Returns:
            被裁剪的消息列表
        """
        # 识别完整轮次
        turns = self._identify_turns()
        if not turns:
            return []

        # 计算要保留的轮次
        removed_count = len(turns) // 2
        if removed_count == 0:
            return []

        # 分离被裁剪和保留的轮次
        discarded_turns = turns[:removed_count]
        kept_turns = turns[removed_count:]

        # 重建消息列表
        discarded_messages = []
        for turn in discarded_turns:
            discarded_messages.extend(turn)

        new_messages = []
        for turn in kept_turns:
            new_messages.extend(turn)

        self.messages = new_messages

        return discarded_messages

    def _identify_turns(self) -> List[List[Message]]:
        """
        识别完整对话轮次

        每轮包含：
        - 1 条 user 消息
        - 0-N 条 assistant 消息（可能包含 tool_use）
        - 0-N 条 tool 消息（tool_result）

        Returns:
            轮次列表，每个轮次是消息列表
        """
        turns = []
        current_turn = []

        for msg in self.messages:
            current_turn.append(msg)

            # user 消息结束一轮（但如果是第一条，继续累积）
            if msg.role == "user" and current_turn:
                # 检查是否已经有完整的一轮（前面有 user 消息）
                if any(m.role == "user" for m in current_turn[:-1]):
                    # 当前 user 开始新的一轮，保存之前的
                    turns.append(current_turn[:-1])
                    current_turn = [msg]

        # 最后一轮
        if current_turn:
            turns.append(current_turn)

        return turns

    # ==================== 持久化 ====================

    def _save_history(self):
        """保存历史到数据库"""
        try:
            store = get_context_store(self.db_path)
            store.save_messages(
                session_id=self.session_id,
                messages=self.get_openai_messages(),
                user_id=self.user_id
            )
        except Exception:
            pass

    def _restore_history(self):
        """从数据库恢复历史"""
        try:
            store = get_context_store(self.db_path)
            saved = store.load_messages(
                session_id=self.session_id,
                max_turns=self.max_turns
            )
            if saved:
                self.messages = [
                    Message(role=m["role"], content=m["content"])
                    for m in saved
                ]
        except Exception:
            pass
