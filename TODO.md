# Minimal Agent 使用指南

## 快速开始

```bash
cd /Users/lbc/minimal_agent
python demo/realtime_demo.py
```

---

## 完整演示步骤

### 第一步：启动 Agent

```bash
cd /Users/lbc/minimal_agent
python demo/realtime_demo.py
```

### 第二步：选择用户身份

```
请选择用户身份:
  1. 王老师 (高中语文老师)
  2. 李教授 (大学教授)
  3. 张码农 (全栈开发工程师)
  4. 刘总   (公司CEO)
  5. 周医生 (三甲医院主任医师)
  6. DJ阿杰 (酒吧DJ)
  7. 孙教练 (健身教练)
  8. 老王   (网约车司机)
  9. 新用户 (自定义)

请输入选项 (1-9): 1
```

### 第三步：对话

```
[teacher] 👤 你: 我今天要做什么？

──────────────────────────────────────────────────────────────────────
📝 第 1 轮对话
──────────────────────────────────────────────────────────────────────

[INFO] 记忆检索
  查询: "我今天要做什么"
  向量化: bge-m3, 维度=1024
  结果: 1 条
    [1] [私有] memory/users/teacher/memory_xxx.md#L1-L1
        内容: 王老师 是一名高中语文老师，热爱教育...
        分数: 0.35

[INFO] Prompt 构建
  系统提示词: 543 字符
  记忆上下文: 49 字符 ⭐ 注入位置
  历史消息: 0 条
  当前输入: 8 字符
  总消息数: 3 条

[INFO] LLM 调用
  模型: GLM-5
  API: https://modelservice.jdcloud.com/coding/openai/v1

🤖 助手:
  根据您的背景，您是一位高中语文老师...
```

### 第四步：查看完整消息列表

```
[teacher] 👤 你: messages

📨 完整消息列表 (发送给 LLM 的内容)
======================================================================

消息总数: 5
======================================================================

[1] 📝 系统提示词 (543 字符)
   └─ 包含: Agent设定 + 工具说明 + 记忆系统说明 + 工作空间

[2] 🧠 记忆上下文 (49 字符) ⭐ 记忆注入位置
   └─ 从数据库检索到的相关记忆，作为系统消息注入
   内容预览:
      ## 相关记忆
      - [私有] 王老师 是一名高中语文老师...

[3] 👤 用户消息 (8 字符)
   └─ 我今天要做什么？

[4] 🤖 助手消息 (120 字符)
   └─ 根据您的背景，您是一位高中语文老师...
```

### 第五步：保存新记忆

```
[teacher] 👤 你: save 我明天要带学生去参观博物馆

[INFO] 记忆存入
  文件: memory/users/teacher/memory_xxx.md
  内容: 我明天要带学生去参观博物馆
  范围: 用户私有 (user_id=teacher)
```

### 第六步：继续对话（会检索到新记忆）

```
[teacher] 👤 你: 我明天有什么安排？

[INFO] 记忆检索
  结果: 2 条
    [1] [私有] memory/users/teacher/memory_xxx.md
        内容: 我明天要带学生去参观博物馆...
```

### 第七步：退出

```
[teacher] 👤 你: q
👋 再见！
```

### 第八步：清理数据（重新开始）

```bash
python demo/clean.py
```

---

## 命令说明

| 命令 | 功能 |
|------|------|
| `<直接输入>` | 与助手对话 |
| `history` | 查看历史对话 |
| `prompt` | 查看系统提示词 |
| `messages` | 查看完整消息列表（含记忆注入位置）⭐ |
| `memory` | 搜索记忆 |
| `save <内容>` | 主动保存记忆 |
| `clear` | 清空对话历史 |
| `q` | 退出 |

---

## 日志说明

### [INFO] 记忆检索

```
[INFO] 记忆检索
  查询: "你好"                    ← 用户输入
  向量化: bge-m3, 维度=1024       ← 嵌入模型
  结果: 1 条                      ← 检索结果数量
    [1] [私有] memory/users/teacher/memory_xxx.md#L1-L1  ← 文件路径和行号
        内容: 王老师 是一名...    ← 记忆内容
        分数: 0.373              ← 相关性分数
```

### [INFO] Prompt 构建

```
[INFO] Prompt 构建
  系统提示词: 545 字符           ← 基础设定
  记忆上下文: 40 字符 ⭐ 注入位置 ← 检索到的记忆
  历史消息: 0 条                 ← 之前的对话
  当前输入: 2 字符               ← 用户刚才说的
  总消息数: 3 条                 ← 发给 LLM 的消息总数
```

### [INFO] LLM 调用

```
[INFO] LLM 调用
  模型: GLM-5
  API: https://modelservice.jdcloud.com/coding/openai/v1
```

### [INFO] 记忆存入

```
[INFO] 记忆存入
  文件: memory/users/teacher/memory_xxx.md  ← 存储路径
  内容: 我明天要带学生去参观博物馆          ← 记忆内容
  范围: 用户私有 (user_id=teacher)         ← 隔离范围
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

---

## 记忆隔离机制

### 消息注入顺序

```
1. [系统提示词] - 基础设定、工具说明、记忆系统说明
2. [记忆上下文] ⭐ - 检索到的记忆（动态注入）
3. [历史消息] - 对话历史
4. [当前输入] - 用户刚才说的话
```

### 隔离原理

```
用户 A 对话时:
  搜索记忆 (user_id = "teacher")
    ↓
  SELECT * FROM chunks
  WHERE (scope = 'shared' OR (scope = 'user' AND user_id = 'teacher'))
    ↓
  返回: 共享记忆 + 用户A的私有记忆

用户 B 对话时:
  搜索记忆 (user_id = "doctor")
    ↓
  SELECT * FROM chunks
  WHERE (scope = 'shared' OR (scope = 'user' AND user_id = 'doctor'))
    ↓
  返回: 共享记忆 + 用户B的私有记忆
```

---

## 文件说明

| 文件 | 功能 |
|------|------|
| `demo/realtime_demo.py` | Agent 对话入口 ⭐ |
| `demo/profession_generator.py` | 职业人设生成器 |
| `demo/clean.py` | 一键清理 |
| `demo/test_agent.py` | 自动化测试 |
