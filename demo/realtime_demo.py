#!/usr/bin/env python3
"""
🚗 汽车语音助手 - 真实场景交互 Demo (增强版)

启动命令:
    python demo/realtime_demo.py

功能:
    1. 选择/创建用户身份
    2. 进行多轮对话（真实 LLM + 自动记忆）
    3. 查看历史对话、系统提示词、记忆注入位置
    4. 支持命令补全、历史记录、多行编辑
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from pathlib import Path
from config import Config
from agent import SimpleAgent
from memory import MemoryStorage, MemoryChunk
from profession_generator import USER_TEMPLATES, generate_user_memory
import json
import io
import contextlib

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding import KeyBindings


class RealTimeDemo:
    """真实场景演示"""

    def __init__(self):
        # 获取项目根目录（demo 的父目录）
        project_root = Path(__file__).parent.parent

        self.config = Config()
        # 使用绝对路径，避免工作目录问题
        workspace_dir = project_root / "workspace"
        self.config.db_path = "memory.db"
        self.config.context_db_path = "context.db"
        self.config.workspace_dir = str(workspace_dir)

        # 确保目录存在
        workspace_dir.mkdir(parents=True, exist_ok=True)

        self.agent = None
        self.user_id = None
        self.dialogue_count = 0
        self.user_name = None
        self.user_template = None

        # 自定义样式
        self.style = Style.from_dict({
            'prompt': 'bold ansicyan',
            'user': 'bold ansigreen',
            'assistant': 'bold ansimagenta',
            'info': 'ansiyellow',
            'tool': 'bold ansiblue',
        })

        # 命令补全
        self.command_completer = WordCompleter([
            'history', 'prompt', 'messages', 'memory', 'save', 'flush', 'clear', 'q', 'help'
        ])

        # 历史记录
        history_dir = os.path.expanduser("~/.minimal_agent")
        os.makedirs(history_dir, exist_ok=True)
        self.session = PromptSession(
            history=FileHistory(f"{history_dir}/chat_history"),
            auto_suggest=AutoSuggestFromHistory(),
            completer=self.command_completer,
            style=self.style,
        )

    def start(self):
        """开始演示"""
        print("\n" + "=" * 70)
        print("🚗 汽车语音助手 - 真实场景交互 Demo")
        print("=" * 70)

        print(f"\n📡 模型配置:")
        print(f"   对话: {self.config.model} @ {self.config.api_base}")
        print(f"   嵌入: {self.config.embedding_model} @ {self.config.embedding_api_base}")

        # 选择或创建用户
        print("\n" + "-" * 50)
        print("请选择用户身份:")
        for i, (user_id, t) in enumerate(USER_TEMPLATES.items(), 1):
            print(f"  {i}. {t['name']:6} ({t['profession']})")
        print(f"  {len(USER_TEMPLATES) + 1}. 新用户 (自定义)")
        print("-" * 50)

        try:
            choice = input("\n请输入选项: ").strip()
        except EOFError:
            return

        # 用户选择映射
        user_ids = list(USER_TEMPLATES.keys())

        if choice.isdigit() and 1 <= int(choice) <= len(user_ids):
            self.user_id = user_ids[int(choice) - 1]
            self.user_template = USER_TEMPLATES[self.user_id]
            self.user_name = self.user_template['name']

            print(f"\n✅ 已选择用户: {self.user_name} ({self.user_template['profession']})")

            # 打印详细人设
            self._print_user_profile()

            # 创建 Agent
            self._create_agent_silent()

            # 生成记忆文件
            self._generate_user_memory()

        elif choice == str(len(user_ids) + 1):
            try:
                self.user_id = input("请输入用户ID或姓名: ").strip()
                if not self.user_id:
                    print("❌ 用户ID不能为空")
                    return

                # 使用输入作为用户ID和姓名
                self.user_name = self.user_id
                self.user_template = None  # 无人设，后续从对话中提炼

                print(f"\n✅ 新用户: {self.user_name}")
                print("   💡 无人设，后续将从对话中自动提炼记忆")

                self._create_agent_silent()

            except EOFError:
                return
        else:
            print("使用默认用户")
            self.user_id = "default_user"
            self.user_name = "用户"
            self._create_agent_silent()

        # 进入交互
        self.interactive_loop()

    def _print_user_profile(self):
        """打印用户详细人设"""
        t = self.user_template
        print(f"\n{'─' * 50}")
        print(f"📋 用户人设详情")
        print(f"{'─' * 50}")
        print(f"   👤 姓名: {t['name']}")
        print(f"   💼 职业: {t['profession']}")
        print(f"   🎭 性格: {t['personality']}")
        print(f"   📝 简介: {t['profile']}")
        if t['daily_events']:
            print(f"\n   📅 近期事件:")
            for event in t['daily_events'][:3]:
                print(f"      • {event[:40]}{'...' if len(event) > 40 else ''}")
        print(f"{'─' * 50}")

    def _generate_user_memory(self):
        """生成用户记忆文件"""
        today = datetime.now().strftime("%Y-%m-%d")

        with contextlib.redirect_stdout(io.StringIO()):
            result = generate_user_memory(self.user_id, self.user_template, self.config.workspace_dir)
            # 同步到数据库
            self.agent.memory_manager.sync_from_files()

        # 打印影响的文件和数据库
        print(f"\n   📁 已生成/更新以下文件:")
        print(f"      • workspace/memory/users/{self.user_id}/MEMORY.md")
        print(f"      • workspace/memory/users/{self.user_id}/{today}.md")
        print(f"\n   🗄️ 已同步到数据库:")
        print(f"      • memory.db (向量索引)")
        print(f"      • 共 {len(self.user_template['daily_events']) + 3} 条记忆块已索引")

    def _create_agent_silent(self):
        """创建 Agent 并检查历史会话"""
        with contextlib.redirect_stdout(io.StringIO()):
            self.agent = SimpleAgent(self.config, user_id=self.user_id)

        # 检查是否恢复了历史会话
        history = self.agent.context.get_openai_messages()
        if history:
            print(f"\n   📜 已恢复历史会话: {len(history)} 条消息")
            print(f"   💡 输入 'history' 查看详情")

    def _save_memory_silent(self, content: str):
        """静默保存记忆"""
        with contextlib.redirect_stdout(io.StringIO()):
            self.agent.add_memory(content, scope="user")
        print(f"   已加载用户背景记忆")

    def interactive_loop(self):
        """交互循环"""
        print("\n" + "=" * 70)
        print("💬 开始对话 (输入命令或直接聊天)")
        print("=" * 70)

        print("""
