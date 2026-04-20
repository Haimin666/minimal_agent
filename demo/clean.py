#!/usr/bin/env python3
"""
一键清理脚本 - 清除所有历史对话和记忆
"""

import os
import shutil
from pathlib import Path


def clean_all():
    """清理所有数据"""
    print("\n" + "=" * 60)
    print("🧹 一键清理 - 清除所有历史对话和记忆")
    print("=" * 60)

    # demo 目录下的工作空间
    demo_dir = Path(__file__).parent

    to_clean = [
        demo_dir / "workspace",
        demo_dir / "realtime_workspace",
        demo_dir / "test_workspace",
        demo_dir / "demo.db",
        demo_dir / "realtime.db",
        demo_dir / "test.db",
    ]

    # 根目录下的工作空间
    root_dir = demo_dir.parent
    to_clean.extend([
        root_dir / "workspace",
        root_dir / "memory.db",
    ])

    cleaned = []
    for item in to_clean:
        if item.exists():
            if item.is_dir():
                shutil.rmtree(item)
                cleaned.append(f"📁 目录: {item}")
            else:
                item.unlink()
                cleaned.append(f"📄 文件: {item}")

    if cleaned:
        print("\n   已清理:")
        for item in cleaned:
            print(f"      ✅ {item}")
    else:
        print("\n   无需清理，已经是初始状态")

    print("\n" + "=" * 60)
    print("✨ 清理完成！可以重新开始")
    print("=" * 60)


if __name__ == "__main__":
    clean_all()
