"""
Deep Dream - 记忆蒸馏

将天级记忆 (YYYY-MM-DD.md) 蒸馏为长期记忆 (MEMORY.md)

功能:
    - 读取 MEMORY.md + 近期天级记忆
    - LLM 整理：去重、合并、冲突更新
    - 覆写 MEMORY.md
    - 限制条目数量 (~50 条)
"""

from typing import List, Dict, Optional, Any
from pathlib import Path
from datetime import datetime, timedelta
import hashlib


# LLM 蒸馏提示词
DISTILL_SYSTEM_PROMPT = """你是一个记忆整理助手，负责定期整理用户的长期记忆。

你将收到两份材料：
1. **当前长期记忆** — MEMORY.md 的全部现有内容
2. **近期日记** — 最近几天的日常记录

MEMORY.md 会注入每次对话的系统提示词中，因此必须保持精炼，只存放有价值和值得记忆的内容。

**重要：只能基于提供的材料进行整理，严禁编造、推测或添加材料中不存在的信息。**

## 核心任务：精简与去重

### 1. 必须删除的内容
- **重复信息**：同一信息出现多次，只保留最精炼的一条
- **过时信息**：带有"明天"、"下周"等时间词且已过期的内容
- **临时事件**：某天的具体行程、某次具体的上课内容（这些属于日记，不是长期记忆）
- **格式残留**：`[标签]` 标记、空白条目、无意义符号
- **冗余表述**：多条信息说的同一件事

### 2. 冲突检测与处理（重要）
当发现矛盾信息时，按以下规则处理：
- **职业变更**：如"是语文老师" vs "改教数学" → 保留最新的职业信息
- **身份更正**：如"是老师" vs "不是老师，是医生" → 以更正后的为准
- **偏好更新**：如"喜欢吃香菜" vs "不吃香菜" → 以最新偏好为准
- **信息修正**：带有"其实"、"实际上"、"改了"、"换了"等词的信息优先级更高

### 3. 必须合并的内容
- 同一主题的多条信息 → 合并为一条
- 同一事实的不同表述 → 保留最新最准确的

### 4. 应该保留的内容
- **身份信息**：姓名、职业、身份
- **偏好习惯**：饮食偏好、兴趣爱好、生活习惯
- **重要地点**：住址、常去地点
- **重要关系**：家人、朋友、同事
- **长期计划**：持续进行的事项

## 输出规范

- 每条一行，用 "- " 开头
- 使用 "## 标题" 分组（如：## 基本信息、## 偏好、## 习惯）
- 控制在 20 条以内
- 每条一句话，不超过 30 字

## 示例

输入（混乱）：
```
- 王老师是一名高中语文老师
- 用户改教数学了
- 今天去第一中学上课，讲了《红楼梦》第三回
- 明天要带教案去学校
- 喜欢吃火锅，不吃香菜和羊肉
```

输出（精简）：
```
[MEMORY]
## 基本信息
- 王老师，高中数学老师（原教语文）

## 偏好
- 喜欢吃火锅，不吃香菜和羊肉
```

注意：职业已更新为数学老师，临时事件和过时信息已删除。"""

DISTILL_USER_PROMPT = """## 当前长期记忆（MEMORY.md）

{long_term_memory}

## 近期日记（最近 {days} 天）

{daily_memory}

## 输出要求

1. 删除所有重复、过时、临时性内容
2. 合并同类信息
3. 按分组输出（## 基本信息、## 偏好、## 习惯等）
4. 控制在 20 条以内

直接输出整理后的长期记忆（必须包含 [MEMORY] 标记）："""


