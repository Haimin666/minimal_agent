"""
Minimal Agent - CowAgent 核心机制最小实现

保留的核心功能:
- 向量检索 (余弦相似度)
- 关键词检索 (LIKE)
- 混合检索 (加权融合)
- 文本分块 (带重叠)
- 时间衰减
- 文件检索 (memory_get)
- 真实 LLM 调用
- Prompt 模块化构建
- 上下文消息历史

删减的功能:
- FTS5 全文索引
- 技能系统
- 知识系统
- 流式输出
- 多渠道支持
- 线程安全
"""

from .config import Config
from .context import Context, Message
from .agent import SimpleAgent
from .memory import MemoryManager, MemoryStorage
from .prompt import PromptBuilder

__all__ = [
    'Config',
    'Context',
    'Message',
    'SimpleAgent',
    'MemoryManager',
    'MemoryStorage',
    'PromptBuilder',
]
