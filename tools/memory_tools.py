"""记忆工具 - memory_search 和 memory_get"""

from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    content: str

    @classmethod
    def ok(cls, content: str):
        return cls(success=True, content=content)

    @classmethod
    def fail(cls, content: str):
        return cls(success=False, content=content)


class MemorySearchTool:
    """
    记忆搜索工具

    CowAgent 实现:
    - name: memory_search
    - description: 搜索记忆
    - params: {query, max_results, min_score}
    """

    name = "memory_search"
    description = "搜索长期记忆，支持语义和关键词检索"
    params = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询"},
            "max_results": {"type": "integer", "default": 10}
        },
        "required": ["query"]
    }

    def __init__(self, memory_manager):
        self.memory_manager = memory_manager

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        """执行搜索"""
        query = args.get("query")
        max_results = args.get("max_results", 10)

        if not query:
            return ToolResult.fail("query 参数必填")

        results = self.memory_manager.search(query, limit=max_results)

        if not results:
            return ToolResult.ok("未找到相关记忆")

        # 格式化输出
        lines = [f"找到 {len(results)} 条相关记忆:\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r.path} (行 {r.start_line}-{r.end_line})")
            lines.append(f"   相似度: {r.score:.3f}")
            lines.append(f"   摘要: {r.snippet[:100]}...")

        return ToolResult.ok("\n".join(lines))


class MemoryGetTool:
    """
    文件读取工具

    CowAgent 实现:
    - name: memory_get
    - description: 读取记忆文件
    - params: {path, start_line, num_lines}
    """

    name = "memory_get"
    description = "读取记忆文件内容"
    params = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "start_line": {"type": "integer", "default": 1},
            "num_lines": {"type": "integer"}
        },
        "required": ["path"]
    }

    def __init__(self, memory_manager):
        self.memory_manager = memory_manager

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        """执行读取"""
        path = args.get("path")
        start_line = args.get("start_line", 1)
        num_lines = args.get("num_lines")

        if not path:
            return ToolResult.fail("path 参数必填")

        content = self.memory_manager.get_file_content(path, start_line, num_lines)

        if content is None:
            return ToolResult.fail(f"文件不存在: {path}")

        return ToolResult.ok(f"文件: {path}\n\n{content}")
