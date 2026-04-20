"""上下文管理 - 简化版"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class Message:
    """消息 - OpenAI 格式"""
    role: str  # system, user, assistant
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Context:
    """
    会话上下文

    CowAgent 中有两个 "Context" 概念:
    1. bridge/context.py 的 Context - 单条消息的容器 (type, content, kwargs)
    2. Agent.messages - 会话级别的对话历史

    这里简化为单一 Context 类，管理会话消息历史
    """
    session_id: str
    messages: List[Message] = field(default_factory=list)
    user_id: Optional[str] = None

    def add_message(self, role: str, content: str, **metadata):
        """添加消息"""
        self.messages.append(Message(role, content, metadata))

    def get_openai_messages(self) -> List[Dict]:
        """获取 OpenAI 格式的消息列表"""
        return [{"role": m.role, "content": m.content} for m in self.messages]

    def clear(self):
        """清空历史"""
        self.messages.clear()
