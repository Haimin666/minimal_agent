#!/usr/bin/env python3
"""
真实 LLM 对话测试 - 带记忆隔离

测试：
1. 创建两个用户 Agent
2. 每个用户添加私有记忆
3. 添加共享记忆
4. 验证记忆隔离
5. 真实 LLM 对话
"""

import sys
import os
# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from config import Config
from agent import SimpleAgent
from memory import MemoryStorage, MemoryChunk
import shutil


def clean_test_workspace():
    """清理测试工作空间"""
    test_dir = "./demo/test_workspace"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir, exist_ok=True)


def test_memory_isolation():
    """测试记忆隔离"""
    print("\n" + "=" * 60)
    print("🧪 记忆隔离测试")
    print("=" * 60)

    clean_test_workspace()

    # 创建配置
    config = Config()
    config.db_path = "./demo/test_workspace/test.db"
    config.workspace_dir = "./demo/test_workspace"

    print(f"\n对话模型: {config.model}")
    print(f"嵌入模型: {config.embedding_model}")

    # 创建共享存储
    storage = MemoryStorage(config.db_path)

    # 添加共享记忆
    print("\n📚 添加共享记忆...")
    storage.save_chunk(MemoryChunk(
        id="shared_1",
        text="Python 是一种流行的编程语言，适合 AI 开发。",
        path="shared/python.md",
        scope="shared",
        user_id=None
    ))

    # 为用户 A 添加私有记忆
    print("👤 添加用户 A 的私有记忆...")
    storage.save_chunk(MemoryChunk(
        id="user_a_1",
        text="用户 A 喜欢 Java，是一名后端工程师。",
        path="users/user_a/profile.md",
        scope="user",
        user_id="user_a"
    ))
    storage.save_chunk(MemoryChunk(
        id="user_a_2",
        text="用户 A 正在学习 Spring Boot 框架。",
        path="users/user_a/learning.md",
        scope="user",
        user_id="user_a"
    ))

    # 为用户 B 添加私有记忆
    print("👤 添加用户 B 的私有记忆...")
    storage.save_chunk(MemoryChunk(
        id="user_b_1",
        text="用户 B 喜欢 Python，是一名 AI 工程师。",
        path="users/user_b/profile.md",
        scope="user",
        user_id="user_b"
    ))
    storage.save_chunk(MemoryChunk(
        id="user_b_2",
        text="用户 B 正在学习 LangChain 框架。",
        path="users/user_b/learning.md",
        scope="user",
        user_id="user_b"
    ))

    # 测试隔离检索
    print("\n" + "-" * 40)
    print("🔍 测试记忆隔离检索")
    print("-" * 40)

    # 用户 A 搜索 "编程"
    print("\n用户 A 搜索 '编程':")
    results_a = storage.search_for_user("编程", "user_a", limit=5)
    for r in results_a:
        scope_tag = "🌐共享" if r.scope == "shared" else "👤私有"
        print(f"  [{scope_tag}] {r.snippet[:50]}...")

    # 用户 B 搜索 "编程"
    print("\n用户 B 搜索 '编程':")
    results_b = storage.search_for_user("编程", "user_b", limit=5)
    for r in results_b:
        scope_tag = "🌐共享" if r.scope == "shared" else "👤私有"
        print(f"  [{scope_tag}] {r.snippet[:50]}...")

    print("\n✅ 记忆隔离测试完成！")


def test_real_chat():
    """测试真实 LLM 对话"""
    print("\n" + "=" * 60)
    print("🤖 真实 LLM 对话测试")
    print("=" * 60)

    clean_test_workspace()

    # 创建配置
    config = Config()
    config.db_path = "./demo/test_workspace/chat.db"
    config.workspace_dir = "./demo/test_workspace"

    # 创建用户 A 的 Agent
    print("\n创建用户 A 的 Agent...")
    agent_a = SimpleAgent(config, user_id="user_a")
    agent_a.add_memory("用户 A 是一名律师，擅长公司法。", scope="user")
    agent_a.add_memory("用户 A 最近在处理一起并购案。", scope="user")

    # 创建用户 B 的 Agent
    print("创建用户 B 的 Agent...")
    agent_b = SimpleAgent(config, user_id="user_b")
    agent_b.add_memory("用户 B 是一名医生，在三甲医院工作。", scope="user")
    agent_b.add_memory("用户 B 最近在做 AI 辅助诊断的研究。", scope="user")

    # 添加共享记忆
    print("添加共享记忆...")
    agent_a.add_memory("今天是 2026 年 4 月 20 日。", scope="shared")

    # 用户 A 对话
    print("\n" + "-" * 40)
    print("👤 用户 A 对话")
    print("-" * 40)
    response_a = agent_a.chat("你好，我最近在忙什么工作？")
    print(f"\n🤖 助手: {response_a}")

    # 用户 B 对话
    print("\n" + "-" * 40)
    print("👤 用户 B 对话")
    print("-" * 40)
    response_b = agent_b.chat("你好，我最近在忙什么工作？")
    print(f"\n🤖 助手: {response_b}")

    print("\n✅ 真实对话测试完成！")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("🚀 Minimal Agent 测试")
    print("=" * 60)

    # 先测试记忆隔离（不需要 LLM）
    test_memory_isolation()

    # 再测试真实对话
    test_real_chat()

    print("\n" + "=" * 60)
    print("✨ 所有测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
