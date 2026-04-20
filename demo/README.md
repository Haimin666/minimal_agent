# Demo 演示目录

## 快速开始

```bash
cd /Users/lbc/minimal_agent

# 1. 生成职业人设文件（可选，首次运行）
python demo/profession_generator.py

# 2. 启动 Agent 对话
python demo/realtime_demo.py

# 3. 清理所有数据（重新开始）
python demo/clean.py
```

---

## 文件说明

| 文件 | 功能 | 命令 |
|------|------|------|
| `realtime_demo.py` | **Agent 对话入口** ⭐ | `python demo/realtime_demo.py` |
| `profession_generator.py` | 生成职业人设文件 | `python demo/profession_generator.py` |
| `clean.py` | 一键清理所有数据 | `python demo/clean.py` |
| `test_agent.py` | 自动化测试脚本 | `python demo/test_agent.py` |

---

## realtime_demo.py - Agent 对话入口

```
$ python demo/realtime_demo.py

🚗 汽车语音助手 - 真实场景交互 Demo
======================================================================

📡 模型配置:
   对话: GLM-5 @ https://modelservice.jdcloud.com/coding/openai/v1
   嵌入: bge-m3 @ https://api.moark.com/v1

----------------------------------------
请选择用户身份:
  1. 张三 (律师)
  2. 李四 (医生)
  3. 王五 (程序员)
  4. 新用户
----------------------------------------

请输入选项 (1-4): 1

✅ 已选择用户: 张三 (律师)

💬 开始对话
======================================================================

[zhang_san] 👤 你: 我最近在忙什么工作？
🤖 助手: 根据我的记忆，您是一名律师，最近在处理并购案...

命令:
  <直接输入>      - 对话
  history        - 查看历史
  prompt         - 查看系统提示词
  messages       - 查看记忆注入位置 ⭐
  memory         - 搜索记忆
  save <内容>    - 保存记忆
  clear          - 清空历史
  q              - 退出
```

### 命令详解

| 命令 | 功能 |
|------|------|
| `<直接输入>` | 与助手对话 |
| `history` | 查看历史对话 |
| `prompt` | 查看系统提示词 |
| `messages` | **查看完整消息列表，标注记忆注入位置** ⭐ |
| `memory` | 搜索记忆 |
| `save <内容>` | 主动保存记忆 |
| `clear` | 清空对话历史 |
| `q` | 退出 |

---

## profession_generator.py - 职业人设生成器

生成职业人设文件，Agent 会自动同步到记忆数据库。

```bash
# 生成所有预设职业
python demo/profession_generator.py --all

# 列出预设职业
python demo/profession_generator.py --list

# 交互式创建人设
python demo/profession_generator.py --create
```

### 预设职业

| ID | 姓名 | 职业 |
|----|------|------|
| teacher | 王老师 | 高中语文老师 |
| professor | 李教授 | 大学教授 |
| developer | 张码农 | 全栈开发工程师 |
| boss | 刘总 | 公司CEO |
| doctor | 周医生 | 三甲医院主任医师 |
| dj | DJ阿杰 | 酒吧DJ |
| coach | 孙教练 | 健身教练 |
| driver | 老王 | 网约车司机 |

### 生成的文件

```
workspace/
├── profiles/
│   ├── teacher.md      # 王老师的画像
│   ├── developer.md    # 张码农的画像
│   └── ...
└── voice/
    ├── teacher/
    │   └── 2026-04-20.md  # 语音记录
    └── ...
```

---

## clean.py - 一键清理

```bash
$ python demo/clean.py

🧹 一键清理 - 清除所有历史对话和记忆
============================================================

   已清理:
      ✅ 📁 目录: demo/workspace
      ✅ 📁 目录: demo/realtime_workspace
      ✅ 📄 文件: demo/demo.db

✨ 清理完成！可以重新开始
============================================================
```

---

## 记忆注入机制

### 使用 `messages` 命令查看

```
[zhang_san] 👤 你: messages

📨 完整消息列表 (发送给 LLM 的内容)
======================================================================

消息总数: 4

[1] 📝 系统提示词 (665 字符)
   └─ 包含: Agent设定 + 工具说明 + 记忆系统说明

[2] 🧠 记忆上下文 (156 字符) ⭐ 记忆注入位置
   └─ 从数据库检索到的相关记忆
   内容预览:
      ## 相关记忆
      - [👤私有] 张三 是一名律师，擅长公司法...

[3] 👤 用户消息
[4] 🤖 助手消息
```

### 消息注入顺序

```
1. [系统提示词] - 基础设定
2. [记忆上下文] ⭐ - 检索到的记忆（动态注入）
3. [历史消息] - 对话历史
4. [当前输入] - 用户刚才说的话
```

---

## 模型配置

配置文件: `config.py`

```python
# 对话模型 (京东云 GLM-5)
api_key: str = "pk-e5d95df8-19c5-4003-8fa4-173c84eb24df"
api_base: str = "https://modelservice.jdcloud.com/coding/openai/v1"
model: str = "GLM-5"

# 嵌入模型 (MoArk bge-m3)
embedding_api_key: str = "6CHJ03YARBNNHTXDSJHU53JF9ZEMT6JDRA8KVL1H"
embedding_api_base: str = "https://api.moark.com/v1"
embedding_model: str = "bge-m3"
embedding_dimensions: int = 1024
```
