"""记忆管理器 - 文件 + 向量数据库混合存储"""

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
    记忆管理器 - 文件（人类可读）+ 数据库（机器检索）

    存储结构：
    workspace/
    ├── MEMORY.md              # 共享长期记忆
    └── memory/
        ├── shared/            # 共享每日记忆
        │   └── YYYY-MM-DD.md
        └── users/
            └── {user_id}/
                ├── MEMORY.md      # 用户长期记忆
                └── YYYY-MM-DD.md  # 用户每日记忆

    更新机制：
    - 新记忆 → 检测相似度
    - 相似度 > 0.85 → 编辑文件对应行 + 更新向量
    - 相似度 <= 0.85 → 追加到当日文件末尾 + 新增向量
    """

    # 相似度阈值
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

    # ==================== 添加记忆 ====================

    def add_memory(
        self,
        content: str,
        user_id: str = None,
        scope: str = "user",
        **metadata
    ) -> str:
        """
        添加记忆 - 支持更新模式

        Args:
            content: 记忆内容（单行）
            user_id: 用户 ID
            scope: 记忆范围 (shared | user)

        Returns:
            文件路径
        """
        if not content.strip():
            return None

        # 格式化为一行
        line_content = content.strip().replace('\n', ' ')
        if not line_content.startswith('- '):
            line_content = f"- {line_content}"

        # 获取当日文件路径
        path = self._get_today_path(user_id, scope)

        # 检查是否需要更新（相似记忆存在）
        similar = None
        if self.embedding_provider:
            similar = self._find_similar_memory(line_content, user_id, scope)

        if similar:
            # 更新模式：编辑文件对应行
            self._edit_memory_line(similar.path, similar.start_line, line_content)
            # 更新数据库
            self._update_chunk(similar, line_content)
            return similar.path
        else:
            # 新增模式：追加到文件末尾
            line_num = self._append_to_file(path, line_content)
            # 同步到数据库
            self._sync_single_line(path, line_num, line_content, user_id, scope)
            return path

    def _get_today_path(self, user_id: str, scope: str) -> str:
        """获取当日文件路径"""
        today = datetime.now().strftime("%Y-%m-%d")

        if scope == "shared":
            return f"memory/shared/{today}.md"
        else:
            return f"memory/users/{user_id}/{today}.md"

    def _find_similar_memory(
        self,
        content: str,
        user_id: str,
        scope: str
    ) -> Optional[SearchResult]:
        """查找相似记忆"""
        if not self.embedding_provider:
            return None

        query_embedding = self.embedding_provider.embed(content)
        scopes = ["user"] if scope == "user" else ["shared"]

        results = self.storage.search_vector(
            query_embedding=query_embedding,
            user_id=user_id if scope == "user" else None,
            scopes=scopes,
            limit=5
        )

        for r in results:
            if r.score >= self.SIMILARITY_THRESHOLD:
                return r

        return None

    def _append_to_file(self, path: str, line_content: str) -> int:
        """追加一行到文件，返回行号"""
        file_path = self.workspace_dir / path
        file_path.parent.mkdir(parents=True, exist_ok=True)

        if file_path.exists():
            content = file_path.read_text(encoding='utf-8')
            lines = content.split('\n')
            # 找到最后一个非空行
            last_line = len(lines)
            for i in range(len(lines) - 1, -1, -1):
                if lines[i].strip():
                    last_line = i + 1
                    break

            # 追加
            new_content = content.rstrip('\n') + '\n' + line_content + '\n'
            file_path.write_text(new_content, encoding='utf-8')
            return last_line + 1
        else:
            # 新文件
            today = datetime.now().strftime("%Y-%m-%d")
            header = f"# Daily Memory: {today}\n\n"
            file_path.write_text(header + line_content + '\n', encoding='utf-8')
            return 3  # 第3行开始（标题 + 空行）

    def _edit_memory_line(self, path: str, line_num: int, new_content: str):
        """编辑文件指定行"""
        file_path = self.workspace_dir / path
        if not file_path.exists():
            return

        lines = file_path.read_text(encoding='utf-8').split('\n')
        if 0 < line_num <= len(lines):
            lines[line_num - 1] = new_content
            file_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    def _sync_single_line(
        self,
        path: str,
        line_num: int,
        content: str,
        user_id: str,
        scope: str
    ):
        """同步单行到数据库"""
        chunk_id = hashlib.md5(f"{path}:{line_num}".encode()).hexdigest()
        content_hash = MemoryStorage.compute_hash(content)

        # 生成向量
        embedding = None
        if self.embedding_provider:
            embedding = self.embedding_provider.embed(content)

        chunk = MemoryChunk(
            id=chunk_id,
            text=content,
            embedding=embedding,
            path=path,
            start_line=line_num,
            end_line=line_num,
            scope=scope,
            user_id=user_id if scope == "user" else None,
            hash=content_hash
        )

        self.storage.save_chunk(chunk)

        # 更新文件 hash
        file_path = self.workspace_dir / path
        if file_path.exists():
            file_hash = MemoryStorage.compute_hash(file_path.read_text(encoding='utf-8'))
            stat = file_path.stat()
            self.storage.update_file_hash(path, file_hash, int(stat.st_mtime), stat.st_size)

    def _update_chunk(self, similar: SearchResult, new_content: str):
        """更新数据库中的块"""
        content_hash = MemoryStorage.compute_hash(new_content)

        # 获取 chunk
        chunk = self.storage.get_chunk_by_path_line(similar.path, similar.start_line)
        if not chunk:
            return

        # 更新文本
        self.storage.update_chunk_text(chunk.id, new_content, content_hash)

        # 更新向量
        if self.embedding_provider:
            embedding = self.embedding_provider.embed(new_content)
            self.storage.update_chunk_embedding(chunk.id, embedding)

        # 更新文件 hash
        file_path = self.workspace_dir / similar.path
        if file_path.exists():
            file_hash = MemoryStorage.compute_hash(file_path.read_text(encoding='utf-8'))
            stat = file_path.stat()
            self.storage.update_file_hash(similar.path, file_hash, int(stat.st_mtime), stat.st_size)

    # ==================== 搜索记忆 ====================

    def search(
        self,
        query: str,
        user_id: str = None,
        limit: int = 10,
        include_shared: bool = True
    ) -> List[SearchResult]:
        """
        搜索记忆

        Args:
            query: 搜索关键词
            user_id: 用户 ID
            limit: 返回数量
            include_shared: 是否包含共享记忆
        """
        if not self.embedding_provider:
            return []

        query_embedding = self.embedding_provider.embed(query)
        scopes = ["user"]
        if include_shared:
            scopes.append("shared")

        return self.storage.search_vector(
            query_embedding=query_embedding,
            user_id=user_id,
            scopes=scopes,
            limit=limit
        )

    # ==================== 文件操作 ====================

    def get_file_content(
        self,
        path: str,
        start_line: int = 1,
        num_lines: int = None
    ) -> Optional[str]:
        """读取文件内容"""
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

    # ==================== 同步 ====================

    def sync_from_files(self):
        """
        从文件系统同步到数据库（增量同步）

        根据 hash 判断文件是否变化
        """
        # 同步共享 MEMORY.md
        shared_memory = self.workspace_dir / "MEMORY.md"
        if shared_memory.exists():
            self._sync_file(shared_memory, "MEMORY.md", scope="shared", user_id=None)

        # 同步共享每日记忆
        shared_dir = self.memory_dir / "shared"
        if shared_dir.exists():
            for file_path in shared_dir.glob("*.md"):
                rel_path = f"memory/shared/{file_path.name}"
                self._sync_file(file_path, rel_path, scope="shared", user_id=None)

        # 同步用户记忆
        users_dir = self.memory_dir / "users"
        if users_dir.exists():
            for user_dir in users_dir.iterdir():
                if user_dir.is_dir():
                    user_id = user_dir.name
                    # 用户 MEMORY.md
                    user_memory = user_dir / "MEMORY.md"
                    if user_memory.exists():
                        rel_path = f"memory/users/{user_id}/MEMORY.md"
                        self._sync_file(user_memory, rel_path, scope="user", user_id=user_id)
                    # 用户每日记忆
                    for file_path in user_dir.glob("*.md"):
                        if file_path.name != "MEMORY.md":
                            rel_path = f"memory/users/{user_id}/{file_path.name}"
                            self._sync_file(file_path, rel_path, scope="user", user_id=user_id)

    def _sync_file(
        self,
        file_path: Path,
        rel_path: str,
        scope: str,
        user_id: str
    ):
        """同步单个文件（增量）"""
        content = file_path.read_text(encoding='utf-8')
        file_hash = MemoryStorage.compute_hash(content)

        # 检查是否变化
        stored_hash = self.storage.get_file_hash(rel_path)
        if stored_hash == file_hash:
            return  # 未变化，跳过

        # 变化，重新索引
        self.storage.delete_by_path(rel_path)

        # 按行处理
        lines = content.split('\n')
        chunks = []

        for i, line in enumerate(lines, start=1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue  # 跳过空行和标题

            chunk_id = hashlib.md5(f"{rel_path}:{i}".encode()).hexdigest()
            line_hash = MemoryStorage.compute_hash(line)

            chunks.append(MemoryChunk(
                id=chunk_id,
                text=line,
                embedding=None,  # 稍后批量生成
                path=rel_path,
                start_line=i,
                end_line=i,
                scope=scope,
                user_id=user_id,
                hash=line_hash
            ))

        # 批量生成向量
        if chunks and self.embedding_provider:
            texts = [c.text for c in chunks]
            embeddings = self.embedding_provider.embed_batch(texts)
            for chunk, embedding in zip(chunks, embeddings):
                chunk.embedding = embedding

        self.storage.save_chunks_batch(chunks)

        # 更新文件 hash
        stat = file_path.stat()
        self.storage.update_file_hash(rel_path, file_hash, int(stat.st_mtime), stat.st_size)
