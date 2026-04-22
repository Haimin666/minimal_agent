"""Agent 主类 - 三层记忆架构"""

from typing import List, Optional, Dict, Any
import json
import requests
from pathlib import Path
import re

try:
    from .config import Config
    from .context import Context, Message
    from .context_store import get_context_store
    from .memory import MemoryManager, MemoryStorage, MemoryFlusher, DeepDream
    from .memory.embedding import EmbeddingProvider
    from .prompt import PromptBuilder
    from .tools.file_tools import FileOperationsTool
except ImportError:
    from config import Config
    from context import Context, Message
    from context_store import get_context_store
    from memory import MemoryManager, MemoryStorage, MemoryFlusher, DeepDream
    from memory.embedding import EmbeddingProvider
    from prompt import PromptBuilder
    from tools.file_tools import FileOperationsTool


# 工具定义（OpenAI 格式）
TOOLS_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "memory_save",
            "description": "保存重要信息到长期记忆。当用户告诉你关于他/她自己的信息、偏好、背景、重要事件时，应该调用此工具保存。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "要保存的记忆内容，应该简洁明确，例如：'用户是王教授，在清华大学任教'"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "语义标签，用于提高检索效果。例如：用户说'我是语文老师'，标签应为 ['职业:教师', '科目:语文']。常用标签类型：职业、科目、爱好、地点、姓名"
                    },
                    "reason": {
                        "type": "string",
                        "description": "保存原因，例如：'用户更正了个人信息'"
                    }
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "memory_search",
            "description": "搜索长期记忆，查找相关信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词"
                    }
                },
                "required": ["query"]
            }
        }
    },
    # 文件操作工具
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "读取工作空间内的文件内容，仅限项目目录内",
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


