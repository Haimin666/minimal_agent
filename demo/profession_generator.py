#!/usr/bin/env python3
"""
职业人设生成器

生成职业人设文件到 workspace 目录：
- workspace/profiles/{user_id}.md  - 用户画像文件
- workspace/voice/{user_id}/{date}.md - 语音记录文件

这些文件会被 Agent 的记忆系统自动同步到数据库。
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from pathlib import Path


# ==================== 职业模板 ====================

PROFESSION_TEMPLATES = {
    "teacher": {
        "name": "王老师",
        "profession": "高中语文老师",
        "profile": "热爱教育，喜欢听有声书，关心学生成长",
        "personality": "温和耐心，注重细节",
        "preferences": [
            "常去地点：学校、图书馆、书店",
            "音乐偏好：有声书、古典音乐、教育播客",
            "车辆习惯：安静模式、温度适中",
            "作息时间：早6:30出发，晚6点回家",
        ],
        "voice_samples": [
            ("06:30", "导航", "导航去第一中学"),
            ("06:45", "音乐", "播放《红楼梦》有声书"),
            ("07:10", "车辆控制", "关闭音响，我要备课"),
            ("17:30", "提醒", "提醒我明天带教案"),
            ("18:00", "导航", "导航去新华书店"),
        ],
    },

    "professor": {
        "name": "李教授",
        "profession": "大学教授",
        "profile": "学术研究，经常参加学术会议，关注科研动态",
        "personality": "严谨专业，思路开阔",
        "preferences": [
            "常去地点：大学、机场、会议中心",
            "音乐偏好：古典交响乐、学术播客",
            "车辆习惯：后排办公模式、降噪开启",
            "作息时间：不规律，经常出差",
        ],
        "voice_samples": [
            ("08:00", "导航", "导航去清华大学"),
            ("08:30", "音乐", "播放贝多芬交响曲"),
            ("10:00", "新闻", "搜索最新的AI研究论文"),
            ("14:00", "导航", "导航去首都机场T3"),
            ("20:00", "提醒", "提醒我明天9点学术会议"),
        ],
    },

    "developer": {
        "name": "张码农",
        "profession": "全栈开发工程师",
        "profile": "互联网大厂程序员，加班多，热爱技术",
        "personality": "逻辑清晰，追求效率",
        "preferences": [
            "常去地点：公司、科技园、网吧",
            "音乐偏好：电子音乐、编程歌单、播客",
            "车辆习惯：运动模式、氛围灯蓝色",
            "作息时间：早10晚10，周末加班",
        ],
        "voice_samples": [
            ("09:30", "导航", "导航去中关村软件园"),
            ("09:50", "音乐", "播放编程专用歌单"),
            ("10:00", "车辆控制", "打开氛围灯蓝色"),
            ("12:00", "闲聊", "今天GitHub有什么热门项目"),
            ("22:00", "导航", "回家"),
        ],
    },

    "boss": {
        "name": "刘总",
        "profession": "公司CEO",
        "profile": "企业老板，商务应酬多，时间宝贵",
        "personality": "决策果断，注重效率",
        "preferences": [
            "常去地点：公司、高尔夫球场、高端餐厅、机场",
            "音乐偏好：轻音乐、商业有声书",
            "车辆习惯：后排办公模式、温度22度、香氛开启",
            "作息时间：早7晚10，经常出差",
        ],
        "voice_samples": [
            ("07:00", "导航", "导航去公司"),
            ("07:30", "新闻", "今天有什么重要财经新闻"),
            ("08:00", "提醒", "提醒我9点董事会议，10点见投资人"),
            ("12:00", "导航", "导航去国贸三期"),
            ("18:00", "导航", "导航去高尔夫球场"),
        ],
    },

    "doctor": {
        "name": "周医生",
        "profession": "三甲医院主任医师",
        "profile": "救死扶伤，工作繁忙，责任心强",
        "personality": "认真负责，沉着冷静",
        "preferences": [
            "常去地点：医院、医学院、学术会议",
            "音乐偏好：古典音乐、冥想音乐",
            "车辆习惯：安静模式、温度舒适",
            "作息时间：早7晚不定，经常值班",
        ],
        "voice_samples": [
            ("07:00", "导航", "导航去协和医院"),
            ("07:30", "新闻", "搜索最新医学研究"),
            ("08:00", "提醒", "提醒我今天有3台手术"),
            ("18:00", "音乐", "播放舒缓音乐"),
            ("22:00", "导航", "回医院值班"),
        ],
    },

    "dj": {
        "name": "DJ阿杰",
        "profession": "酒吧DJ",
        "profile": "夜生活工作者，音乐狂热，个性张扬",
        "personality": "外向张扬，追求个性",
        "preferences": [
            "常去地点：酒吧街、音乐节现场、录音棚",
            "音乐偏好：电子舞曲、Hip-Hop、Remix",
            "车辆习惯：氛围灯炫彩模式、音响低音增强",
            "作息时间：下午起床，凌晨下班",
        ],
        "voice_samples": [
            ("18:00", "音乐", "播放最新电音"),
            ("18:30", "车辆控制", "氛围灯调成炫彩模式"),
            ("19:00", "导航", "导航去三里屯酒吧街"),
            ("20:00", "新闻", "最近有什么音乐节"),
            ("02:00", "导航", "回家"),
        ],
    },

    "coach": {
        "name": "孙教练",
        "profession": "健身教练",
        "profile": "热爱运动，注重健康，精力充沛",
        "personality": "阳光积极，充满活力",
        "preferences": [
            "常去地点：健身房、体育馆、健康餐厅",
            "音乐偏好：动感音乐、健身歌单",
            "车辆习惯：运动模式、温度凉爽",
            "作息时间：早6晚9，规律作息",
        ],
        "voice_samples": [
            ("06:00", "音乐", "播放动感健身歌单"),
            ("06:30", "导航", "导航去金域健身房"),
            ("07:00", "闲聊", "今天适合做什么运动"),
            ("12:00", "导航", "找附近的健康餐厅"),
            ("18:00", "车辆控制", "空调调到18度"),
        ],
    },

    "driver": {
        "name": "老王",
        "profession": "网约车司机",
        "profile": "全职司机，熟悉城市道路，服务态度好",
        "personality": "稳重踏实，善于聊天",
        "preferences": [
            "常去地点：机场、火车站、商圈、小区",
            "音乐偏好：交通广播、老歌",
            "车辆习惯：节能模式、清洁常备",
            "作息时间：早6晚10，时间灵活",
        ],
        "voice_samples": [
            ("06:00", "闲聊", "今天限行吗"),
            ("06:30", "音乐", "播放交通广播"),
            ("08:00", "导航", "导航去首都机场T2"),
            ("12:00", "导航", "找附近的充电站"),
            ("18:00", "闲聊", "今天跑了多少单"),
        ],
    },
}


def generate_user_profile(user_id: str, template: dict, workspace_dir: str) -> str:
    """生成用户画像文件"""
    profile_dir = Path(workspace_dir) / "profiles"
    profile_dir.mkdir(parents=True, exist_ok=True)

    content = f"""# {template['name']} 的用户画像

