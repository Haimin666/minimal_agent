"""
Minimal Agent - 三层记忆架构最小实现

核心功能:
- 三层记忆：短期(Context) / 中期(Daily) / 长期(MEMORY.md)
- 混合检索：向量检索 + 关键词检索
- 上下文摘要注入：裁剪时保持连续性
- Deep Dream 蒸馏：长期记忆整理
"""

from .config import Config
from .context import Context, Message
from .context_store import ContextStore, get_context_store
from .agent import SimpleAgent
from .memory import (
    MemoryManager, MemoryStorage, MemoryFlusher, DeepDream,
    MemoryChunk, SearchResult
)
from .prompt import PromptBuilder

__all__ = [
    'Config',
    'Context',
    'Message',
    'ContextStore',
    'get_context_store',
    'SimpleAgent',
    'MemoryManager',
    'MemoryStorage',
    'MemoryFlusher',
    'DeepDream',
    'MemoryChunk',
    'SearchResult',
    'PromptBuilder',
]