class SimpleAgent:
    """
    Agent 实现 - 三层记忆架构

    记忆层级:
    - 短期记忆: Context.messages (内存 + SQLite 持久化)
    - 中期记忆: YYYY-MM-DD.md (上下文裁剪时 Flush)
    - 长期记忆: MEMORY.md (退出时 Deep Dream 蒸馏)

    核心流程:
    1. 构建系统提示词 (PromptBuilder)
    2. 搜索相关记忆 (MemoryManager.search - 仅向量检索)
    3. 构建消息列表 (Context)
    4. 调用 LLM API（支持工具调用）
    5. 执行工具调用（如 memory_save）
    6. 保存对话历史（可能触发裁剪 → Flush）
    """

    def __init__(self, config: Config = None, user_id: str = None):
        self.config = config or Config()
        self.user_id = user_id

        # 初始化嵌入模型
        self.embedding_provider = EmbeddingProvider(
            model=self.config.embedding_model,
            api_key=self.config.embedding_api_key,
            api_base=self.config.embedding_api_base,
            dimensions=self.config.embedding_dimensions
        )

        # 确保工作空间存在
        self._init_workspace()

        # 存储层（在 workspace 目录下）
        memory_db_path = Path(self.config.workspace_dir) / self.config.db_path
        self.storage = MemoryStorage(str(memory_db_path))

        self.memory_manager = MemoryManager(
            storage=self.storage,
            embedding_provider=self.embedding_provider,
            workspace_dir=self.config.workspace_dir,
            chunk_max_tokens=self.config.chunk_max_tokens,
            chunk_overlap_tokens=self.config.chunk_overlap_tokens,
        )

        self.prompt_builder = PromptBuilder(self.config.workspace_dir)

        # 设置 context_store 路径（必须在创建 Context 之前）
        context_db_path = Path(self.config.workspace_dir) / self.config.context_db_path

        # 每个用户独立的上下文
        session_id = f"{user_id}_session" if user_id else "default"
        self.context = Context(
            session_id=session_id,
            user_id=user_id,
            max_turns=self.config.max_context_turns,
            db_path=str(context_db_path)
        )

        # 工具调用记录
        self.tool_calls_log = []

        # 文件操作工具（仅限工作空间目录）
        self.file_tool = FileOperationsTool(self.config.workspace_dir)

        # 每日记忆 flush
        self.flusher = MemoryFlusher(
            workspace_dir=self.config.workspace_dir,
            embedding_provider=self.embedding_provider,
            memory_manager=self.memory_manager
        )

        # Deep Dream 蒸馏
        self.deep_dream = DeepDream(
            workspace_dir=self.config.workspace_dir,
            embedding_provider=self.embedding_provider,
            memory_manager=self.memory_manager
        )

        # 同步文件记忆到数据库（增量同步）
        self._sync_memory()

    def _init_workspace(self):
        """初始化工作空间"""
        workspace = Path(self.config.workspace_dir)
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "memory").mkdir(exist_ok=True)
        (workspace / "memory" / "shared").mkdir(exist_ok=True)
        (workspace / "memory" / "users").mkdir(exist_ok=True)

        # 创建默认文件
        agent_file = workspace / "AGENT.md"
        if not agent_file.exists():
            agent_file.write_text("# AGENT.md\n\n我是 AI 助手。\n", encoding='utf-8')

        memory_file = workspace / "MEMORY.md"
        if not memory_file.exists():
            memory_file.write_text("# MEMORY.md\n\n长期记忆索引。\n", encoding='utf-8')

    def _sync_memory(self):
        """同步文件记忆到数据库"""
        try:
            self.memory_manager.sync_from_files()
        except Exception as e:
            # 同步失败不影响启动
            print(f"[WARN] 记忆同步失败: {e}")

    def chat(self, user_input: str) -> Dict[str, Any]:
        """
        处理用户输入

        Returns:
            {
                "response": str,           # 助手回复
                "tool_calls": list,        # 工具调用记录
                "memories_found": int,     # 检索到的记忆数
                "flushed": bool            # 是否触发了 flush
            }
        """
        self.tool_calls_log = []
        flushed = False

        # 1. 构建系统提示词
        context_files = self.prompt_builder.load_context_files()

        system_prompt = self._build_system_prompt(context_files)

        # 2. 搜索相关记忆（混合检索：向量 + 关键词）
        memories = self.memory_manager.search(
            query=user_input,
            user_id=self.user_id,
            limit=5,
            include_shared=True
        )

        # 3. 构建消息列表
        messages = [{"role": "system", "content": system_prompt}]

        # 注入记忆上下文
        if memories:
            memory_context = "## 相关记忆\n\n"
            for m in memories[:3]:
                scope_tag = "共享" if m.scope == "shared" else "私有"
                memory_context += f"- [{scope_tag}] {m.snippet[:200]}\n"
            messages.append({"role": "system", "content": memory_context})

        # 添加历史消息（带上下文摘要）
        messages.extend(self.context.get_messages_with_summary())

        # 添加当前输入
        messages.append({"role": "user", "content": user_input})

        # 4. 调用 LLM（支持工具调用）
        response = self._call_llm_with_tools(messages)

        # 5. 保存历史（可能触发裁剪）
        discarded = self.context.add_message("user", user_input)
        self.context.add_message("assistant", response["content"])

        # 6. 如果触发了裁剪，flush 被裁剪的消息并注入摘要
        if discarded:
            self._flush_discarded(discarded)
            flushed = True

        return {
            "response": response["content"],
            "tool_calls": self.tool_calls_log,
            "memories_found": len(memories),
            "flushed": flushed
        }

    def _build_system_prompt(self, context_files: list) -> str:
        """构建系统提示词"""
        from datetime import datetime

        base_prompt = """你是一个智能助手，具有长期记忆能力和文件操作能力。

## 记忆能力

你可以通过工具保存和检索记忆：
- `memory_save`: 保存重要信息到长期记忆
- `memory_search`: 搜索已有记忆

## 何时保存记忆

当用户告诉你以下信息时，应该主动保存：
1. 用户的个人信息（姓名、职业、身份等）
2. 用户的偏好和习惯
3. 用户更正之前的信息
4. 用户提到的重要事件或计划
5. 用户明确要求"记住"的内容

## 保存记忆的格式

保存时内容应该简洁明确，例如：
- "用户是王教授，在清华大学任教"
- "用户喜欢听古典音乐"
- "用户明天要去上海出差"

不要保存：
- 临时性的对话内容
- 问候语和闲聊
- 可以随时查到的常识

## 文件操作能力

你可以通过工具操作工作空间内的文件：
- `file_read`: 读取文件内容
- `file_write`: 写入文件（创建或覆盖）
- `file_edit`: 编辑文件（替换文本）
- `file_list`: 列出目录内容

安全限制：只能在工作空间目录内操作，不能访问目录外的文件。
"""

        # 添加上下文文件内容
        if context_files:
            base_prompt += "\n\n## 项目上下文\n"
            for f in context_files:
                base_prompt += f"\n### {f.path}\n{f.content}\n"

        # 添加运行时信息
        base_prompt += f"\n\n## 当前状态\n"
        base_prompt += f"- 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        base_prompt += f"- 用户: {self.user_id or '未指定'}\n"

        return base_prompt

    def _call_llm_with_tools(self, messages: List[Dict]) -> Dict[str, Any]:
        """调用 LLM 并处理工具调用"""
        max_iterations = 3  # 最多 3 轮工具调用

        for iteration in range(max_iterations):
            # 调用 LLM
            response = requests.post(
                f"{self.config.api_base}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.config.api_key}"
                },
                json={
                    "model": self.config.model,
                    "messages": messages,
                    "tools": TOOLS_DEFINITION,
                    "tool_choice": "auto"
                },
                timeout=60
            )

            if response.status_code != 200:
                raise Exception(f"LLM 调用失败: {response.status_code} - {response.text}")

            result = response.json()
            message = result["choices"][0]["message"]

            # 检查是否有工具调用
            if message.get("tool_calls"):
                # 添加助手消息到历史
                messages.append(message)

                # 处理每个工具调用
                for tool_call in message["tool_calls"]:
                    tool_name = tool_call["function"]["name"]
                    tool_args = json.loads(tool_call["function"]["arguments"])
                    tool_call_id = tool_call["id"]

                    # 执行工具
                    tool_result = self._execute_tool(tool_name, tool_args)

                    # 添加工具结果到消息
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": json.dumps(tool_result, ensure_ascii=False)
                    })

                # 继续循环，让 LLM 生成最终回复
                continue

            # 没有工具调用，返回最终回复
            content = message.get("content") or ""
            return {"content": content}

        # 超过最大迭代次数
        return {"content": "抱歉，处理过程中出现问题。"}

    def _execute_tool(self, tool_name: str, tool_args: Dict) -> Dict:
        """执行工具调用"""
        if tool_name == "memory_save":
            content = tool_args.get("content", "")
            reason = tool_args.get("reason", "")
            tags = tool_args.get("tags", [])

            # 保存记忆（带标签）
            path = self.add_memory(content, scope="user", tags=tags)

            self.tool_calls_log.append({
                "tool": "memory_save",
                "content": content,
                "tags": tags,
                "reason": reason,
                "path": path
            })

            return {
                "success": True,
                "message": f"已保存记忆: {content[:50]}..." + (f" [标签: {', '.join(tags)}]" if tags else ""),
                "path": path
            }

        elif tool_name == "memory_search":
            query = tool_args.get("query", "")

            results = self.memory_manager.search(
                query=query,
                user_id=self.user_id,
                limit=5
            )

            self.tool_calls_log.append({
                "tool": "memory_search",
                "query": query,
                "results_count": len(results)
            })

            return {
                "success": True,
                "results": [
                    {
                        "content": r.snippet[:100],
                        "path": r.path,
                        "score": round(r.score, 3)
                    }
                    for r in results
                ]
            }

        # 文件操作工具
        elif tool_name == "file_read":
            path = tool_args.get("path", "")
            result = self.file_tool.read(path)

            self.tool_calls_log.append({
                "tool": "file_read",
                "path": path,
                "success": result.success
            })

            return {
                "success": result.success,
                "content": result.content
            }

        elif tool_name == "file_write":
            path = tool_args.get("path", "")
            content = tool_args.get("content", "")
            result = self.file_tool.write(path, content)

            self.tool_calls_log.append({
                "tool": "file_write",
                "path": path,
                "success": result.success
            })

            return {
                "success": result.success,
                "message": result.content
            }

        elif tool_name == "file_edit":
            path = tool_args.get("path", "")
            old_text = tool_args.get("old_text", "")
            new_text = tool_args.get("new_text", "")
            result = self.file_tool.edit(path, old_text, new_text)

            self.tool_calls_log.append({
                "tool": "file_edit",
                "path": path,
                "success": result.success
            })

            return {
                "success": result.success,
                "message": result.content
            }

        elif tool_name == "file_list":
            path = tool_args.get("path", ".")
            result = self.file_tool.list_dir(path)

            self.tool_calls_log.append({
                "tool": "file_list",
                "path": path
            })

            return {
                "success": result.success,
                "content": result.content
            }

        else:
            return {"success": False, "error": f"未知工具: {tool_name}"}

    def add_memory(self, content: str, scope: str = "user", tags: List[str] = None):
        """添加记忆（带标签）"""
        return self.memory_manager.add_memory(
            content=content,
            user_id=self.user_id,
            scope=scope,
            tags=tags or []
        )

    def clear_history(self):
        """清空对话历史"""
        self.context.clear()

    def _flush_discarded(self, messages: List[Message]):
        """
        Flush 被裁剪的消息到每日记忆，并注入上下文摘要

        流程：
        1. 调用 LLM 总结被裁剪的消息
        2. 写入每日记忆文件
        3. 注入摘要到当前对话（保持上下文连续性）
        """
        msg_dicts = [{"role": m.role, "content": m.content} for m in messages]

        # 创建摘要注入回调
        def on_summary_ready(summary: str):
            self.context.inject_context_summary(summary)

        self.flusher.flush_messages(
            messages=msg_dicts,
            user_id=self.user_id,
            api_base=self.config.api_base,
            api_key=self.config.api_key,
            model=self.config.model,
            context_summary_callback=on_summary_ready
        )

    def flush(self) -> bool:
        """
        手动 flush 当前对话到每日记忆

        Returns:
            是否成功写入
        """
        messages = self.context.get_openai_messages()
        return self.flusher.flush_messages(
            messages=messages,
            user_id=self.user_id,
            api_base=self.config.api_base,
            api_key=self.config.api_key,
            model=self.config.model
        )

    def distill(self, lookback_days: int = None) -> bool:
        """
        手动触发记忆蒸馏

        Args:
            lookback_days: 回看天数（默认使用配置值）

        Returns:
            是否成功执行蒸馏
        """
        lookback = lookback_days or self.config.deep_dream_lookback
        return self.deep_dream.distill_with_config(
            user_id=self.user_id,
            lookback_days=lookback,
            api_base=self.config.api_base,
            api_key=self.config.api_key,
            model=self.config.model
        )

    def exit(self):
        """
        退出时处理

        流程:
        1. Flush 剩余对话到每日记忆
        2. Deep Dream 蒸馏近期记忆
        3. 保存上下文
        """
        # 1. Flush 剩余对话
        if self.context.messages:
            self.flush()

        # 2. Deep Dream 蒸馏
        self.distill()

        # 3. 保存上下文（自动保存已启用，这里显式确认）
        self.context._save_history()
