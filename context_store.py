"""
Session 历史持久化 - SQLite 存储

功能:
    - 保存对话历史到 SQLite
    - 重启时恢复最近 N 轮对话
    - 支持多用户隔离
"""

import sqlite3
import json
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime


class ContextStore:
    """
    Session 历史持久化存储

    表结构:
        sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT,
            messages TEXT,        -- JSON 格式的消息列表
            created_at INTEGER,
            updated_at INTEGER
        )
    """

    def __init__(self, db_path: str = "context.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT,
                messages TEXT,
                created_at INTEGER DEFAULT (strftime('%s', 'now')),
                updated_at INTEGER DEFAULT (strftime('%s', 'now'))
            )
        """)
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)"
        )
        self.conn.commit()

    def save_messages(self, session_id: str, messages: List[Dict], user_id: str = None):
        """
        保存对话历史

        Args:
            session_id: 会话 ID
            messages: 消息列表 [{"role": "user/assistant", "content": "..."}]
            user_id: 用户 ID
        """
        messages_json = json.dumps(messages, ensure_ascii=False)

        self.conn.execute("""
            INSERT OR REPLACE INTO sessions (session_id, user_id, messages, updated_at)
            VALUES (?, ?, ?, strftime('%s', 'now'))
        """, (session_id, user_id, messages_json))
        self.conn.commit()

    def load_messages(
        self,
        session_id: str,
        max_turns: int = 20
    ) -> List[Dict]:
        """
        加载对话历史

        Args:
            session_id: 会话 ID
            max_turns: 最大恢复轮数（1轮 = 1问 + 1答）

        Returns:
            消息列表
        """
        row = self.conn.execute(
            "SELECT messages FROM sessions WHERE session_id = ?",
            (session_id,)
        ).fetchone()

        if not row:
            return []

        try:
            messages = json.loads(row['messages'])
        except json.JSONDecodeError:
            return []

        # 过滤：只保留 user 和 assistant 的文本消息
        filtered = self._filter_text_messages(messages)

        # 限制轮数
        if max_turns > 0:
            # 每轮包含 user + assistant，所以最多 max_turns * 2 条
            max_messages = max_turns * 2
            if len(filtered) > max_messages:
                filtered = filtered[-max_messages:]

        return filtered

    def clear_session(self, session_id: str):
        """清空指定会话"""
        self.conn.execute(
            "DELETE FROM sessions WHERE session_id = ?",
            (session_id,)
        )
        self.conn.commit()

    def clear_user_sessions(self, user_id: str):
        """清空用户所有会话"""
        self.conn.execute(
            "DELETE FROM sessions WHERE user_id = ?",
            (user_id,)
        )
        self.conn.commit()

    def get_stats(self) -> Dict:
        """获取统计信息"""
        count = self.conn.execute(
            "SELECT COUNT(*) FROM sessions"
        ).fetchone()[0]
        return {"sessions": count}

    def get_all_users(self) -> List[str]:
        """获取所有有会话记录的用户 ID 列表（按最近更新时间排序）"""
        rows = self.conn.execute(
            "SELECT DISTINCT user_id FROM sessions WHERE user_id IS NOT NULL ORDER BY updated_at DESC"
        ).fetchall()
        return [row['user_id'] for row in rows]

    @staticmethod
    def _filter_text_messages(messages: List[Dict]) -> List[Dict]:
        """
        过滤消息：只保留 user 和 assistant 的文本消息

        原因：
        1. tool_use/tool_result 是中间过程，占用大量 token
        2. 不同模型的 tool 格式不兼容
        3. 最终答案已包含工具调用的结果
        """
        filtered = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            # 只保留 user 和 assistant
            if role not in ("user", "assistant"):
                continue

            # 提取文本内容
            if isinstance(content, str):
                text = content.strip()
            elif isinstance(content, list):
                # Claude 格式: [{"type": "text", "text": "..."}]
                parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        parts.append(block)
                text = "\n".join(p for p in parts if p).strip()
            else:
                continue

            if text:
                filtered.append({"role": role, "content": text})

        return filtered

    def close(self):
        """关闭连接"""
        self.conn.close()


# 全局单例（按 db_path 存储）
_context_stores: Dict[str, ContextStore] = {}


def get_context_store(db_path: str = None) -> ContextStore:
    """获取或创建 ContextStore 实例（按 db_path 缓存）"""
    if db_path is None:
        db_path = "context.db"

    if db_path not in _context_stores:
        _context_stores[db_path] = ContextStore(db_path)

    return _context_stores[db_path]


def reset_context_store():
    """重置全局单例（用于测试）"""
    global _context_stores
    for store in _context_stores.values():
        try:
            store.close()
        except Exception:
            pass
    _context_stores = {}
