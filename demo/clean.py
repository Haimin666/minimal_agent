#!/usr/bin/env python3
"""
重置 Agent - 删除所有用户数据和记忆

功能:
    1. 删除 workspace/memory 目录（用户数据）
    2. 删除 SQLite 数据库文件
    3. 保留 AGENT.md、MEMORY.md（人格设定和长期记忆索引）

使用:
    python demo/clean.py
"""

import os
import shutil
from pathlib import Path


def reset_agent():
    """重置 Agent 到初始状态"""
    print("\n" + "=" * 60)
    print("🔄 重置 Agent - 删除所有用户数据和记忆")
    print("=" * 60)

    # 项目根目录
    root_dir = Path(__file__).parent.parent

    # 要清理的目录（只清理 memory，保留 AGENT.md 和 MEMORY.md）
    memory_dir = root_dir / "workspace" / "memory"

    # 要清理的数据库文件
    db_files = [
        root_dir / "workspace" / "memory.db",      # 记忆向量数据库
        root_dir / "workspace" / "context.db",     # Session 历史数据库
    ]

    cleaned = []

    # 清理 memory 目录
    if memory_dir.exists():
        shutil.rmtree(memory_dir)
        cleaned.append(f"📁 目录: workspace/memory/")

    # 清理数据库文件
    for db_file in db_files:
        if db_file.exists():
            db_file.unlink()
            cleaned.append(f"📄 文件: {db_file.name}")

    if cleaned:
        print("\n   已清理:")
        for item in cleaned:
            print(f"      ✅ {item}")
    else:
        print("\n   无需清理，已经是初始状态")

    # 重建 memory 目录结构
    workspace_dir = root_dir / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "memory").mkdir(exist_ok=True)
    (workspace_dir / "memory" / "shared").mkdir(exist_ok=True)
    (workspace_dir / "memory" / "users").mkdir(exist_ok=True)

    # 确保 AGENT.md 存在
    agent_file = workspace_dir / "AGENT.md"
    if not agent_file.exists():
        agent_file.write_text("""# AGENT.md

我是 AI 助手，具有长期记忆能力。

## 能力

- 记住用户的重要信息
- 检索过往记忆
- 文件操作（限于工作空间）

## 行为准则

- 简洁回复
- 主动记忆重要信息
- 保护用户隐私
""", encoding='utf-8')

    # 确保 MEMORY.md 存在
    memory_file = workspace_dir / "MEMORY.md"
    if not memory_file.exists():
        memory_file.write_text("""# MEMORY.md

长期记忆索引。

## 用户信息

<!-- LLM 会自动在此添加用户相关信息 -->

## 偏好设置

<!-- 用户的偏好和习惯 -->

## 重要事件

<!-- 用户提到的重要事件 -->
""", encoding='utf-8')

    print("\n   已保留/创建:")
    print(f"      📄 workspace/AGENT.md")
    print(f"      📄 workspace/MEMORY.md")

    print("\n   已重建目录:")
    print(f"      📁 workspace/memory/shared/")
    print(f"      📁 workspace/memory/users/")

    print("\n" + "=" * 60)
    print("✨ 重置完成！运行 python demo/realtime_demo.py 开始")
    print("=" * 60)


if __name__ == "__main__":
    reset_agent()
