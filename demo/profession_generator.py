#!/usr/bin/env python3
"""
用户 Mock 数据生成器

生成用户记忆文件到 workspace/memory 目录：
- workspace/memory/users/{user_id}/MEMORY.md  - 用户画像（长期记忆）
- workspace/memory/users/{user_id}/{date}.md  - 每日记忆（重要事件总结）

启动 Agent 时会自动同步这些文件到数据库。
修改文件后重启 Agent，记忆会增量更新。
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from pathlib import Path


# ==================== 用户模板 ====================

USER_TEMPLATES = {
    "teacher": {
        "name": "王老师",
        "profession": "高中语文老师",
        "personality": "温和耐心，注重细节",
        "profile": "热爱教育，喜欢听有声书，关心学生成长",
        "daily_events": [
            "今天去第一中学上课，讲了《红楼梦》第三回",
            "课后帮学生修改作文，发现几个学生的写作有明显进步",
            "在图书馆借了两本关于教学方法的书籍",
            "提醒自己明天要带教案去学校",
            "晚上听了《红楼梦》有声书，准备明天的课程内容",
        ],
    },

    "professor": {
        "name": "李教授",
        "profession": "大学教授",
        "personality": "严谨专业，思路开阔",
        "profile": "学术研究，经常参加学术会议，关注科研动态",
        "daily_events": [
            "今天去清华大学参加学术研讨会",
            "会上分享了关于 AI 在教育领域应用的研究成果",
            "与几位同行讨论了后续合作的可能性",
            "下午去首都机场，准备出差参加下周的学术会议",
            "提醒自己明天9点有学术会议，需要准备发言稿",
        ],
    },

    "developer": {
        "name": "张码农",
        "profession": "全栈开发工程师",
        "personality": "逻辑清晰，追求效率",
        "profile": "互联网大厂程序员，加班多，热爱技术",
        "daily_events": [
            "今天去中关村软件园上班",
            "上午完成了用户认证模块的代码重构",
            "下午参加技术评审，讨论新架构方案",
            "发现了一个性能瓶颈，用缓存方案解决了",
            "晚上加班到10点，解决了几个线上bug",
        ],
    },

    "boss": {
        "name": "刘总",
        "profession": "公司CEO",
        "personality": "决策果断，注重效率",
        "profile": "企业老板，商务应酬多，时间宝贵",
        "daily_events": [
            "今天早上7点到公司，先看了财务报表",
            "9点召开董事会，讨论了Q2的发展规划",
            "中午在国贸三期与投资人共进午餐",
            "下午去高尔夫球场接待重要客户",
            "提醒自己明天要准备季度总结报告",
        ],
    },

    "doctor": {
        "name": "周医生",
        "profession": "三甲医院主任医师",
        "personality": "认真负责，沉着冷静",
        "profile": "救死扶伤，工作繁忙，责任心强",
        "daily_events": [
            "今天去协和医院上班，上午做了三台手术",
            "手术都很顺利，病人情况稳定",
            "下午参加了医学研讨会，分享了一个疑难病例",
            "晚上查房后回医院值班",
            "提醒自己明天还有两台手术需要准备",
        ],
    },

    "dj": {
        "name": "DJ阿杰",
        "profession": "酒吧DJ",
        "personality": "个性张扬，热情奔放",
        "profile": "夜生活工作者，音乐狂热，追求潮流",
        "daily_events": [
            "昨晚在三里屯酒吧演出，气氛很嗨",
            "尝试了几首新歌的混音，效果不错",
            "下午在家休息，研究新的音乐制作软件",
            "和几个音乐人讨论了下周的合作计划",
            "提醒自己今晚10点有演出",
        ],
    },

    "coach": {
        "name": "孙教练",
        "profession": "健身教练",
        "personality": "精力充沛，积极向上",
        "profile": "热爱运动，注重健康，帮助他人塑形",
        "daily_events": [
            "今天去健身房上班，带了5节私教课",
            "帮学员制定了新的训练计划",
            "中午自己训练了一小时，练习了深蹲",
            "和会员聊了营养搭配的话题",
            "提醒自己明天早起跑步",
        ],
    },

    "driver": {
        "name": "老王",
        "profession": "网约车司机",
        "personality": "踏实肯干，服务周到",
        "profile": "全职司机，熟悉城市道路，善于聊天",
        "daily_events": [
            "今天早上6点出车，接了20多单",
            "送一位乘客去机场，聊了一路",
            "中午在路边简单吃了盒饭",
            "发现一条新路线，避开了晚高峰拥堵",
            "提醒自己明天要去做车辆保养",
        ],
    },
}


def generate_user_memory(user_id: str, template: dict, workspace_dir: str) -> dict:
    """
    生成用户记忆文件（CowAgent 格式）

    目录结构：
    workspace/memory/users/{user_id}/
    ├── MEMORY.md      # 长期记忆（画像）
    └── {date}.md      # 每日记忆（重要事件总结）
    """
    memory_dir = Path(workspace_dir) / "memory" / "users" / user_id
    memory_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")

    # 1. 生成 MEMORY.md（长期记忆/画像）
    # 格式对标 CowAgent：简洁的条目列表
    memory_content = f"""# {template['name']} 的长期记忆

## 基本信息

