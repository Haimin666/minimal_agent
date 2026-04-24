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
DISTILL_SYSTEM_PROMPT = """你是一个记忆整理助手，负责将混乱的记忆整理为结构化的长期记忆。

你将收到两份材料：
1. **当前长期记忆** — MEMORY.md 的全部现有内容（可能已混乱）
2. **近期日记** — 最近几天的日常记录

## 核心原则

**必须严格去重**：这是最重要的任务。同一信息无论以何种形式出现多次，只保留一条最精炼的。

## 处理规则

### 必须删除
1. **完全重复**：内容相同或高度相似的条目
2. **子集重复**：如"热爱教育"和"热爱教育，喜欢听有声书"，删除前者
3. **过时信息**：带"明天"、"下周"等时间词且已过期的内容
4. **临时事件**：某天具体行程、某次具体上课内容（属于日记，非长期记忆）
5. **格式残留**：`[标签]` 标记、空白条目、无意义符号
6. **无意义条目**：如单独的"热爱热爱教育"这种残缺内容

### 必须合并
- 同一主题的多条 → 合并为一条完整描述
- 同一事实的不同表述 → 保留最新最准确的
- 身份信息分散 → 合并为一条完整介绍

### 保留内容
- 身份信息（姓名、职业、身份）
- 偏好习惯（饮食、兴趣、生活习惯）
- 重要地点和关系
- 待办事项（仅保留未过期的）

## 输出格式

```
[MEMORY]
## 基本信息
- 姓名、职业、身份等

## 偏好
- 饮食、兴趣等偏好

## 习惯
- 生活习惯

## 重要事项
- 待办或重要提醒
```

## 示例

输入（混乱）：
```
- 王老师 是一名高中语文老师
- 性格：温和耐心，注重细节
- 简介：热爱教育，喜欢听有声书，关心学生成长
- 热爱热爱教育
- 今天去第一中学上课，讲了《红楼梦》第三回
- 提醒自己明天要带教案去学校
- 身份信息：王老师，高中语文老师
- 性格特点：温和耐心，注重细节
- 兴趣爱好：热爱教育，喜欢听有声书，关心学生成长
- 王老师是一名高中数学老师（原教语文）
- 喜欢听有声书
- 关心学生成长
- 性格温和耐心，注重细节
- 周三有家长会
```

输出（精简）：
```
[MEMORY]
## 基本信息
- 王老师，高中数学老师（从语文转岗）
- 性格温和耐心，注重细节

## 偏好
- 喜欢听有声书

## 习惯
- 关心学生成长

## 重要事项
- 周三有家长会
```

注意：
1. "热爱热爱教育"被删除（无意义残缺内容）
2. "喜欢听有声书"出现多次，只保留一条
3. "性格温和耐心"出现多次，合并为一条
4. 临时事件（具体上课内容）被删除
5. 身份信息合并为一条完整描述"""

DISTILL_USER_PROMPT = """## 当前长期记忆（MEMORY.md）

{long_term_memory}

## 近期日记（最近 {days} 天）

{daily_memory}

## 处理要求

1. **严格去重**：同一信息只保留一条，无论它以何种形式出现
2. **合并同类**：分散的身份/偏好信息合并为完整描述
3. **删除无效**：临时事件、过时提醒、无意义残缺内容
4. **结构化输出**：按 ## 基本信息 / ## 偏好 / ## 习惯 / ## 重要事项 分组
5. **控制数量**：每类不超过 5 条

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
        """写入长期记忆文件"""
        if user_id:
            memory_file = self.memory_dir / "users" / user_id / "MEMORY.md"
            memory_file.parent.mkdir(parents=True, exist_ok=True)
        else:
            memory_file = self.workspace_dir / "MEMORY.md"

        # 限制条目数
        lines = content.strip().split("\n")
        items = [l for l in lines if l.strip().startswith("-")]
        items = items[:self.max_items]

        # 写入文件
        today = datetime.now().strftime("%Y-%m-%d")
        header = f"# MEMORY.md\n\n最后更新: {today}\n\n"
        memory_file.write_text(header + "\n".join(items) + "\n", encoding="utf-8")
