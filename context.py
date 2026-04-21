"""上下文管理 - 支持持久化"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

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
    会话上下文 - 支持持久化

    功能:
    1. 内存管理对话历史
    2. 自动保存到 SQLite
    3. 初始化时恢复历史

    CowAgent 中有两个 "Context" 概念:
    1. bridge/context.py 的 Context - 单条消息的容器 (type, content, kwargs)
    2. Agent.messages - 会话级别的对话历史

    这里简化为单一 Context 类，管理会话消息历史
    """
    session_id: str
    messages: List[Message] = field(default_factory=list)
    user_id: Optional[str] = None
    max_turns: int = 20  # 最大恢复轮数
    auto_save: bool = True  # 自动保存

    def __post_init__(self):
        """初始化后恢复历史"""
        self._restore_history()

    def add_message(self, role: str, content: str, **metadata):
        """添加消息"""
        self.messages.append(Message(role, content, metadata))
        if self.auto_save:
            self._save_history()

    def get_openai_messages(self) -> List[Dict]:
        """获取 OpenAI 格式的消息列表"""
        return [{"role": m.role, "content": m.content} for m in self.messages]

    def clear(self):
        """清空历史（内存 + 数据库）"""
        self.messages.clear()
        try:
            store = get_context_store()
            store.clear_session(self.session_id)
        except Exception:
            pass

    def _save_history(self):
        """保存历史到数据库"""
        try:
            store = get_context_store()
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
            store = get_context_store()
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