## 基本信息
- 用户ID: {user_id}
- 姓名: {template['name']}
- 职业: {template['profession']}
- 性格: {template['personality']}
- 简介: {template['profile']}

## 偏好设置
"""
    for pref in template['preferences']:
        content += f"- {pref}\n"

    content += f"""
## 生成时间
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

    file_path = profile_dir / f"{user_id}.md"
    file_path.write_text(content, encoding='utf-8')
    return str(file_path)


def generate_voice_records(user_id: str, template: dict, workspace_dir: str) -> str:
    """生成语音记录文件"""
    today = datetime.now().strftime("%Y-%m-%d")
    voice_dir = Path(workspace_dir) / "voice" / user_id
    voice_dir.mkdir(parents=True, exist_ok=True)

    content = f"# {template['name']} 的语音记录 ({today})\n\n"

    for time, intent, text in template['voice_samples']:
        content += f"- [{time}] {intent}: {text}\n"

    content += f"\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"

    file_path = voice_dir / f"{today}.md"
    file_path.write_text(content, encoding='utf-8')
    return str(file_path)


def generate_custom_user(user_id: str, name: str, profession: str, profile: str,
                         personality: str = None, preferences: list = None,
                         voice_samples: list = None, workspace_dir: str = "./workspace") -> dict:
    """生成自定义用户"""

    # 推断性格
    if not personality:
        personality = _infer_personality(profession, profile)

    # 生成偏好
    if not preferences:
        preferences = _generate_preferences(profession, profile)

    # 生成语音样本
    if not voice_samples:
        voice_samples = _generate_voice_samples(profession)

    template = {
        "name": name,
        "profession": profession,
        "profile": profile,
        "personality": personality,
        "preferences": preferences,
        "voice_samples": voice_samples,
    }

    # 生成文件
    profile_file = generate_user_profile(user_id, template, workspace_dir)
    voice_file = generate_voice_records(user_id, template, workspace_dir)

    return {
        "user_id": user_id,
        "template": template,
        "files": {
            "profile": profile_file,
            "voice": voice_file
        }
    }


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


