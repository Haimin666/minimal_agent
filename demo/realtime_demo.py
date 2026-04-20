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
from config import Config
from agent import SimpleAgent
from memory import MemoryStorage, MemoryChunk
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
        self.config = Config()
        self.config.db_path = "./demo/realtime_workspace/demo.db"
        self.config.workspace_dir = "./demo/realtime_workspace"

        # 确保目录存在
        os.makedirs("./demo/realtime_workspace", exist_ok=True)

        self.agent = None
        self.user_id = None
        self.dialogue_count = 0

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
            'history', 'prompt', 'messages', 'memory', 'clear', 'save', 'q', 'help'
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
        print("  1. 王老师 (高中语文老师)")
        print("  2. 李教授 (大学教授)")
        print("  3. 张码农 (全栈开发工程师)")
        print("  4. 刘总   (公司CEO)")
        print("  5. 周医生 (三甲医院主任医师)")
        print("  6. DJ阿杰 (酒吧DJ)")
        print("  7. 孙教练 (健身教练)")
        print("  8. 老王   (网约车司机)")
        print("  9. 新用户 (自定义)")
        print("-" * 50)

        try:
            choice = input("\n请输入选项 (1-9): ").strip()
        except EOFError:
            return

        user_profiles = {
            "1": ("teacher", "王老师", "高中语文老师", "热爱教育，喜欢听有声书，关心学生成长"),
            "2": ("professor", "李教授", "大学教授", "学术研究，经常参加学术会议，关注科研动态"),
            "3": ("developer", "张码农", "全栈开发工程师", "互联网大厂程序员，加班多，热爱技术"),
            "4": ("boss", "刘总", "公司CEO", "企业老板，商务应酬多，时间宝贵"),
            "5": ("doctor", "周医生", "三甲医院主任医师", "救死扶伤，工作繁忙，责任心强"),
            "6": ("dj", "DJ阿杰", "酒吧DJ", "夜生活工作者，音乐狂热，个性张扬"),
            "7": ("coach", "孙教练", "健身教练", "热爱运动，注重健康，精力充沛"),
            "8": ("driver", "老王", "网约车司机", "全职司机，熟悉城市道路，服务态度好"),
        }

        if choice in user_profiles:
            self.user_id, name, profession, background = user_profiles[choice]
            print(f"\n✅ 已选择用户: {name} ({profession})")

            # 创建 Agent（静默模式）
            self._create_agent_silent()

            # 添加初始记忆
            self._save_memory_silent(f"{name} 是一名{profession}，{background}")

        elif choice == "9":
            try:
                self.user_id = input("请输入用户ID: ").strip() or "new_user"
                name = input("请输入姓名: ").strip() or "新用户"
                profession = input("请输入职业: ").strip() or "未指定"
                background = input("请输入背景简介: ").strip()

                self._create_agent_silent()
                self._save_memory_silent(f"{name} 是一名{profession}，{background}")
                print(f"\n✅ 已创建用户: {name}")
            except EOFError:
                return
        else:
            print("使用默认用户")
            self.user_id = "default_user"
            self._create_agent_silent()

        # 进入交互
        self.interactive_loop()

    def _create_agent_silent(self):
        """静默创建 Agent"""
        with contextlib.redirect_stdout(io.StringIO()):
            self.agent = SimpleAgent(self.config, user_id=self.user_id)

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

            else:
                # 对话
                self.chat(user_input)

    def _do_save_memory(self, content: str):
        """保存记忆并显示详情"""
        import hashlib

        # 生成路径
        content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
        path = f"memory/users/{self.user_id}/memory_{content_hash}.md"

        # 写入文件
        file_path = self.agent.memory_manager.workspace_dir / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding='utf-8')

        # 保存到数据库
        with contextlib.redirect_stdout(io.StringIO()):
            self.agent.add_memory(content, scope="user")

        print(f"\n[INFO] 记忆存入")
        print(f"  文件: {path}")
        print(f"  内容: {content[:100]}{'...' if len(content) > 100 else ''}")
        print(f"  范围: 用户私有 (user_id={self.user_id})")

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
            query_embedding = self.agent.embedding_provider.embed(user_input)

        print(f"  向量化: {self.config.embedding_model}, 维度={len(query_embedding)}")

        memories = self.agent.storage.search_hybrid_for_user(
            query=user_input,
            query_embedding=query_embedding,
            user_id=self.user_id,
            limit=3
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
            query_embedding = self.agent.embedding_provider.embed(query)

        memories = self.agent.storage.search_hybrid_for_user(
            query=query,
            query_embedding=query_embedding,
            user_id=self.user_id,
            limit=10
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
                query_embedding = self.agent.embedding_provider.embed(last_user_msg)
            memories = self.agent.storage.search_hybrid_for_user(
                query=last_user_msg,
                query_embedding=query_embedding,
                user_id=self.user_id,
                limit=3
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
║  clear          清空对话历史                                         ║
║  help           显示此帮助                                           ║
║  q              退出                                                 ║
╠═══════════════════════════════════════════════════════════════════╣
║  快捷键:                                                            ║
║  ↑/↓            查看历史输入                                         ║
║  Tab            自动补全命令                                         ║
║  Ctrl+C         中断当前操作                                         ║
║  Ctrl+D         退出                                                 ║
╚═══════════════════════════════════════════════════════════════════╝
        """)


def main():
    demo = RealTimeDemo()
    demo.start()


if __name__ == "__main__":
    main()
