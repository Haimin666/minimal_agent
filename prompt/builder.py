"""Prompt 构建器 - 模块化注入"""

from typing import List, Optional, Any, Dict
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime


@dataclass
class ContextFile:
    """上下文文件"""
    path: str
    content: str


class PromptBuilder:
    """
    Prompt 构建器

    CowAgent 实现注入顺序:
    1. 🔧 工具系统
    2. 🧩 技能系统 (简化版删除)
    3. 🧠 记忆系统
    4. 📚 知识系统 (简化版删除)
    5. 📂 工作空间
    6. 👤 用户身份 (简化版删除)
    7. 📋 项目上下文
    8. ⚙️ 运行时信息

    简化版: 保留 1, 3, 5, 7, 8
    """

    def __init__(self, workspace_dir: str = "./workspace"):
        self.workspace_dir = Path(workspace_dir)

    def build(
        self,
        base_prompt: str = "你是一个有帮助的 AI 助手。",
        tools: List[Any] = None,
        memory_manager: Any = None,
        context_files: List[ContextFile] = None,
        runtime_info: Dict = None
    ) -> str:
        """构建完整系统提示词"""
        sections = []

        # 1. 基础提示词
        sections.append(base_prompt)

        # 2. 工具说明
        if tools:
            sections.append(self._build_tools_section(tools))

        # 3. 记忆系统说明
        if memory_manager:
            sections.append(self._build_memory_section())

        # 4. 工作空间
        sections.append(self._build_workspace_section())

        # 5. 上下文文件
        if context_files:
            sections.append(self._build_context_section(context_files))

        # 6. 运行时信息
        if runtime_info:
            sections.append(self._build_runtime_section(runtime_info))

        return "\n\n".join(sections)

    def _build_tools_section(self, tools: List) -> str:
        """构建工具说明"""
        lines = ["## 🔧 可用工具\n"]
        for tool in tools:
            name = getattr(tool, 'name', str(tool))
            desc = getattr(tool, 'description', '')
            lines.append(f"- **{name}**: {desc}")
        return "\n".join(lines)

    def _build_memory_section(self) -> str:
        """构建记忆系统说明"""
        today = datetime.now().strftime("%Y-%m-%d")
        return f"""## 🧠 记忆系统

### 检索记忆
- 使用 `memory_search` 搜索过往记忆
- 使用 `memory_get` 读取文件内容

### 记忆文件
- `MEMORY.md`: 长期记忆索引
- `memory/{today}.md`: 今日记忆

### 写入规则
- 重要信息应主动记录到 MEMORY.md
- 当天事件写入 memory/{today}.md"""

    def _build_workspace_section(self) -> str:
        """构建工作空间说明"""
        return f"""## 📂 工作空间

你的工作目录是: `{self.workspace_dir}`

目录结构:
- `AGENT.md` - 你的人格设定
- `MEMORY.md` - 长期记忆索引
- `memory/` - 每日记忆"""

    def _build_context_section(self, files: List[ContextFile]) -> str:
        """构建上下文文件内容"""
        lines = ["## 📋 项目上下文\n"]
        for f in files:
            lines.append(f"### {f.path}\n")
            lines.append(f.content)
            lines.append("")
        return "\n".join(lines)

    def _build_runtime_section(self, info: Dict) -> str:
        """构建运行时信息"""
        lines = ["## ⚙️ 运行时信息\n"]
        for k, v in info.items():
            lines.append(f"- {k}: {v}")
        return "\n".join(lines)

    def load_context_files(self) -> List[ContextFile]:
        """加载上下文文件"""
        files = []
        for filename in ["AGENT.md", "MEMORY.md"]:
            path = self.workspace_dir / filename
            if path.exists():
                content = path.read_text(encoding='utf-8').strip()
                if content:
                    files.append(ContextFile(path=filename, content=content))
        return files