class DeepDream:
    """
    记忆蒸馏器

    将天级记忆蒸馏为长期记忆，类似睡眠时的记忆整理过程。
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

        # 最大记忆条目数
        self.max_items = 50
        # 回看天数
        self.lookback_days = 3

        # 语义组织器（用于格式化输出）
        try:
            from .semantic_organizer import SemanticOrganizer
            self.semantic_organizer = SemanticOrganizer(embedding_provider)
        except ImportError:
            from semantic_organizer import SemanticOrganizer
            self.semantic_organizer = SemanticOrganizer(embedding_provider)

    def distill(
        self,
        user_id: Optional[str] = None,
        lookback_days: int = None
    ) -> bool:
        """
        蒸馏近期记忆

        Args:
            user_id: 用户 ID（None 表示共享记忆）
            lookback_days: 回看天数

        Returns:
            是否成功执行蒸馏
        """
        lookback = lookback_days or self.lookback_days

        # 1. 读取长期记忆
        long_term = self._read_long_term_memory(user_id)

        # 2. 读取近期天级记忆
        daily_memories = self._read_recent_daily_memories(user_id, lookback)

        if not long_term and not daily_memories:
            return False

        # 3. LLM 蒸馏
        distilled = self._distill_with_llm(long_term, daily_memories)

        if not distilled:
            return False

        # 4. 覆写 MEMORY.md
        self._write_long_term_memory(distilled, user_id)

        # 5. 同步到数据库
        if self.memory_manager:
            try:
                self.memory_manager.sync_from_files()
            except Exception:
                pass

        return True

    def _read_long_term_memory(self, user_id: Optional[str] = None) -> str:
        """读取长期记忆文件"""
        if user_id:
            memory_file = self.memory_dir / "users" / user_id / "MEMORY.md"
        else:
            memory_file = self.workspace_dir / "MEMORY.md"

        if not memory_file.exists():
            return ""

        content = memory_file.read_text(encoding="utf-8")
        # 移除标题行
        lines = [l for l in content.split("\n") if not l.startswith("#")]
        return "\n".join(lines).strip()

    def _read_recent_daily_memories(
        self,
        user_id: Optional[str] = None,
        days: int = 3
    ) -> str:
        """读取近期的天级记忆"""
        memories = []

        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")

            if user_id:
                daily_file = self.memory_dir / "users" / user_id / f"{date_str}.md"
            else:
                daily_file = self.memory_dir / f"{date_str}.md"

            if daily_file.exists():
                content = daily_file.read_text(encoding="utf-8")
                # 移除标题和空行
                lines = [
                    l for l in content.split("\n")
                    if l.strip() and not l.startswith("#")
                ]
                if lines:
                    memories.append(f"### {date_str}\n" + "\n".join(lines))

        return "\n\n".join(memories)

    def _distill_with_llm(
        self,
        long_term: str,
        daily: str,
        api_base: str = None,
        api_key: str = None,
        model: str = None
    ) -> str:
        """
        调用 LLM 蒸馏记忆

        注意: 需要在调用时传入 API 配置
        """
        # 这个方法会在 agent.py 中被调用，传入实际的 API 配置
        # 这里只是一个占位实现
        raise NotImplementedError("请在调用时传入 api_base, api_key, model")

    def distill_with_config(
        self,
        user_id: Optional[str],
        lookback_days: int,
        api_base: str,
        api_key: str,
        model: str
    ) -> bool:
        """带 API 配置的蒸馏方法"""
        lookback = lookback_days or self.lookback_days

        # 读取记忆
        long_term = self._read_long_term_memory(user_id)
        daily_memories = self._read_recent_daily_memories(user_id, lookback)

        if not long_term and not daily_memories:
            return False

        # LLM 蒸馏
        distilled = self._call_llm_distill(
            long_term, daily_memories, api_base, api_key, model
        )

        if not distilled:
            return False

        # 覆写 MEMORY.md
        self._write_long_term_memory(distilled, user_id)

        # 同步到数据库
        if self.memory_manager:
            try:
                self.memory_manager.sync_from_files()
            except Exception:
                pass

        return True

    def _call_llm_distill(
        self,
        long_term: str,
        daily: str,
        api_base: str,
        api_key: str,
        model: str
    ) -> str:
        """调用 LLM 执行蒸馏"""
        try:
            import requests

            # 根据输入大小动态调整 max_tokens
            input_chars = len(long_term) + len(daily)
            max_tokens = max(2000, min(input_chars, 8000))

            response = requests.post(
                f"{api_base}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": DISTILL_SYSTEM_PROMPT},
                        {"role": "user", "content": DISTILL_USER_PROMPT.format(
                            long_term_memory=long_term or "(empty)",
                            days=self.lookback_days,
                            daily_memory=daily or "(no recent daily records)"
                        )}
                    ],
                    "temperature": 0.3,
                    "max_tokens": max_tokens
                },
                timeout=60
            )

            if response.status_code == 200:
                raw = response.json()["choices"][0]["message"]["content"].strip()
                # 解析 [MEMORY] 部分
                return self._parse_memory_output(raw)

        except Exception as e:
            print(f"[DeepDream] LLM 蒸馏失败: {e}")

        return ""

    @staticmethod
    def _parse_memory_output(raw: str) -> str:
        """解析 LLM 输出，提取 [MEMORY] 部分"""
        raw = raw.strip().replace("```", "")

        if "[MEMORY]" in raw:
            start = raw.index("[MEMORY]") + len("[MEMORY]")
            # 如果有 [DREAM] 标记，截取到它之前
            end = raw.index("[DREAM]") if "[DREAM]" in raw else len(raw)
            return raw[start:end].strip()

        # 如果没有 [MEMORY] 标记，返回原始内容
        return raw

    def _write_long_term_memory(self, content: str, user_id: Optional[str] = None):
        """写入长期记忆文件 - 使用 SemanticOrganizer 格式化"""
        if user_id:
            memory_file = self.memory_dir / "users" / user_id / "MEMORY.md"
            memory_file.parent.mkdir(parents=True, exist_ok=True)
        else:
            memory_file = self.workspace_dir / "MEMORY.md"

        # 解析内容为条目列表
        lines = content.strip().split("\n")
        items = []
        for line in lines:
            line = line.strip()
            if line.startswith("- "):
                items.append(line[2:])  # 移除 "- " 前缀
            elif line.startswith("-"):
                items.append(line[1:])
            elif line and not line.startswith("#"):
                items.append(line)

        # 限制条目数
        items = items[:self.max_items]

        if not items:
            return

        # 使用 SemanticOrganizer 格式化写入
        today = datetime.now().strftime("%Y-%m-%d")
        header = f"# MEMORY.md\n\n最后更新: {today}"

        self.semantic_organizer.organize_and_write(memory_file, items, header)
