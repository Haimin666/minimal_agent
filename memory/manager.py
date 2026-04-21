"""记忆管理器 - 整合分块、嵌入、存储 + 人类可读存储"""

from typing import List, Optional, Dict, Any
from pathlib import Path
import hashlib
import os
import re
from datetime import datetime

from .storage import MemoryStorage, MemoryChunk, SearchResult
from .chunker import TextChunker
from .embedding import EmbeddingProvider


class MemoryManager:
    """
    记忆管理器 - 支持用户隔离 + 人类可读存储

    存储结构：
    workspace/
    ├── MEMORY.md              # 记忆索引（人类可读）
    ├── profile/               # 用户画像目录
    │   └── {user_id}.md       # 用户画像文件
    └── memory/
        ├── shared/            # 共享记忆
        └── users/
            └── {user_id}/
                ├── profile.md     # 用户画像（从 profile/ 同步）
                └── YYYY-MM-DD.md  # 每日记忆（人类可读文件名）

    记忆更新策略：
    - 当保存新记忆时，搜索相似记忆
    - 如果相似度 > 0.85，认为是更新，删除旧记忆
    - 否则作为新记忆追加
    """

    # 相似度阈值，超过此值认为是更新
    SIMILARITY_THRESHOLD = 0.85

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
        (self.memory_dir / "shared").mkdir(exist_ok=True)
        (self.memory_dir / "users").mkdir(exist_ok=True)

        # 用户画像目录
        self.profile_dir = self.workspace_dir / "profile"
        self.profile_dir.mkdir(parents=True, exist_ok=True)

    def add_memory(
        self,
        content: str,
        path: str = None,
        user_id: str = None,
        scope: str = "user",
        **metadata
    ) -> str:
        """
        添加记忆 - 支持更新模式

        Args:
            content: 记忆内容
            path: 存储路径 (默认自动生成人类可读的文件名)
            user_id: 用户 ID (私有记忆必填)
            scope: 记忆范围 (shared | user)

        Returns:
            生成的路径
        """
        if not content.strip():
            return None

        # 检查是否需要更新（相似记忆存在）
        if self.embedding_provider and scope == "user" and user_id:
            similar = self._find_similar_memory(content, user_id)
            if similar:
                # 删除旧记忆
                self._delete_memory_file(similar.path)
                self.storage.delete_by_path(similar.path)

        # 生成人类可读的路径
        if not path:
            path = self._generate_readable_path(content, user_id, scope)

        # 写入文件
        file_path = self.workspace_dir / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding='utf-8')

        # 更新 MEMORY.md 索引
        self._update_memory_index(path, content, user_id, scope)

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

    def _generate_readable_path(self, content: str, user_id: str, scope: str) -> str:
        """
        生成人类可读的文件路径

        格式:
        - 共享: memory/shared/YYYY-MM-DD.md
        - 用户: memory/users/{user_id}/YYYY-MM-DD.md
        """
        today = datetime.now().strftime("%Y-%m-%d")

        if scope == "shared":
            dir_path = self.memory_dir / "shared"
            dir_path.mkdir(parents=True, exist_ok=True)
            base_path = f"memory/shared/{today}.md"
        else:
            dir_path = self.memory_dir / "users" / (user_id or "default")
            dir_path.mkdir(parents=True, exist_ok=True)
            base_path = f"memory/users/{user_id}/{today}.md"

        return base_path

    def _find_similar_memory(self, content: str, user_id: str) -> Optional[SearchResult]:
        """查找相似记忆，用于判断是否需要更新"""
        if not self.embedding_provider:
            return None

        query_embedding = self.embedding_provider.embed(content)
        results = self.storage.search_hybrid_for_user(
            query=content,
            query_embedding=query_embedding,
            user_id=user_id,
            limit=5,
            include_shared=False  # 只搜索用户私有记忆
        )

        for r in results:
            if r.score >= self.SIMILARITY_THRESHOLD:
                return r

        return None

    def _delete_memory_file(self, path: str):
        """删除记忆文件"""
        file_path = self.workspace_dir / path
        if not file_path.exists():
            return
        file_path.unlink()

    def _update_memory_index(self, path: str, content: str, user_id: str, scope: str):
        """更新 MEMORY.md 索引文件"""
        index_file = self.workspace_dir / "MEMORY.md"

        if index_file.exists():
            index_content = index_file.read_text(encoding='utf-8')
        else:
            index_content = "# 记忆索引\n\n自动维护的记忆索引。\n\n"

        # 检查是否已存在
        if path in index_content:
            return

        # 添加新条目
        today = datetime.now().strftime("%Y-%m-%d %H:%M")
        scope_tag = "共享" if scope == "shared" else f"用户({user_id})"
        summary = content[:50].replace('\n', ' ')

        new_entry = f"\n## [{today}] {scope_tag}\n- 文件: `{path}`\n- 内容: {summary}...\n"

        index_file.write_text(index_content + new_entry, encoding='utf-8')

    def load_user_profile(self, user_id: str) -> Optional[str]:
        """
        加载用户画像

        查找顺序：
        1. workspace/profile/{user_id}.md
        2. workspace/memory/users/{user_id}/profile.md
        """
        # 优先查找 profile 目录
        profile_file = self.profile_dir / f"{user_id}.md"
        if profile_file.exists():
            return profile_file.read_text(encoding='utf-8')

        # 其次查找 memory 目录
        profile_file = self.memory_dir / "users" / user_id / "profile.md"
        if profile_file.exists():
            return profile_file.read_text(encoding='utf-8')

        return None

    def scan_profiles(self) -> Dict[str, str]:
        """
        扫描所有用户画像

        Returns:
            {user_id: profile_content}
        """
        profiles = {}

        # 扫描 profile 目录
        for profile_file in self.profile_dir.glob("*.md"):
            user_id = profile_file.stem
            profiles[user_id] = profile_file.read_text(encoding='utf-8')

        return profiles

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

        扫描：
        1. MEMORY.md
        2. profile/ 目录（用户画像）
        3. memory/ 目录
        """
        # 扫描 MEMORY.md
        memory_file = self.workspace_dir / "MEMORY.md"
        if memory_file.exists():
            self._sync_file(memory_file, "MEMORY.md", scope="shared")

        # 扫描 profile 目录
        for profile_file in self.profile_dir.glob("*.md"):
            user_id = profile_file.stem
            rel_path = f"profile/{profile_file.name}"
            self._sync_file(profile_file, rel_path, scope="user", user_id=user_id)

        # 扫描 memory/ 目录
        for file_path in self.memory_dir.rglob("*.md"):
            rel_path = str(file_path.relative_to(self.workspace_dir))

            # 判断 scope
            if "shared" in rel_path:
                scope = "shared"
                user_id = None
            else:
                scope = "user"
                # 从路径提取 user_id: memory/users/{user_id}/xxx.md
                match = re.search(r"users/([^/]+)/", rel_path)
                user_id = match.group(1) if match else None

            self._sync_file(file_path, rel_path, scope=scope, user_id=user_id)

    def _sync_file(
        self,
        file_path: Path,
        rel_path: str,
        scope: str = "shared",
        user_id: str = None
    ):
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
                end_line=chunk.end_line,
                scope=scope,
                user_id=user_id
            ))

        self.storage.save_chunks_batch(memory_chunks)