命令:
  <直接输入文字>    - 与助手对话
  history          - 查看历史对话
  prompt           - 查看系统提示词
  messages         - 查看完整消息列表
  memory <关键词>  - 搜索记忆
  save <内容>      - 主动保存记忆
  flush            - 总结对话并写入每日记忆
  clear            - 清空对话历史
  help             - 显示帮助
  q                - 退出

提示:
  - 按 ↑/↓ 查看历史输入
  - 按 Tab 自动补全命令
  - 支持 Ctrl+C 中断当前操作
        """)

        while True:
            try:
                # 使用 prompt_toolkit 获取输入
                user_input = self.session.prompt(
                    f"[{self.user_id}] 👤 ",
                ).strip()
            except KeyboardInterrupt:
                print("\n\n⚠️  按Ctrl+D退出，或继续输入...")
                continue
            except EOFError:
                print("\n👋 再见！")
                break

            if not user_input:
                continue

            # 解析命令
            parts = user_input.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""

            if cmd == "q":
                # 退出前自动总结对话
                self._auto_flush_on_exit()
                print("\n👋 再见！")
                break

            elif cmd == "help":
                self.show_help()

            elif cmd == "history":
                self.show_history()

            elif cmd == "prompt":
                self.show_prompt()

            elif cmd == "messages":
                self.show_messages()

            elif cmd == "memory":
                self.search_memory(arg or "最近")

            elif cmd == "clear":
                self.agent.clear_history()
                print("✅ 对话历史已清空")

            elif cmd == "save":
                if arg:
                    self._do_save_memory(arg)
                else:
                    print("❌ 用法: save <要保存的内容>")

            elif cmd == "flush":
                self._do_flush()

            else:
                # 对话
                self.chat(user_input)

    def _do_save_memory(self, content: str):
        """保存记忆并显示详情"""
        # 保存到数据库（自动写入日期文件）
        with contextlib.redirect_stdout(io.StringIO()):
            path = self.agent.add_memory(content, scope="user")

        print(f"\n[INFO] 记忆存入")
        print(f"  文件: {path}")
        print(f"  内容: {content[:100]}{'...' if len(content) > 100 else ''}")
        print(f"  范围: 用户私有 (user_id={self.user_id})")

    def _do_flush(self):
        """总结对话并写入每日记忆"""
        messages = self.agent.context.get_openai_messages()
        if not messages:
            print("⚠️  当前无对话历史，无需总结")
            return

        print(f"\n[INFO] 正在总结 {len(messages)} 条对话...")
        with contextlib.redirect_stdout(io.StringIO()):
            success = self.agent.flush()

        if success:
            from datetime import datetime
            today_file = f"memory/{self.user_id}/{datetime.now().strftime('%Y-%m-%d')}.md"
            print(f"✅ 对话已总结并写入每日记忆")
            print(f"   文件: {today_file}")
        else:
            print("ℹ️  对话内容无记录价值，未写入")

    def _auto_flush_on_exit(self):
        """退出时自动总结对话并蒸馏记忆"""
        # 调用 agent.exit() 完成完整的退出流程：
        # 1. Flush 剩余对话到每日记忆
        # 2. Deep Dream 蒸馏近期记忆 → 更新长期记忆
        # 3. 保存上下文
        print(f"\n🔄 正在处理退出流程...")

        # 检查是否有对话历史
        messages = self.agent.context.get_openai_messages()
        if messages:
            print(f"   1. 总结本次对话...")
            print(f"   2. 蒸馏近期记忆...")
        else:
            print(f"   1. 无对话需要总结")
            print(f"   2. 蒸馏近期记忆...")

        # 调用完整的 exit 流程
        self.agent.exit()

        # 获取今日文件路径
        from datetime import datetime
        today_file = f"memory/{self.user_id}/{datetime.now().strftime('%Y-%m-%d')}.md"
        print(f"✅ 退出处理完成")
        print(f"   每日记忆: {today_file}")
        print(f"   长期记忆: memory/{self.user_id}/MEMORY.md")

    def chat(self, user_input: str):
        """对话并展示详情"""
        self.dialogue_count += 1

        print(f"\n{'─' * 70}")
        print(f"📝 第 {self.dialogue_count} 轮对话")
        print(f"{'─' * 70}")

        # ========== 1. 记忆检索 ==========
        print(f"\n[INFO] 记忆检索")
        print(f"  查询: \"{user_input}\"")

        with contextlib.redirect_stdout(io.StringIO()):
            memories = self.agent.memory_manager.search(
                query=user_input,
                user_id=self.user_id,
                limit=3,
                include_shared=True
            )

        print(f"  结果: {len(memories)} 条")
        if memories:
            for i, m in enumerate(memories, 1):
                scope_tag = "私有" if m.scope == "user" else "共享"
                print(f"    [{i}] [{scope_tag}] {m.path}#L{m.start_line}-L{m.end_line}")
                print(f"        内容: {m.snippet[:60]}...")
                print(f"        分数: {m.score:.3f}")
        else:
            print(f"    (无相关记忆)")

        # ========== 2. Prompt 构建 ==========
        print(f"\n[INFO] Prompt 构建")

        context_files = self.agent.prompt_builder.load_context_files()
        system_prompt = self.agent._build_system_prompt(context_files)

        messages = [{"role": "system", "content": system_prompt}]

        memory_context = None
        if memories:
            memory_context = "## 相关记忆\n\n"
            for m in memories:
                scope_tag = "共享" if m.scope == "shared" else "私有"
                memory_context += f"- [{scope_tag}] {m.snippet[:100]}\n"
            messages.append({"role": "system", "content": memory_context})

        history = self.agent.context.get_openai_messages()
        messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        print(f"  系统提示词: {len(system_prompt)} 字符")
        if memory_context:
            print(f"  记忆上下文: {len(memory_context)} 字符 ⭐ 注入位置")
        print(f"  历史消息: {len(history)} 条")
        print(f"  总消息数: {len(messages)} 条")

        # ========== 3. LLM 调用 ==========
        print(f"\n[INFO] LLM 调用")
        print(f"  模型: {self.config.model}")

        with contextlib.redirect_stdout(io.StringIO()):
            result = self.agent.chat(user_input)

        response = result["response"]
        tool_calls = result["tool_calls"]

        # ========== 4. 工具调用 ==========
        if tool_calls:
            print(f"\n[INFO] 工具调用")
            for tc in tool_calls:
                if tc["tool"] == "memory_save":
                    print(f"  📝 memory_save")
                    print(f"     内容: {tc['content']}")
                    print(f"     原因: {tc.get('reason', '-')}")
                    print(f"     文件: {tc['path']}")
                elif tc["tool"] == "memory_search":
                    print(f"  🔍 memory_search")
                    print(f"     查询: {tc['query']}")
                    print(f"     结果: {tc['results_count']} 条")

        # ========== 5. 回答 ==========
        print(f"\n🤖 助手:")
        # 格式化输出，支持换行
        for line in response.split('\n'):
            print(f"  {line}")

    def search_memory(self, query: str):
        """搜索记忆"""
        print(f"\n[INFO] 记忆搜索: \"{query}\"")

        with contextlib.redirect_stdout(io.StringIO()):
            memories = self.agent.memory_manager.search(
                query=query,
                user_id=self.user_id,
                limit=10,
                include_shared=True
            )

        print(f"  结果: {len(memories)} 条\n")

        for i, m in enumerate(memories, 1):
            scope_tag = "私有" if m.scope == "user" else "共享"
            print(f"  [{i}] [{scope_tag}] {m.path}")
            print(f"      分数: {m.score:.3f}")
            print(f"      内容: {m.snippet[:80]}...")
            print()

    def show_history(self):
        """显示历史对话"""
        print("\n" + "=" * 70)
        print("📜 历史对话")
        print("=" * 70)

        messages = self.agent.context.get_openai_messages()

        if not messages:
            print("\n   (暂无对话历史)")
            return

        print(f"\n共 {len(messages)} 条消息:\n")

        for i, msg in enumerate(messages, 1):
            role = "👤 用户" if msg["role"] == "user" else "🤖 助手"
            content = msg["content"]
            if len(content) > 300:
                content = content[:300] + "..."
            print(f"{i}. {role}:")
            for line in content.split('\n')[:10]:
                print(f"   {line}")
            if len(content.split('\n')) > 10:
                print("   ...")
            print()

        total_chars = sum(len(m["content"]) for m in messages)
        print(f"📊 总字符数: {total_chars}, 估算 Token: ~{total_chars // 2}")

    def show_prompt(self):
        """显示系统提示词"""
        print("\n" + "=" * 70)
        print("📝 系统提示词 (System Prompt)")
        print("=" * 70)

        context_files = self.agent.prompt_builder.load_context_files()
        prompt = self.agent._build_system_prompt(context_files)

        print(f"\n长度: {len(prompt)} 字符\n")
        print("-" * 70)
        print(prompt)
        print("-" * 70)

    def show_messages(self):
        """显示完整消息列表"""
        print("\n" + "=" * 70)
        print("📨 完整消息列表 (发送给 LLM 的内容)")
        print("=" * 70)

        context_files = self.agent.prompt_builder.load_context_files()
        system_prompt = self.agent._build_system_prompt(context_files)

        history = self.agent.context.get_openai_messages()
        last_user_msg = None
        if history:
            for msg in reversed(history):
                if msg["role"] == "user":
                    last_user_msg = msg["content"]
                    break

        messages = [{"role": "system", "content": system_prompt}]

        if last_user_msg:
            with contextlib.redirect_stdout(io.StringIO()):
                memories = self.agent.memory_manager.search(
                    query=last_user_msg,
                    user_id=self.user_id,
                    limit=3,
                    include_shared=True
                )
            if memories:
                memory_context = "## 相关记忆\n\n"
                for m in memories:
                    scope_tag = "共享" if m.scope == "shared" else "私有"
                    memory_context += f"- [{scope_tag}] {m.snippet[:100]}\n"
                messages.append({"role": "system", "content": memory_context})

        messages.extend(history)

        print(f"\n消息总数: {len(messages)}")
        print("=" * 70)

        for i, msg in enumerate(messages, 1):
            role = msg["role"]
            content = msg["content"]

            if role == "system":
                if i == 1:
                    print(f"\n[{i}] 📝 系统提示词 ({len(content)} 字符)")
                else:
                    print(f"\n[{i}] 🧠 记忆上下文 ({len(content)} 字符) ⭐ 注入位置")
                    for line in content.split('\n')[:5]:
                        print(f"      {line}")
            elif role == "user":
                print(f"\n[{i}] 👤 用户消息 ({len(content)} 字符)")
                print(f"   {content[:100]}{'...' if len(content) > 100 else ''}")
            else:
                print(f"\n[{i}] 🤖 助手消息 ({len(content)} 字符)")
                print(f"   {content[:100]}{'...' if len(content) > 100 else ''}")

    def show_help(self):
        """显示帮助"""
        print("""
