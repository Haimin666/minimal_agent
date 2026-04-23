"""
每日记忆 Flush - 对话总结写入 YYYY-MM-DD.md

功能:
    - LLM 总结对话内容
    - 写入每日记忆文件
    - 支持手动触发和自动触发
    - 上下文摘要注入（可选）
    - 语义组织：按标题分块 + 语义去重
"""

from typing import List, Dict, Optional, Any, Callable
from pathlib import Path
from datetime import datetime
import hashlib

try:
    from .semantic_organizer import SemanticOrganizer
except ImportError:
    from semantic_organizer import SemanticOrganizer


# LLM 总结提示词
SUMMARIZE_SYSTEM_PROMPT = """你是一个对话记录助手。请将对话内容归纳为当天的日常记录。

## 要求

按「事件」维度归纳发生的事，不要按对话轮次逐条记录：
- 每条一行，用 "- " 开头
- 合并同一件事的多轮对话
- 只记录有意义的事件，忽略闲聊和问候
- 保留关键的决策、结论和待办事项

当对话没有任何记录价值（仅含问候或无意义内容），直接回复"无"。

## 输出格式

直接输出记录条目，不要加任何前缀或解释。"""

SUMMARIZE_USER_PROMPT = """请归纳以下对话的日常记录：

{conversation}"""


class MemoryFlusher:
    """
    对话总结 Flush

    将对话历史总结后写入每日记忆文件（YYYY-MM-DD.md）
    支持语义组织：按标题分块 + 语义去重
    """

    def __init__(
        self,
        workspace_dir: str,
        embedding_provider: Any = None,
        memory_manager: Any = None
    ):
        self.workspace_dir = Path(workspace_dir)
        self.embedding_provider = embedding_provider
        self.memory_manager = memory_manager

        self.memory_dir = self.workspace_dir / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        # 内容去重
        self._last_flush_hash: str = ""

        # 语义组织器
        self.semantic_organizer = SemanticOrganizer(embedding_provider)

    def get_today_file(self, user_id: Optional[str] = None, ensure_exists: bool = False) -> Path:
        """获取今日记忆文件路径"""
        today = datetime.now().strftime("%Y-%m-%d")

        if user_id:
            user_dir = self.memory_dir / "users" / user_id
            if ensure_exists:
                user_dir.mkdir(parents=True, exist_ok=True)
            today_file = user_dir / f"{today}.md"
        else:
            today_file = self.memory_dir / f"{today}.md"

        if ensure_exists and not today_file.exists():
            today_file.write_text(f"# Daily Memory: {today}\n\n", encoding='utf-8')

        return today_file

    def flush_messages(
        self,
        messages: List[Dict],
        user_id: Optional[str] = None,
        llm_client: Any = None,
        api_base: str = None,
        api_key: str = None,
        model: str = None,
        context_summary_callback: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """
        总结对话并写入每日记忆

        Args:
            messages: 消息列表 [{"role": "user/assistant", "content": "..."}]
            user_id: 用户 ID
            llm_client: LLM 客户端（可选）
            api_base: API 地址
            api_key: API Key
            model: 模型名称
            context_summary_callback: 上下文摘要回调，用于注入摘要到当前对话

        Returns:
            是否成功写入
        """
        # 过滤有效消息
        conversation = self._format_conversation(messages)
        if not conversation.strip():
            return False

        # 去重
        content_hash = hashlib.md5(conversation.encode()).hexdigest()
        if content_hash == self._last_flush_hash:
            return False
        self._last_flush_hash = content_hash

        # LLM 总结
        summary = self._summarize_with_llm(
            conversation,
            llm_client,
            api_base,
            api_key,
            model
        )

        if not summary or summary.strip() == "无":
            return False

        # 写入文件
        self._write_daily(summary, user_id)

        # 上下文摘要注入回调
        if context_summary_callback:
            try:
                context_summary_callback(summary)
            except Exception:
                pass

        return True

    def _format_conversation(self, messages: List[Dict]) -> str:
        """格式化对话为文本"""
        lines = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if isinstance(content, list):
                # Claude 格式
                parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
                content = "\n".join(parts)

            if not content or not str(content).strip():
                continue

            if role == "user":
                lines.append(f"用户: {str(content)[:500]}")
            elif role == "assistant":
                lines.append(f"助手: {str(content)[:500]}")

        return "\n".join(lines)

    def _summarize_with_llm(
        self,
        conversation: str,
        llm_client: Any = None,
        api_base: str = None,
        api_key: str = None,
        model: str = None
    ) -> str:
        """调用 LLM 总结对话"""
        if not api_base or not api_key or not model:
            # 无 LLM 配置，使用规则提取
            return self._extract_summary_fallback(conversation)

        try:
            import requests

            response = requests.post(
                f"{api_base}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SUMMARIZE_SYSTEM_PROMPT},
                        {"role": "user", "content": SUMMARIZE_USER_PROMPT.format(conversation=conversation)}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 500
                },
                timeout=30
            )

            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"].strip()

        except Exception as e:
            pass

        return self._extract_summary_fallback(conversation)

    def _extract_summary_fallback(self, conversation: str) -> str:
        """规则提取总结（无 LLM 时的回退）"""
        lines = conversation.split("\n")
        events = []

        for line in lines:
            if line.startswith("用户:"):
                text = line[3:].strip()
                if len(text) > 5:
                    events.append(f"- 用户询问: {text[:80]}")

        return "\n".join(events[:5])

    def _write_daily(self, summary: str, user_id: Optional[str] = None):
        """写入每日记忆文件 - 使用语义组织器"""
        today_file = self.get_today_file(user_id, ensure_exists=True)

        # 解析 summary 为条目列表
        items = self._parse_summary_to_items(summary)
        if not items:
            return

        # 使用语义组织器写入
        header = f"# Daily Memory: {datetime.now().strftime('%Y-%m-%d')}"
        self.semantic_organizer.organize_and_write(today_file, items, header)

        # 同步到数据库
        if self.memory_manager:
            try:
                self.memory_manager.sync_from_files()
            except Exception:
                pass

    def _parse_summary_to_items(self, summary: str) -> List[str]:
        """解析 summary 为条目列表"""
        items = []
        for line in summary.split("\n"):
            line = line.strip()
            if not line:
                continue
            # 移除 "- " 前缀
            if line.startswith("- "):
                line = line[2:]
            # 跳过标题行
            if line.startswith("#"):
                continue
            items.append(line)
        return items