- {template['name']} 是一名{template['profession']}
- 性格：{template['personality']}
- 简介：{template['profile']}

## 偏好

"""
    memory_content += f"- 热爱{template['profile'].split('，')[0] if '，' in template['profile'] else '自己的工作'}\n"

    memory_file = memory_dir / "MEMORY.md"
    memory_file.write_text(memory_content, encoding='utf-8')

    # 2. 生成每日记忆（重要事件总结，不是对话记录）
    # 格式对标 CowAgent 的 LLM 总结输出
    daily_content = f"# Daily Memory: {today}\n\n"
    for event in template['daily_events']:
        daily_content += f"- {event}\n"

    daily_file = memory_dir / f"{today}.md"
    daily_file.write_text(daily_content, encoding='utf-8')

    return {
        "user_id": user_id,
        "name": template['name'],
        "files": {
            "memory": str(memory_file),
            "daily": str(daily_file)
        }
    }


def generate_custom_user(
    user_id: str,
    name: str,
    profession: str,
    profile: str,
    personality: str = None,
    daily_events: list = None,
    workspace_dir: str = "./workspace"
) -> dict:
    """生成自定义用户"""

    if not personality:
        personality = _infer_personality(profession, profile)

    if not daily_events:
        daily_events = _generate_daily_events(profession, profile)

    template = {
        "name": name,
        "profession": profession,
        "profile": profile,
        "personality": personality,
        "daily_events": daily_events,
    }

    return generate_user_memory(user_id, template, workspace_dir)


def _infer_personality(profession: str, profile: str) -> str:
    """推断性格"""
    keywords = {
        "严谨": ["医生", "教授", "架构师", "会计", "律师"],
        "外向": ["销售", "主播", "DJ", "教练", "艺人"],
        "稳重": ["司机", "老板", "经理", "工程师"],
        "创意": ["设计师", "艺人", "音乐人", "作家"],
        "耐心": ["老师", "医生", "教练", "客服"],
    }
    for personality, jobs in keywords.items():
        for job in jobs:
            if job in profession or job in profile:
                return personality
    return "随和友善"


def _generate_daily_events(profession: str, profile: str) -> list:
    """生成每日事件（重要事件总结格式）"""
    events_map = {
        "老师": [
            "今天去学校上课，讲了新课内容",
            "课后辅导了几位学生",
            "在办公室备课，准备明天的课程",
        ],
        "程序员": [
            "今天去公司上班，完成了代码开发",
            "参加了技术评审会议",
            "修复了几个线上bug",
        ],
        "医生": [
            "今天去医院上班，做了几台手术",
            "参加了科室会诊",
            "查看了住院病人的情况",
        ],
        "老板": [
            "今天在公司处理重要事务",
            "召开了管理层会议",
            "接待了重要客户",
        ],
    }

    for key, events in events_map.items():
        if key in profession:
            return events

    return [
        "今天正常上班",
        "完成了一些日常工作",
        "为明天做了计划",
    ]


def generate_all_users(workspace_dir: str = "./workspace"):
    """生成所有预设用户"""
    print("\n" + "=" * 60)
    print("🎭 生成用户 Mock 数据")
    print("=" * 60)

    print(f"\n工作空间: {workspace_dir}\n")

    for user_id, template in USER_TEMPLATES.items():
        result = generate_user_memory(user_id, template, workspace_dir)
        print(f"✅ {template['name']} ({template['profession']})")
        print(f"   长期记忆: {result['files']['memory']}")
        print(f"   每日记忆: {result['files']['daily']}")

    print(f"\n✨ 已生成 {len(USER_TEMPLATES)} 个用户")
    print("\n💡 启动 Agent 后会自动同步到数据库")


def interactive_create():
    """交互式创建用户"""
    print("\n" + "=" * 60)
    print("✨ 创建自定义用户")
    print("=" * 60)

    user_id = input("\n用户ID (如: lawyer_zhang): ").strip()
    if not user_id:
        print("❌ 用户ID不能为空")
        return

    name = input("姓名: ").strip()
    profession = input("职业: ").strip()
    profile = input("简介: ").strip()

    if not all([name, profession, profile]):
        print("❌ 请填写完整信息")
        return

    workspace_dir = input("工作空间目录 (默认 ./workspace): ").strip() or "./workspace"

    result = generate_custom_user(user_id, name, profession, profile, workspace_dir=workspace_dir)

    print(f"\n✅ 已创建用户: {name}")
    print(f"   长期记忆: {result['files']['memory']}")
    print(f"   每日记忆: {result['files']['daily']}")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="用户 Mock 数据生成器")
    parser.add_argument("--workspace", "-w", default="./workspace", help="工作空间目录")
    parser.add_argument("--all", "-a", action="store_true", help="生成所有预设用户")
    parser.add_argument("--create", "-c", action="store_true", help="交互式创建用户")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有预设用户")

    args = parser.parse_args()

    if args.list:
        print("\n预设用户列表:")
        for user_id, t in USER_TEMPLATES.items():
            print(f"  {user_id:12} - {t['name']:6} ({t['profession']})")
        return

    if args.create:
        interactive_create()
        return

    if args.all:
        generate_all_users(args.workspace)
        return

    # 默认：生成所有
    generate_all_users(args.workspace)


if __name__ == "__main__":
    main()