def _generate_preferences(profession: str, profile: str) -> list:
    """生成偏好"""
    if "老师" in profession or "教育" in profile:
        return ["常去地点：学校、图书馆", "音乐偏好：有声书、古典音乐", "作息：早6晚6"]
    elif "程序员" in profession or "开发" in profession:
        return ["常去地点：公司、科技园", "音乐偏好：电子音乐、编程歌单", "作息：早10晚10"]
    elif "医生" in profession:
        return ["常去地点：医院、医学院", "音乐偏好：古典音乐、冥想音乐", "作息：不规律，经常值班"]
    elif "老板" in profession or "CEO" in profession:
        return ["常去地点：公司、机场、高端餐厅", "音乐偏好：轻音乐、商业有声书", "作息：早7晚10"]
    else:
        return ["常去地点：公司、家", "音乐偏好：流行音乐", "作息：正常作息"]


def _generate_voice_samples(profession: str) -> list:
    """生成语音样本"""
    base = [
        ("08:00", "导航", "导航去公司"),
        ("08:15", "音乐", "播放音乐"),
        ("18:00", "导航", "回家"),
    ]
    return base


def generate_all_professions(workspace_dir: str = "./workspace"):
    """生成所有预设职业"""
    print("\n" + "=" * 60)
    print("🎭 生成职业人设文件")
    print("=" * 60)

    print(f"\n工作空间: {workspace_dir}\n")

    for user_id, template in PROFESSION_TEMPLATES.items():
        profile_file = generate_user_profile(user_id, template, workspace_dir)
        voice_file = generate_voice_records(user_id, template, workspace_dir)

        print(f"✅ {template['name']} ({template['profession']})")
        print(f"   画像: {profile_file}")
        print(f"   语音: {voice_file}")

    print(f"\n✨ 已生成 {len(PROFESSION_TEMPLATES)} 个职业人设")


def interactive_create():
    """交互式创建人设"""
    print("\n" + "=" * 60)
    print("✨ 创建自定义职业人设")
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
    print(f"   画像: {result['files']['profile']}")
    print(f"   语音: {result['files']['voice']}")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="职业人设生成器")
    parser.add_argument("--workspace", "-w", default="./workspace", help="工作空间目录")
    parser.add_argument("--all", "-a", action="store_true", help="生成所有预设职业")
    parser.add_argument("--create", "-c", action="store_true", help="交互式创建人设")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有预设职业")

    args = parser.parse_args()

    if args.list:
        print("\n预设职业列表:")
        for user_id, t in PROFESSION_TEMPLATES.items():
            print(f"  {user_id:12} - {t['name']:6} ({t['profession']})")
        return

    if args.create:
        interactive_create()
        return

    if args.all:
        generate_all_professions(args.workspace)
        return

    # 默认：生成所有 + 进入交互
    generate_all_professions(args.workspace)

    print("\n" + "-" * 60)
    create_more = input("是否创建自定义人设? (y/n): ").strip().lower()
    if create_more == 'y':
        interactive_create()


if __name__ == "__main__":
    main()
