# Minimal Agent

一个最小化的 AI Agent 实现，核心功能对标 CowAgent：

- ✅ 记忆系统（文件 + 向量数据库混合存储）
- ✅ 记忆隔离（用户级隔离）
- ✅ 记忆更新（相似度检测，最小化更新）
- ✅ 自动记忆（LLM 自动保存重要信息）
- ✅ Session 历史持久化（SQLite 存储）
- ✅ 每日记忆 Flush（LLM 总结写入）
- ✅ 文件操作（仅限工作空间目录）
- ✅ Prompt 模块化构建

---

## 📁 运行时文件结构

```
workspace/
├── AGENT.md                    # Agent 人格设定
├── MEMORY.md                   # 共享长期记忆索引
└── memory/
    ├── shared/                 # 共享记忆目录
    │   ├── 2026-04-20.md       # 共享每日记忆
    │   └── 2026-04-21.md
    └── users/
        ├── teacher/            # 用户隔离目录
        │   ├── MEMORY.md       # 用户长期记忆
        │   ├── 2026-04-20.md   # 用户每日记忆
        │   └── 2026-04-21.md
        └── developer/
            ├── MEMORY.md
            └── 2026-04-21.md

# SQLite 数据库（在 workspace 目录下）
./workspace/memory.db              # 记忆向量数据库
./workspace/context.db             # Session 历史数据库
```

---

## 📄 文件生成方式 & 时机

### 1. 文件类型

| 文件 | 生成方式 | 生成时机 | 内容格式 |
|------|----------|----------|----------|
| `AGENT.md` | 手动/初始化 | Agent 启动时检测不存在则创建 | Agent 人格设定 |
| `MEMORY.md` | 手动/LLM保存 | 用户调用 `save` 或 LLM 自动保存 | 长期记忆索引 |
| `YYYY-MM-DD.md` | Flush | 用户调用 `flush` 命令 | LLM 总结的每日事件 |
| `memory.db` | 自动 | 添加/更新记忆时 | 向量 + 文本块 |
| `context.db` | 自动 | 每次对话后 | Session 历史 |

### 2. 详细说明

#### AGENT.md（人格设定）
```markdown
# AGENT.md

我是 AI 助手。
```
- **生成时机**：Agent 启动时，文件不存在则创建默认内容
- **更新方式**：手动编辑
- **用途**：注入到系统提示词，定义 Agent 人格

#### MEMORY.md（长期记忆）
```markdown
# MEMORY.md

## 用户信息
- 王老师是一名高中语文老师，热爱教育
- 用户喜欢听有声书，最近在听《红楼梦》

## 偏好设置
- 用户偏好简洁的回复风格
```
- **生成时机**：
  - Agent 启动时检测不存在则创建
  - 用户调用 `save` 命令
  - LLM 自动调用 `memory_save` 工具
- **更新机制**：
  - 相似度 > 0.85：编辑对应行（最小化更新）
  - 相似度 ≤ 0.85：追加到文件末尾

#### YYYY-MM-DD.md（每日记忆）
```markdown
# Daily Memory: 2026-04-21

## Session 14:30

- 用户询问了关于课程设计的问题
- 讨论了《红楼梦》教学方案
- 用户决定下周开始实施新教案

## Session 16:45

- 用户分享了学生反馈，整体效果良好
```
- **生成时机**：用户调用 `flush` 命令
- **内容来源**：LLM 总结当前对话历史
- **格式要求**：按事件维度归纳，合并同一件事的多轮对话

---

## 🗄️ SQLite 存储结构

### 1. memory.db（记忆数据库）

```sql
-- 文本块表
CREATE TABLE chunks (
    id TEXT PRIMARY KEY,           -- hash(path:start:end)
    path TEXT NOT NULL,            -- 文件路径
    start_line INTEGER NOT NULL,   -- 起始行
    end_line INTEGER NOT NULL,     -- 结束行
    text TEXT NOT NULL,            -- 文本内容
    embedding TEXT,                -- 向量 (JSON)
    scope TEXT NOT NULL DEFAULT 'shared',  -- shared | user
    user_id TEXT,                  -- 用户 ID
    hash TEXT NOT NULL,            -- 内容 hash
    created_at INTEGER             -- 创建时间戳
);

-- 文件元数据表（增量同步）
CREATE TABLE files (
    path TEXT PRIMARY KEY,
    hash TEXT NOT NULL,            -- 文件内容 hash
    mtime INTEGER NOT NULL,        -- 修改时间
    size INTEGER NOT NULL,         -- 文件大小
    updated_at INTEGER
);

-- 索引
CREATE INDEX idx_chunks_path ON chunks(path);
CREATE INDEX idx_chunks_scope ON chunks(scope, user_id);
```

**数据流**：
```
文件内容 → TextChunker 分块 → EmbeddingProvider 向量化 → 存入 chunks 表
```

**查询方式**：
- 向量检索：余弦相似度
- 关键词检索：LIKE 模糊匹配
- 混合检索：加权融合 + 时间衰减

### 2. context.db（Session 历史数据库）

```sql
-- 会话表
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,   -- "{user_id}_session"
    user_id TEXT,                  -- 用户 ID
    messages TEXT,                 -- JSON 格式消息列表
    created_at INTEGER,
    updated_at INTEGER
);

-- 索引
CREATE INDEX idx_sessions_user ON sessions(user_id);
```

**消息格式**（JSON）：
```json
[
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！有什么可以帮你的？"},
    {"role": "user", "content": "我叫王老师"},
    {"role": "assistant", "content": "好的，王老师，我记住了。"}
]
```

**过滤规则**：
- 只保留 `user` 和 `assistant` 消息
- 过滤 `tool_use`、`tool_result` 等中间消息
- 最多保留 20 轮对话（40 条消息）