╔═══════════════════════════════════════════════════════════════════╗
║                           命令帮助                                  ║
╠═══════════════════════════════════════════════════════════════════╣
║  <直接输入>      与助手对话（支持自动记忆）                          ║
║  history        查看历史对话                                         ║
║  prompt         查看系统提示词                                       ║
║  messages       查看完整消息列表（含记忆注入位置）                    ║
║  memory <关键词> 搜索记忆                                            ║
║  save <内容>    主动保存记忆                                         ║
║  flush           总结对话并写入每日记忆                               ║
║  clear          清空对话历史                                         ║
║  help           显示此帮助                                           ║
║  q              退出（自动 flush + distill 更新长期记忆）             ║
╠═══════════════════════════════════════════════════════════════════╣
║  快捷键:                                                            ║
║  ↑/↓            查看历史输入                                         ║
║  Tab            自动补全命令                                         ║
║  Ctrl+C         中断当前操作                                         ║
║  Ctrl+D         退出                                                 ║
╠═══════════════════════════════════════════════════════════════════╣
║  退出流程:                                                          ║
║  1. Flush: 对话 → 每日记忆 (YYYY-MM-DD.md)                           ║
║  2. Distill: 每日记忆 → 长期记忆 (MEMORY.md)                         ║
╚═══════════════════════════════════════════════════════════════════╝
        """)


def main():
    demo = RealTimeDemo()
    demo.start()


if __name__ == "__main__":
    main()
