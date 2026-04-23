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
        # 启用 WAL 模式支持并发读写
        self.conn = sqlite3.connect(db_path, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
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

        # FTS5 全文索引虚拟表
        self.conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                text,
                path,
                content='chunks',
                content_rowid='rowid',
                tokenize='unicode61'
            )
        """)

        # 同步触发器：插入时更新 FTS
        self.conn.execute("""
            CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
                INSERT INTO chunks_fts(rowid, text, path)
                VALUES (new.rowid, new.text, new.path);
            END
        """)

        # 同步触发器：删除时更新 FTS
        self.conn.execute("""
            CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
                INSERT INTO chunks_fts(chunks_fts, rowid, text, path)
                VALUES('delete', old.rowid, old.text, old.path);
            END
        """)

        # 同步触发器：更新时更新 FTS
        self.conn.execute("""
            CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
                INSERT INTO chunks_fts(chunks_fts, rowid, text, path)
                VALUES('delete', old.rowid, old.text, old.path);
                INSERT INTO chunks_fts(rowid, text, path)
                VALUES (new.rowid, new.text, new.path);
            END
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
            UPDATE chunks SET text = ?, hash = ?
            WHERE id = ?
        """, (new_text, new_hash, chunk_id))
        self.conn.commit()

    def update_chunk_embedding(self, chunk_id: str, embedding: List[float]):
        """更新块向量"""
        self.conn.execute("""
            UPDATE chunks SET embedding = ?
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

    # ==================== 关键词检索 ====================

    def search_keyword(
        self,
        query: str,
        user_id: str = None,
        scopes: List[str] = None,
        limit: int = 10
    ) -> List[SearchResult]:
        """
        关键词检索 - 与 CowAgent 一致

        策略:
        1. 包含 CJK：优先 LIKE 搜索（FTS5 对中文支持不好）
        2. 纯英文：FTS5 搜索
        """
        if scopes is None:
            scopes = ["shared"]
            if user_id:
                scopes.append("user")

        # CJK 文字：直接用 LIKE 搜索（更可靠）
        if self._contains_cjk(query):
            return self._search_like(query, user_id, scopes, limit)

        # 英文：使用 FTS5
        return self._search_fts5(query, user_id, scopes, limit)

    def _search_fts5(
        self,
        query: str,
        user_id: str = None,
        scopes: List[str] = None,
        limit: int = 10
    ) -> List[SearchResult]:
        """FTS5 全文检索"""
        scopes = scopes or ["shared"]
        fts_query = self._build_fts_query(query)
        if not fts_query:
            return []

        scope_placeholders = ','.join('?' * len(scopes))
        params = [fts_query] + scopes

        if user_id:
            sql = f"""
                SELECT c.*, bm25(chunks_fts) as bm25_score
                FROM chunks c
                JOIN chunks_fts fts ON c.rowid = fts.rowid
                WHERE chunks_fts MATCH ?
                AND c.scope IN ({scope_placeholders})
                AND (c.scope = 'shared' OR c.user_id = ?)
                ORDER BY bm25_score
                LIMIT ?
            """
            params.extend([user_id, limit])
        else:
            sql = f"""
                SELECT c.*, bm25(chunks_fts) as bm25_score
                FROM chunks c
                JOIN chunks_fts fts ON c.rowid = fts.rowid
                WHERE chunks_fts MATCH ?
                AND c.scope IN ({scope_placeholders})
                ORDER BY bm25_score
                LIMIT ?
            """
            params.append(limit)

        try:
            rows = self.conn.execute(sql, params).fetchall()
            return [
                SearchResult(
                    path=row['path'],
                    start_line=row['start_line'],
                    end_line=row['end_line'],
                    score=self._bm25_rank_to_score(row['bm25_score']),
                    snippet=self._truncate(row['text'], 500),
                    scope=row['scope'],
                    user_id=row['user_id']
                )
                for row in rows
            ]
        except Exception:
            return []

    def _build_fts_query(self, query: str) -> str:
        """
        构建 FTS5 查询

        改进：
        1. 对中文使用字符级匹配（更宽松）
        2. 对英文使用词级匹配
        """
        import re

        # 检测是否全是中文
        if self._is_all_chinese(query):
            # 中文：使用模糊匹配，每个字符都可能匹配
            # 提取所有中文字符
            chars = [c for c in query if '\u4e00' <= c <= '\u9fff']
            if chars:
                # 使用 OR 连接每个字符，并加 * 前缀进行前缀匹配
                return " OR ".join(f'"{c}"*' for c in chars[:5])  # 最多 5 个字符

        # 英文/混合：使用词级匹配
        words = re.findall(r'\w+', query)
        if not words:
            return ""
        return " OR ".join(words)

    @staticmethod
    def _is_all_chinese(text: str) -> bool:
        """检测是否全是中文（忽略标点和空格）"""
        for char in text:
            if char.isalpha() and not ('\u4e00' <= char <= '\u9fff'):
                return False
        return any('\u4e00' <= c <= '\u9fff' for c in text)

    def _bm25_rank_to_score(self, rank: float) -> float:
        """BM25 排名转分数（归一化）"""
        # BM25 返回负值，越小匹配越好
        score = max(0.0, -rank / 10)
        return min(score, 1.0)

    def _search_like(
        self,
        query: str,
        user_id: str = None,
        scopes: List[str] = None,
        limit: int = 10
    ) -> List[SearchResult]:
        """LIKE 模糊匹配 - CJK 回退方案"""
        import re
        scopes = scopes or ["shared"]

        # 提取所有 CJK 字符（单字）
        # 注意：不要用 {2,}，因为会匹配连续字符而不是分词
        cjk_chars = [c for c in query if '\u4e00' <= c <= '\u9fff']

        if not cjk_chars:
            return []

        scope_placeholders = ','.join('?' * len(scopes))

        # 构建 LIKE 条件
        like_conditions = " OR ".join(["text LIKE ?"] * len(cjk_chars))
        like_params = [f'%{char}%' for char in cjk_chars]

        if user_id:
            sql = f"""
                SELECT * FROM chunks
                WHERE ({like_conditions})
                AND scope IN ({scope_placeholders})
                AND (scope = 'shared' OR user_id = ?)
                LIMIT ?
            """
            params = like_params + scopes + [user_id, limit]
        else:
            sql = f"""
                SELECT * FROM chunks
                WHERE ({like_conditions})
                AND scope IN ({scope_placeholders})
                LIMIT ?
            """
            params = like_params + scopes + [limit]

        try:
            rows = self.conn.execute(sql, params).fetchall()
            return [
                SearchResult(
                    path=row['path'],
                    start_line=row['start_line'],
                    end_line=row['end_line'],
                    score=0.5,  # LIKE 匹配固定分数
                    snippet=self._truncate(row['text'], 500),
                    scope=row['scope'],
                    user_id=row['user_id']
                )
                for row in rows
            ]
        except Exception:
            return []

    def search_keyword_in_scope(
        self,
        keywords: List[str],
        user_id: str = None,
        scopes: List[str] = None,
        limit: int = 10
    ) -> List[SearchResult]:
        """
        关键词检索 - 兼容旧接口

        Args:
            keywords: 关键词列表
        """
        query = " ".join(keywords)
        return self.search_keyword(query, user_id, scopes, limit)

    @staticmethod
    def _contains_cjk(text: str) -> bool:
        """检测是否包含中日韩文字"""
        for char in text:
            if '\u4e00' <= char <= '\u9fff':  # 中文
                return True
            if '\u3040' <= char <= '\u30ff':  # 日文
                return True
            if '\uac00' <= char <= '\ud7af':  # 韩文
                return True
        return False

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