---

## 🔄 数据流图

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户交互                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     SimpleAgent.chat()                          │
│                                                                 │
│  1. PromptBuilder.load_context_files()                          │
│     └─ 读取 AGENT.md, MEMORY.md                                 │
│                                                                 │
│  2. MemoryManager.search(query)                                 │
│     └─ 向量检索 + 关键词检索 + 混合检索                          │
│     └─ 从 memory.db 查询                                        │
│                                                                 │
│  3. 构建消息列表                                                │
│     └─ system prompt + 记忆上下文 + 历史消息 + 用户输入          │
│                                                                 │
│  4. _call_llm_with_tools()                                      │
│     └─ 调用 LLM API                                             │
│     └─ 处理 tool_calls (memory_save/memory_search)              │
│                                                                 │
│  5. Context.add_message()                                       │
│     └─ 保存到 context.db                                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     flush 命令触发                               │
│                                                                 │
│  1. 获取 Context 历史消息                                       │
│  2. MemoryFlusher.flush_messages()                              │
│     └─ LLM 总结对话                                             │
│     └─ 写入 YYYY-MM-DD.md                                       │
│  3. MemoryManager.sync_from_files()                             │
│     └─ 增量同步到 memory.db                                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📋 实践步骤

### Step 1: 环境准备

```bash
cd /Users/lbc/minimal_agent

# 安装依赖
pip install requests python-dotenv prompt_toolkit

# 创建 .env 文件
cat > .env << 'EOF'
# 对话模型 (京东云 GLM-5)
OPENAI_API_KEY=your-api-key
OPENAI_API_BASE=https://modelservice.jdcloud.com/coding/openai/v1
OPENAI_MODEL=GLM-5

# 嵌入模型 (MoArk bge-m3)
EMBEDDING_API_KEY=your-embedding-key
EMBEDDING_API_BASE=https://api.moark.com/v1
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIMENSIONS=1024
EOF
```

### Step 2: 生成 Mock 数据（可选）

```bash
# 生成职业人设文件
python demo/profession_generator.py --all

# 查看生成的文件
ls -la workspace/
ls -la workspace/memory/users/
```

### Step 3: 启动 Agent

```bash
python demo/realtime_demo.py
```

### Step 4: 交互测试

```
🚗 汽车语音助手 - 真实场景交互 Demo
======================================================================

请选择用户身份:
  1. 王老师 (高中语文老师)
  ...

请输入选项 (1-9): 1

✅ 已选择用户: 王老师 (高中语文老师)

💬 开始对话
======================================================================

[teacher] 👤 你好
🤖 助手: 你好！王老师，今天有什么可以帮您的？

[teacher] 👤 我最近在准备《红楼梦》的教学
🤖 助手: 好的，我记住了。您正在准备《红楼梦》的教学...

[teacher] 👤 save 我下周三有公开课，讲《红楼梦》第一回
✅ 记忆已保存

[teacher] 👤 messages
📨 完整消息列表...
[2] 🧠 记忆上下文 ⭐ 记忆注入位置
   - [私有] 王老师是一名高中语文老师...

[teacher] 👤 flush
[INFO] 正在总结 4 条对话...
✅ 对话已总结并写入每日记忆
   文件: memory/teacher/2026-04-21.md

[teacher] 👤 q
👋 再见！
```

### Step 5: 验证数据

```bash
# 查看生成的记忆文件
cat workspace/memory/users/teacher/2026-04-21.md

# 查看 SQLite 数据
sqlite3 workspace/memory.db "SELECT path, start_line, text FROM chunks LIMIT 5;"
sqlite3 workspace/context.db "SELECT session_id, json_array_length(messages) FROM sessions;"
```

### Step 6: 重启验证持久化

```bash
# 退出后重新启动
python demo/realtime_demo.py

# 选择同一用户，历史对话会自动恢复
[teacher] 👤 history
📜 历史对话
======================================================================

共 4 条消息:

1. 👤 用户:
   你好
2. 🤖 助手:
   你好！王老师...
```

---

## 📊 命令速查表

| 命令 | 功能 | 数据存储 |
|------|------|----------|
| `<对话>` | 与 Agent 对话 | context.db |
| `history` | 查看对话历史 | 从 context.db 读取 |
| `memory <关键词>` | 搜索记忆 | 从 memory.db 检索 |
| `save <内容>` | 保存长期记忆 | MEMORY.md + memory.db |
| `flush` | 总结写入每日记忆 | YYYY-MM-DD.md + memory.db |
| `messages` | 查看记忆注入位置 | - |
| `prompt` | 查看系统提示词 | - |
| `clear` | 清空对话历史 | 删除 context.db 记录 |
| `q` | 退出 | - |

---

## 📂 项目结构

```
minimal_agent/
├── config.py              # 配置管理
├── context.py             # 上下文管理（内存）
├── context_store.py       # Session 历史持久化（SQLite）
├── agent.py               # Agent 主类
├── memory/
│   ├── storage.py         # 存储层（SQLite + 向量）
│   ├── embedding.py       # 向量嵌入
│   ├── chunker.py         # 文本分块
│   ├── manager.py         # 记忆管理器
│   └── flusher.py         # 每日记忆 Flush
├── prompt/
│   └── builder.py         # Prompt 构建
├── tools/
│   ├── memory_tools.py    # 记忆工具
│   └── file_tools.py      # 文件操作工具
├── demo/
│   ├── realtime_demo.py   # 交互 Demo
│   ├── profession_generator.py  # 职业人设生成
│   ├── clean.py           # 重置脚本
│   └── README.md          # Demo 说明
├── .env                   # 环境变量
├── requirements.txt       # 依赖列表
└── README.md              # 项目说明
```

---

## 许可证

MIT License
