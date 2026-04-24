"""记忆管理器 - 简化版：只追加，不更新

设计原则：
- 只追加写入，不实时编辑
- 仅向量检索（移除关键词兜底）
- 冲突/更新由 Deep Dream 延迟处理
"""

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
    记忆管理器 - 简化版

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
    - 新记忆 → 直接追加到当日文件末尾
    - 冲突检测 → 由 Deep Dream 延迟处理
    """

    def __init__(
        self,
        storage: MemoryStorage = None,
        embedding_provider: EmbeddingProvider = None,
        workspace_dir: str = "./workspace",
        chunk_max_tokens: int = 500,
        chunk_overlap_tokens: int = 50,
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
        tags: List[str] = None,
        **metadata
    ) -> str:
        """
        添加记忆 - 只追加，不检测相似度

        Args:
            content: 记忆内容（单行）
            user_id: 用户 ID
            scope: 记忆范围 (shared | user)
            tags: 语义标签列表，例如 ['职业:教师', '科目:语文']

        Returns:
            文件路径
        """
        if not content.strip():
            return None

        # 格式化为一行
        line_content = content.strip().replace('\n', ' ')

        # 附加标签到内容末尾（提高检索效果）
        # 标签格式: [职业:教师] [科目:语文]
        if tags:
            tag_str = ' '.join(f'[{tag}]' for tag in tags)
            line_content = f"{line_content} {tag_str}"

        if not line_content.startswith('- '):
            line_content = f"- {line_content}"

        # 获取当日文件路径
        path = self._get_today_path(user_id, scope)

        # 追加到文件末尾（带去重）
        line_num = self._append_to_file(path, line_content)

        # 如果重复，不写入数据库
        if line_num == -1:
            return path  # 已存在，跳过

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

    def _append_to_file(self, path: str, line_content: str) -> int:
        """追加一行到文件（带去重），返回行号，重复返回 -1"""
        file_path = self.workspace_dir / path
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # 提取纯内容用于去重比较（移除标签和前缀）
        def normalize(s):
            # 移除 "- " 前缀和 [标签]
            s = re.sub(r'^-\s*', '', s.strip())
            s = re.sub(r'\s*\[[^\]]+\]', '', s)
            # 归一化标点
            s = s.replace('，', ',').replace('。', '').lower()
            return s.strip()

        normalized_new = normalize(line_content)

        if file_path.exists():
            content = file_path.read_text(encoding='utf-8')
            lines = content.split('\n')

            # 检查是否已存在相同内容
            for line in lines:
                if normalize(line) == normalized_new:
                    return -1  # 重复，不写入

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

    # ==================== 搜索记忆 ====================

    def search(
        self,
        query: str,
        user_id: str = None,
        limit: int = 10,
        include_shared: bool = True,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3,
    ) -> List[SearchResult]:
        """
        搜索记忆 - 混合检索（向量 + 关键词），与 CowAgent 一致

        Args:
            query: 搜索关键词
            user_id: 用户 ID
            limit: 返回数量
            include_shared: 是否包含共享记忆
            vector_weight: 向量检索权重
            keyword_weight: 关键词检索权重
        """
        scopes = ["user"]
        if include_shared:
            scopes.append("shared")

        # 1. 向量检索
        vector_results = []
        if self.embedding_provider:
            try:
                query_embedding = self.embedding_provider.embed(query)
                vector_results = self.storage.search_vector(
                    query_embedding=query_embedding,
                    user_id=user_id,
                    scopes=scopes,
                    limit=limit * 2  # 获取更多候选
                )
            except Exception:
                pass

        # 2. 关键词检索
        keyword_results = self.storage.search_keyword(
            query=query,
            user_id=user_id,
            scopes=scopes,
            limit=limit * 2
        )

        # 3. 合并结果
        merged = self._merge_results(
            vector_results,
            keyword_results,
            vector_weight,
            keyword_weight
        )

        return merged[:limit]

    def _merge_results(
        self,
        vector_results: List[SearchResult],
        keyword_results: List[SearchResult],
        vector_weight: float,
        keyword_weight: float
    ) -> List[SearchResult]:
        """
        合并向量和关键词检索结果

        Args:
            vector_results: 向量检索结果
            keyword_results: 关键词检索结果
            vector_weight: 向量权重
            keyword_weight: 关键词权重
        """
        # 使用 (path, start_line, end_line) 作为唯一键
        merged_map = {}

        for result in vector_results:
            key = (result.path, result.start_line, result.end_line)
            merged_map[key] = {
                'result': result,
                'vector_score': result.score,
                'keyword_score': 0.0
            }

        for result in keyword_results:
            key = (result.path, result.start_line, result.end_line)
            if key in merged_map:
                merged_map[key]['keyword_score'] = result.score
            else:
                merged_map[key] = {
                    'result': result,
                    'vector_score': 0.0,
                    'keyword_score': result.score
                }

        # 计算加权分数
        merged_results = []
        for entry in merged_map.values():
            result = entry['result']
            combined_score = (
                vector_weight * entry['vector_score'] +
                keyword_weight * entry['keyword_score']
            )

            merged_results.append(SearchResult(
                path=result.path,
                start_line=result.start_line,
                end_line=result.end_line,
                score=combined_score,
                snippet=result.snippet,
                scope=result.scope,
                user_id=result.user_id
            ))

        # 按分数排序
        merged_results.sort(key=lambda r: r.score, reverse=True)
        return merged_results

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
