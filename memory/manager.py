"""记忆管理器 - 整合分块、嵌入、存储"""

from typing import List, Optional, Dict, Any
from pathlib import Path
import hashlib
import os

from .storage import MemoryStorage, MemoryChunk, SearchResult
from .chunker import TextChunker
from .embedding import EmbeddingProvider


class MemoryManager:
    """
    记忆管理器 - 支持用户隔离

    记忆隔离级别：
    - shared: 共享记忆，所有用户可见（如通用知识）
    - user: 用户私有记忆，仅该用户可见
    - session: 会话级记忆，仅当前会话可见
    """

    def __init__(
        self,
        storage: MemoryStorage = None,
        embedding_provider: EmbeddingProvider = None,
        workspace_dir: str = "./workspace",
        chunk_max_tokens: int = 500,
        chunk_overlap_tokens: int = 50
    ):
        self.storage = storage or MemoryStorage()
        self.embedding_provider = embedding_provider
        self.workspace_dir = Path(workspace_dir)

        self.chunker = TextChunker(
            max_tokens=chunk_max_tokens,
            overlap_tokens=chunk_overlap_tokens
        )

        # 确保目录存在
        self.memory_dir = self.workspace_dir / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def add_memory(
        self,
        content: str,
        path: str = None,
        user_id: str = None,
        scope: str = "user",
        **metadata
    ) -> str:
        """
        添加记忆

        Args:
            content: 记忆内容
            path: 存储路径 (默认自动生成)
            user_id: 用户 ID (私有记忆必填)
            scope: 记忆范围 (shared | user | session)

        Returns:
            生成的路径
        """
        if not content.strip():
            return None

        # 生成路径
        if not path:
            content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
            if scope == "shared":
                path = f"memory/shared/memory_{content_hash}.md"
            elif scope == "user" and user_id:
                path = f"memory/users/{user_id}/memory_{content_hash}.md"
            else:
                path = f"memory/memory_{content_hash}.md"

        # 写入文件
        file_path = self.workspace_dir / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding='utf-8')

        # 分块
        chunks = self.chunker.chunk_text(content)

        # 生成向量
        embeddings = None
        if self.embedding_provider:
            texts = [c.text for c in chunks]
            embeddings = self.embedding_provider.embed_batch(texts)

        # 保存到数据库
        memory_chunks = []
        for i, chunk in enumerate(chunks):
            chunk_id = hashlib.md5(f"{path}:{chunk.start_line}:{chunk.end_line}".encode()).hexdigest()
            embedding = embeddings[i] if embeddings else None

            memory_chunks.append(MemoryChunk(
                id=chunk_id,
                text=chunk.text,
                embedding=embedding,
                path=path,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                scope=scope,
                user_id=user_id if scope == "user" else None,
                metadata={**metadata}
            ))

        self.storage.save_chunks_batch(memory_chunks)

        return path

    def search(
        self,
        query: str,
        user_id: str = None,
        limit: int = 10,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3,
        include_shared: bool = True
    ) -> List[SearchResult]:
        """
        搜索记忆 - 支持用户隔离

        Args:
            query: 搜索关键词
            user_id: 用户 ID (提供时启用隔离)
            limit: 返回数量
            vector_weight: 向量权重
            keyword_weight: 关键词权重
            include_shared: 是否包含共享记忆

        Returns:
            搜索结果列表
        """
        if user_id:
            # 用户隔离检索
            if self.embedding_provider:
                query_embedding = self.embedding_provider.embed(query)
                return self.storage.search_hybrid_for_user(
                    query=query,
                    query_embedding=query_embedding,
                    user_id=user_id,
                    limit=limit,
                    vector_weight=vector_weight,
                    keyword_weight=keyword_weight,
                    include_shared=include_shared
                )
            else:
                return self.storage.search_for_user(
                    query=query,
                    user_id=user_id,
                    limit=limit,
                    include_shared=include_shared
                )
        else:
            # 全局检索（无隔离）
            if self.embedding_provider:
                query_embedding = self.embedding_provider.embed(query)
                return self.storage.search_hybrid(
                    query=query,
                    query_embedding=query_embedding,
                    limit=limit,
                    vector_weight=vector_weight,
                    keyword_weight=keyword_weight
                )
            else:
                return self.storage.search_keyword(query, limit)

    def get_file_content(
        self,
        path: str,
        start_line: int = 1,
        num_lines: int = None
    ) -> Optional[str]:
        """
        读取文件内容

        CowAgent 的 memory_get 工具实现
        """
        file_path = self.workspace_dir / path
        if not file_path.exists():
            return None

        content = file_path.read_text(encoding='utf-8')
        lines = content.split('\n')

        start_idx = max(0, start_line - 1)
        if num_lines:
            selected = lines[start_idx:start_idx + num_lines]
        else:
            selected = lines[start_idx:]

        return '\n'.join(selected)

    def sync_from_files(self):
        """
        从文件系统同步到数据库

        CowAgent 实现:
        1. 扫描 MEMORY.md
        2. 扫描 memory/ 目录
        3. 比对 hash，增量更新
        """
        # 扫描 MEMORY.md
        memory_file = self.workspace_dir / "MEMORY.md"
        if memory_file.exists():
            self._sync_file(memory_file, "MEMORY.md")

        # 扫描 memory/ 目录
        for file_path in self.memory_dir.rglob("*.md"):
            rel_path = str(file_path.relative_to(self.workspace_dir))
            self._sync_file(file_path, rel_path)

    def _sync_file(self, file_path: Path, rel_path: str):
        """同步单个文件"""
        content = file_path.read_text(encoding='utf-8')

        # 删除旧数据
        self.storage.delete_by_path(rel_path)

        # 分块 + 向量化
        chunks = self.chunker.chunk_text(content)

        embeddings = None
        if self.embedding_provider:
            texts = [c.text for c in chunks]
            embeddings = self.embedding_provider.embed_batch(texts)

        # 保存
        memory_chunks = []
        for i, chunk in enumerate(chunks):
            chunk_id = hashlib.md5(f"{rel_path}:{chunk.start_line}:{chunk.end_line}".encode()).hexdigest()
            memory_chunks.append(MemoryChunk(
                id=chunk_id,
                text=chunk.text,
                embedding=embeddings[i] if embeddings else None,
                path=rel_path,
                start_line=chunk.start_line,
                end_line=chunk.end_line
            ))

        self.storage.save_chunks_batch(memory_chunks)
