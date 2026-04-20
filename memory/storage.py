"""存储层 - 向量检索 + 关键词检索 + 混合检索"""

import sqlite3
import json
import math
import re
import hashlib
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime


@dataclass
class MemoryChunk:
    """
    记忆块

    scope 字段说明：
    - "shared": 共享记忆，所有用户可见（如通用知识、系统提示）
    - "user": 用户私有记忆，仅该用户可见
    - "session": 会话级记忆，仅当前会话可见
    """
    id: str
    text: str
    embedding: Optional[List[float]] = None
    path: str = ""
    start_line: int = 1
    end_line: int = 1
    scope: str = "shared"  # shared | user | session
    user_id: Optional[str] = None
    metadata: Dict[str, Any] = None


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
    SQLite 存储 - 支持用户隔离

    表结构：
    - chunks 表: 文本块 + 向量 + scope + user_id
    - scope 字段: shared(共享) | user(用户私有) | session(会话级)

    检索方式：
    - search_vector(): 余弦相似度
    - search_keyword(): LIKE 模糊匹配
    - search_hybrid(): 加权融合
    - search_for_user(): 用户隔离检索
    """

    def __init__(self, db_path: str = "memory.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        # chunks 表 - 增加 scope 和 user_id 字段
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
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 索引
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_scope ON chunks(scope)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_user ON chunks(user_id)")
        self.conn.commit()

    def save_chunk(self, chunk: MemoryChunk):
        """保存单个块"""
        self.conn.execute("""
            INSERT OR REPLACE INTO chunks
            (id, path, start_line, end_line, text, embedding, scope, user_id, metadata)
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
            json.dumps(chunk.metadata) if chunk.metadata else None
        ))
        self.conn.commit()

    def save_chunks_batch(self, chunks: List[MemoryChunk]):
        """批量保存"""
        self.conn.executemany("""
            INSERT OR REPLACE INTO chunks
            (id, path, start_line, end_line, text, embedding, scope, user_id, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (c.id, c.path, c.start_line, c.end_line, c.text,
             json.dumps(c.embedding) if c.embedding else None,
             c.scope, c.user_id,
             json.dumps(c.metadata) if c.metadata else None)
            for c in chunks
        ])
        self.conn.commit()

    def delete_by_path(self, path: str):
        """删除指定路径的所有块"""
        self.conn.execute("DELETE FROM chunks WHERE path = ?", (path,))
        self.conn.commit()

    # ==================== 向量检索 ====================

    def search_vector(
        self,
        query_embedding: List[float],
        limit: int = 10
    ) -> List[SearchResult]:
        """
        向量检索 - 余弦相似度

        CowAgent 实现:
        1. 从数据库取出所有有向量的 chunk
        2. 在内存中计算余弦相似度
        3. 排序返回 Top K

        注: 生产环境可用 sqlite-vec 扩展或专业向量数据库
        """
        rows = self.conn.execute(
            "SELECT * FROM chunks WHERE embedding IS NOT NULL"
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
                snippet=self._truncate(row['text'], 500)
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

    def search_keyword(self, query: str, limit: int = 10) -> List[SearchResult]:
        """
        关键词检索 - LIKE 模糊匹配

        CowAgent 实现:
        - FTS5 (英文友好): MATCH 查询
        - LIKE (中文回退): 模糊匹配

        简化版: 仅保留 LIKE
        """
        # 提取关键词
        keywords = self._extract_keywords(query)
        if not keywords:
            return []

        # 构建 LIKE 条件
        conditions = " OR ".join(["text LIKE ?"] * len(keywords))
        params = [f"%{kw}%" for kw in keywords]
        params.append(limit)

        sql = f"SELECT * FROM chunks WHERE {conditions} LIMIT ?"
        rows = self.conn.execute(sql, params).fetchall()

        return [
            SearchResult(
                path=row['path'],
                start_line=row['start_line'],
                end_line=row['end_line'],
                score=0.5,  # LIKE 匹配固定分数
                snippet=self._truncate(row['text'], 500)
            )
            for row in rows
        ]

    @staticmethod
    def _extract_keywords(query: str) -> List[str]:
        """提取关键词"""
        # 中文词 (2字以上)
        cjk = re.findall(r'[\u4e00-\u9fff]{2,}', query)
        # 英文词
        en = re.findall(r'[A-Za-z]{2,}', query)
        return cjk + en

    # ==================== 用户隔离检索 ====================

    def search_for_user(
        self,
        query: str,
        user_id: str,
        limit: int = 10,
        include_shared: bool = True
    ) -> List[SearchResult]:
        """
        用户隔离的关键词检索

        Args:
            query: 搜索关键词
            user_id: 用户 ID
            limit: 返回数量
            include_shared: 是否包含共享记忆

        Returns:
            搜索结果列表

        检索规则:
        - shared 记忆: 所有用户可见
        - user 记忆: 仅该用户可见（user_id 匹配）
        - session 记忆: 不在此搜索范围
        """
        keywords = self._extract_keywords(query)
        if not keywords:
            return []

        # 构建 LIKE 条件
        like_conditions = " OR ".join(["text LIKE ?"] * len(keywords))
        like_params = [f"%{kw}%" for kw in keywords]

        # 构建权限条件
        if include_shared:
            # shared 或 (user 且 user_id 匹配)
            permission_sql = "(scope = 'shared' OR (scope = 'user' AND user_id = ?))"
            params = like_params + [user_id, limit]
        else:
            # 仅用户私有
            permission_sql = "scope = 'user' AND user_id = ?"
            params = like_params + [user_id, limit]

        sql = f"""
            SELECT * FROM chunks
            WHERE ({like_conditions}) AND {permission_sql}
            LIMIT ?
        """

        rows = self.conn.execute(sql, params).fetchall()

        return [
            SearchResult(
                path=row['path'],
                start_line=row['start_line'],
                end_line=row['end_line'],
                score=0.5,
                snippet=self._truncate(row['text'], 500),
                scope=row['scope'],
                user_id=row['user_id']
            )
            for row in rows
        ]

    def search_hybrid_for_user(
        self,
        query: str,
        query_embedding: List[float],
        user_id: str,
        limit: int = 10,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3,
        include_shared: bool = True
    ) -> List[SearchResult]:
        """
        用户隔离的混合检索

        Args:
            query: 搜索关键词
            query_embedding: 查询向量
            user_id: 用户 ID
            limit: 返回数量
            vector_weight: 向量权重
            keyword_weight: 关键词权重
            include_shared: 是否包含共享记忆
        """
        # 向量检索（带用户隔离）
        vector_results = self._search_vector_for_user(query_embedding, user_id, limit * 2, include_shared)
        # 关键词检索（带用户隔离）
        keyword_results = self.search_for_user(query, user_id, limit * 2, include_shared)

        # 合并结果
        merged = {}
        for r in vector_results:
            key = (r.path, r.start_line, r.end_line)
            merged[key] = {'result': r, 'vector_score': r.score, 'keyword_score': 0.0}

        for r in keyword_results:
            key = (r.path, r.start_line, r.end_line)
            if key in merged:
                merged[key]['keyword_score'] = r.score
            else:
                merged[key] = {'result': r, 'vector_score': 0.0, 'keyword_score': r.score}

        # 计算最终分数
        results = []
        for key, entry in merged.items():
            combined = (vector_weight * entry['vector_score'] +
                       keyword_weight * entry['keyword_score'])
            decay = self._compute_temporal_decay(entry['result'].path)
            final_score = combined * decay

            results.append(SearchResult(
                path=entry['result'].path,
                start_line=entry['result'].start_line,
                end_line=entry['result'].end_line,
                score=final_score,
                snippet=entry['result'].snippet,
                scope=entry['result'].scope,
                user_id=entry['result'].user_id
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]

    def _search_vector_for_user(
        self,
        query_embedding: List[float],
        user_id: str,
        limit: int,
        include_shared: bool
    ) -> List[SearchResult]:
        """用户隔离的向量检索"""
        # 构建权限条件
        if include_shared:
            permission_sql = "(scope = 'shared' OR (scope = 'user' AND user_id = ?))"
            rows = self.conn.execute(
                f"SELECT * FROM chunks WHERE embedding IS NOT NULL AND {permission_sql}",
                (user_id,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM chunks WHERE embedding IS NOT NULL AND scope = 'user' AND user_id = ?",
                (user_id,)
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

    # ==================== 混合检索 ====================

    def search_hybrid(
        self,
        query: str,
        query_embedding: List[float],
        limit: int = 10,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3
    ) -> List[SearchResult]:
        """
        混合检索 - 加权融合

        CowAgent 实现:
        1. 分别执行向量检索和关键词检索
        2. 合并结果，按 path 去重
        3. 加权计算最终分数
        4. 应用时间衰减 (日期文件)
        """
        vector_results = self.search_vector(query_embedding, limit * 2)
        keyword_results = self.search_keyword(query, limit * 2)

        # 合并结果
        merged = {}  # (path, start, end) -> {vector_score, keyword_score}

        for r in vector_results:
            key = (r.path, r.start_line, r.end_line)
            merged[key] = {'result': r, 'vector_score': r.score, 'keyword_score': 0.0}

        for r in keyword_results:
            key = (r.path, r.start_line, r.end_line)
            if key in merged:
                merged[key]['keyword_score'] = r.score
            else:
                merged[key] = {'result': r, 'vector_score': 0.0, 'keyword_score': r.score}

        # 计算最终分数
        results = []
        for key, entry in merged.items():
            combined = (vector_weight * entry['vector_score'] +
                       keyword_weight * entry['keyword_score'])

            # 时间衰减
            decay = self._compute_temporal_decay(entry['result'].path)
            final_score = combined * decay

            results.append(SearchResult(
                path=entry['result'].path,
                start_line=entry['result'].start_line,
                end_line=entry['result'].end_line,
                score=final_score,
                snippet=entry['result'].snippet
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]

    @staticmethod
    def _compute_temporal_decay(path: str, half_life_days: float = 30.0) -> float:
        """
        时间衰减 - 日期记忆权重降低

        CowAgent 实现:
        - MEMORY.md: 不衰减 (evergreen)
        - memory/2024-01-01.md: 按日期衰减

        公式: multiplier = exp(-ln2/half_life * age_days)
        """
        match = re.search(r'(\d{4})-(\d{2})-(\d{2})\.md$', path)
        if not match:
            return 1.0  # evergreen

        try:
            file_date = datetime(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3))
            )
            age_days = (datetime.now() - file_date).days
            if age_days <= 0:
                return 1.0

            decay_lambda = math.log(2) / half_life_days
            return math.exp(-decay_lambda * age_days)
        except:
            return 1.0

    @staticmethod
    def _truncate(text: str, max_chars: int) -> str:
        """截断文本"""
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "..."

    def close(self):
        """关闭连接"""
        self.conn.close()
