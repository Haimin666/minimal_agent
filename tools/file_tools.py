"""文件操作工具 - file_read, file_write, file_edit"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path
import os


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


class FileOperationsTool:
    """
    文件操作工具 - 仅限工作空间目录内操作

    安全限制：
    - 只能操作 workspace_dir 及其子目录
    - 不能访问父目录
    - 不能访问符号链接指向的目录外文件
    """

    name = "file_operations"
    description = "读取、写入、编辑工作空间内的文件（仅限项目目录）"

    def __init__(self, workspace_dir: str = "./workspace"):
        self.workspace_dir = Path(workspace_dir).resolve()

    def _safe_path(self, path: str) -> Optional[Path]:
        """
        安全路径检查

        确保路径在 workspace_dir 内
        """
        try:
            # 解析绝对路径
            target = (self.workspace_dir / path).resolve()

            # 检查是否在允许的目录内
            if not str(target).startswith(str(self.workspace_dir)):
                return None

            # 检查是否是符号链接且指向目录外
            if target.is_symlink():
                real_target = target.resolve()
                if not str(real_target).startswith(str(self.workspace_dir)):
                    return None

            return target
        except Exception:
            return None

    def read(self, path: str) -> ToolResult:
        """读取文件内容"""
        safe_path = self._safe_path(path)
        if not safe_path:
            return ToolResult.fail(f"访问被拒绝: {path} 不在工作空间内")

        if not safe_path.exists():
            return ToolResult.fail(f"文件不存在: {path}")

        if not safe_path.is_file():
            return ToolResult.fail(f"不是文件: {path}")

        try:
            content = safe_path.read_text(encoding='utf-8')
            return ToolResult.ok(f"文件: {path}\n\n{content}")
        except Exception as e:
            return ToolResult.fail(f"读取失败: {str(e)}")

    def write(self, path: str, content: str) -> ToolResult:
        """写入文件（创建或覆盖）"""
        safe_path = self._safe_path(path)
        if not safe_path:
            return ToolResult.fail(f"访问被拒绝: {path} 不在工作空间内")

        try:
            # 创建父目录
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            # 写入文件
            safe_path.write_text(content, encoding='utf-8')
            return ToolResult.ok(f"已写入: {path} ({len(content)} 字符)")
        except Exception as e:
            return ToolResult.fail(f"写入失败: {str(e)}")

    def edit(self, path: str, old_text: str, new_text: str) -> ToolResult:
        """编辑文件（替换文本）"""
        safe_path = self._safe_path(path)
        if not safe_path:
            return ToolResult.fail(f"访问被拒绝: {path} 不在工作空间内")

        if not safe_path.exists():
            return ToolResult.fail(f"文件不存在: {path}")

        try:
            content = safe_path.read_text(encoding='utf-8')

            if old_text not in content:
                return ToolResult.fail(f"未找到要替换的文本")

            # 替换文本
            new_content = content.replace(old_text, new_text, 1)
            safe_path.write_text(new_content, encoding='utf-8')

            return ToolResult.ok(f"已编辑: {path}\n替换: {len(old_text)} 字符 -> {len(new_text)} 字符")
        except Exception as e:
            return ToolResult.fail(f"编辑失败: {str(e)}")

    def list_dir(self, path: str = ".") -> ToolResult:
        """列出目录内容"""
        safe_path = self._safe_path(path)
        if not safe_path:
            return ToolResult.fail(f"访问被拒绝: {path} 不在工作空间内")

        if not safe_path.exists():
            return ToolResult.fail(f"目录不存在: {path}")

        if not safe_path.is_dir():
            return ToolResult.fail(f"不是目录: {path}")

        try:
            items = []
            for item in sorted(safe_path.iterdir()):
                item_type = "📁" if item.is_dir() else "📄"
                items.append(f"{item_type} {item.name}")

            return ToolResult.ok(f"目录: {path}\n\n" + "\n".join(items))
        except Exception as e:
            return ToolResult.fail(f"列出失败: {str(e)}")

    def delete(self, path: str) -> ToolResult:
        """删除文件"""
        safe_path = self._safe_path(path)
        if not safe_path:
            return ToolResult.fail(f"访问被拒绝: {path} 不在工作空间内")

        if not safe_path.exists():
            return ToolResult.fail(f"文件不存在: {path}")

        try:
            if safe_path.is_file():
                safe_path.unlink()
            else:
                # 不允许删除目录，防止误操作
                return ToolResult.fail(f"只能删除文件，不能删除目录")

            return ToolResult.ok(f"已删除: {path}")
        except Exception as e:
            return ToolResult.fail(f"删除失败: {str(e)}")

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        """执行文件操作"""
        operation = args.get("operation")

        if operation == "read":
            return self.read(args.get("path", ""))
        elif operation == "write":
            return self.write(args.get("path", ""), args.get("content", ""))
        elif operation == "edit":
            return self.edit(
                args.get("path", ""),
                args.get("old_text", ""),
                args.get("new_text", "")
            )
        elif operation == "list":
            return self.list_dir(args.get("path", "."))
        elif operation == "delete":
            return self.delete(args.get("path", ""))
        else:
            return ToolResult.fail(f"未知操作: {operation}")


# OpenAI 工具定义格式
FILE_TOOLS_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "读取工作空间内的文件内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径（相对于工作空间根目录）"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": "写入文件（创建或覆盖），仅限工作空间目录内",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径（相对于工作空间根目录）"
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的内容"
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file_edit",
            "description": "编辑文件（替换文本），仅限工作空间目录内",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径（相对于工作空间根目录）"
                    },
                    "old_text": {
                        "type": "string",
                        "description": "要替换的文本"
                    },
                    "new_text": {
                        "type": "string",
                        "description": "替换后的文本"
                    }
                },
                "required": ["path", "old_text", "new_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file_list",
            "description": "列出工作空间目录内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "目录路径（默认为根目录）",
                        "default": "."
                    }
                }
            }
        }
    }
]
