"""存储层 - 向量检索 + 增量同步"""

import sqlite3
import json
import hashlib
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from pathlib import Path


@dataclass
class MemoryChunk:
    """记忆块"""
    id: str
    text: str
    embedding: Optional[List[float]] = None
    path: str = ""
    start_line: int = 1
    end_line: int = 1
    scope: str = "shared"  # shared | user
    user_id: Optional[str] = None
    hash: str = ""


@dataclass
class SearchResult:
    """搜索结果"""
    path: str
    start_line: int
    end_line: int
    score: float
    snippet: str
    scope: str = "shared"
    user_id: Optional[str] = None


class MemoryStorage:
    """
    SQLite 存储 - 支持用户隔离 + 增量同步

    表结构：
    - chunks 表: 文本块 + 向量 + scope + user_id
    - files 表: 文件元数据（用于增量同步）
    """

    def __init__(self, db_path: str = "memory.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        # chunks 表
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                text TEXT NOT NULL,
                embedding TEXT,
                scope TEXT NOT NULL DEFAULT 'shared',
                user_id TEXT,
                hash TEXT NOT NULL,
                created_at INTEGER DEFAULT (strftime('%s', 'now'))
            )
        """)

        # files 表 - 用于增量同步
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                hash TEXT NOT NULL,
                mtime INTEGER NOT NULL,
                size INTEGER NOT NULL,
                updated_at INTEGER DEFAULT (strftime('%s', 'now'))
            )
        """)

        # 索引
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_scope ON chunks(scope)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_user ON chunks(user_id)")
        self.conn.commit()

    # ==================== 文件元数据 ====================

    def get_file_hash(self, path: str) -> Optional[str]:
        """获取文件的存储 hash"""
        row = self.conn.execute(
            "SELECT hash FROM files WHERE path = ?", (path,)
        ).fetchone()
        return row['hash'] if row else None

    def update_file_hash(self, path: str, hash: str, mtime: int = 0, size: int = 0):
        """更新文件 hash"""
        self.conn.execute("""
            INSERT OR REPLACE INTO files (path, hash, mtime, size, updated_at)
            VALUES (?, ?, ?, ?, strftime('%s', 'now'))
        """, (path, hash, mtime, size))
        self.conn.commit()

    def delete_file_record(self, path: str):
        """删除文件记录"""
        self.conn.execute("DELETE FROM files WHERE path = ?", (path,))
        self.conn.commit()

    # ==================== Chunk 操作 ====================

    def save_chunk(self, chunk: MemoryChunk):
        """保存单个块"""
        self.conn.execute("""
            INSERT OR REPLACE INTO chunks
            (id, path, start_line, end_line, text, embedding, scope, user_id, hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            chunk.id,
            chunk.path,
            chunk.start_line,
            chunk.end_line,
            chunk.text,
            json.dumps(chunk.embedding) if chunk.embedding else None,
            chunk.scope,
            chunk.user_id,
            chunk.hash
        ))
        self.conn.commit()

    def save_chunks_batch(self, chunks: List[MemoryChunk]):
        """批量保存"""
        self.conn.executemany("""
            INSERT OR REPLACE INTO chunks
            (id, path, start_line, end_line, text, embedding, scope, user_id, hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (c.id, c.path, c.start_line, c.end_line, c.text,
             json.dumps(c.embedding) if c.embedding else None,
             c.scope, c.user_id, c.hash)
            for c in chunks
        ])
        self.conn.commit()

    def delete_by_path(self, path: str):
        """删除指定路径的所有块"""
        self.conn.execute("DELETE FROM chunks WHERE path = ?", (path,))
        self.conn.commit()

    def delete_by_line(self, path: str, line: int):
        """删除指定路径指定行的块"""
        self.conn.execute(
            "DELETE FROM chunks WHERE path = ? AND start_line <= ? AND end_line >= ?",
            (path, line, line)
        )
        self.conn.commit()

    def update_chunk_text(self, chunk_id: str, new_text: str, new_hash: str):
        """更新块文本"""
        self.conn.execute("""
            UPDATE chunks SET text = ?, hash = ?, updated_at = strftime('%s', 'now')
            WHERE id = ?
        """, (new_text, new_hash, chunk_id))
        self.conn.commit()

    def update_chunk_embedding(self, chunk_id: str, embedding: List[float]):
        """更新块向量"""
        self.conn.execute("""
            UPDATE chunks SET embedding = ?, updated_at = strftime('%s', 'now')
            WHERE id = ?
        """, (json.dumps(embedding), chunk_id))
        self.conn.commit()

    def get_chunk_by_path_line(self, path: str, line: int) -> Optional[MemoryChunk]:
        """获取指定路径指定行的块"""
        row = self.conn.execute(
            "SELECT * FROM chunks WHERE path = ? AND start_line <= ? AND end_line >= ?",
            (path, line, line)
        ).fetchone()

        if not row:
            return None

        return MemoryChunk(
            id=row['id'],
            text=row['text'],
            embedding=json.loads(row['embedding']) if row['embedding'] else None,
            path=row['path'],
            start_line=row['start_line'],
            end_line=row['end_line'],
            scope=row['scope'],
            user_id=row['user_id'],
            hash=row['hash']
        )

    # ==================== 向量检索 ====================

    def search_vector(
        self,
        query_embedding: List[float],
        user_id: str = None,
        scopes: List[str] = None,
        limit: int = 10
    ) -> List[SearchResult]:
        """向量检索 - 余弦相似度"""
        scopes = scopes or ["shared"]

        # 构建查询条件
        if user_id and "user" in scopes:
            # 包含共享 + 用户私有
            condition = "(scope = 'shared' OR (scope = 'user' AND user_id = ?))"
            params = [user_id]
        else:
            # 仅共享
            condition = "scope = 'shared'"
            params = []

        rows = self.conn.execute(
            f"SELECT * FROM chunks WHERE embedding IS NOT NULL AND {condition}",
            params
        ).fetchall()

        results = []
        for row in rows:
            embedding = json.loads(row['embedding'])
            similarity = self._cosine_similarity(query_embedding, embedding)

            results.append(SearchResult(
                path=row['path'],
                start_line=row['start_line'],
                end_line=row['end_line'],
                score=similarity,
                snippet=self._truncate(row['text'], 500),
                scope=row['scope'],
                user_id=row['user_id']
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]

    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """余弦相似度"""
        if len(vec1) != len(vec2):
            return 0.0

        dot = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot / (norm1 * norm2)

    # ==================== 统计 ====================

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        chunks_count = self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        files_count = self.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        return {
            'chunks': chunks_count,
            'files': files_count
        }

    @staticmethod
    def compute_hash(text: str) -> str:
        """计算文本 hash"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    @staticmethod
    def _truncate(text: str, max_chars: int) -> str:
        """截断文本"""
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "..."

    def close(self):
        """关闭连接"""
        self.conn.close()
