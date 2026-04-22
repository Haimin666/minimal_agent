# Minimal Agent

一个最小化的 AI Agent 实现，采用三层记忆架构，与 CowAgent 设计一致。

## 核心特性

- ✅ **三层记忆架构** - 短期/中期/长期记忆分层管理
- ✅ **混合检索** - 向量检索 + 关键词检索（FTS5/LIKE）
- ✅ **记忆隔离** - 用户级隔离
- ✅ **上下文摘要注入** - 裁剪时自动注入摘要保持连续性
- ✅ **自动 Flush** - 上下文裁剪时自动总结写入每日记忆
- ✅ **Deep Dream** - 退出时自动蒸馏长期记忆
- ✅ **Session 持久化** - SQLite 存储对话历史

---

## 三层记忆架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    短期记忆（Context）                           │
│                                                                 │
│  存储：内存中，Context.messages + SQLite 持久化                  │
│  限制：max_context_turns (默认 20 轮)                            │
│  特点：快速访问，自动裁剪                                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                    超出限制时裁剪 + Flush
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              中期记忆（天级 YYYY-MM-DD.md）                       │
│                                                                 │
│  存储：workspace/memory/YYYY-MM-DD.md                            │
│  触发：上下文裁剪时 + 手动 flush                                   │
│  内容：LLM 总结的对话摘要                                         │
│  特点：追加写入，人类可读                                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                    退出时/手动触发蒸馏
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 长期记忆（MEMORY.md）                             │
│                                                                 │
│  存储：workspace/MEMORY.md                                       │
│  触发：退出时 + 手动命令                                          │
│  内容：LLM 蒸馏后的精炼记忆（~50 条）                              │
│  特点：覆写更新，去重合并                                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 记忆检索

采用与 CowAgent 一致的混合检索策略：

```
查询 → 向量检索 (Top 2N) → 关键词检索 (Top 2N) → 加权融合 → Top N 结果
```

### 检索策略

| 场景 | 方法 | 说明 |
|------|------|------|
| 语义相似 | 向量检索 | 余弦相似度，捕捉语义关联 |
| 精确匹配 | 关键词检索 | FTS5 全文索引 + BM25 排序 |
| 中文关键词 | LIKE 回退 | FTS5 对 CJK 支持有限 |
| 最终结果 | 加权融合 | vector_weight=0.7, keyword_weight=0.3 |

---

## 上下文摘要注入

当对话历史超出限制被裁剪时：

1. **LLM 总结** 被裁剪的对话内容
2. **写入** 每日记忆文件（持久化）
3. **注入摘要** 到当前对话（保持连续性）

```
原始对话 (30轮) → 裁剪前 15 轮 → LLM 总结 → 注入摘要
                    ↓
              [系统消息: 历史对话摘要...]
              [用户: ...]
              [助手: ...]
              (保留后 15 轮)
```

---

## 📁 运行时文件结构

```
workspace/
├── AGENT.md                    # Agent 人格设定
├── MEMORY.md                   # 长期记忆（蒸馏后）
├── context.db                  # Session 历史持久化
├── memory.db                   # 向量数据库 + FTS5 索引
└── memory/
    ├── shared/                 # 共享记忆
    │   └── 2026-04-22.md
    └── users/
        └── teacher/            # 用户隔离
            ├── MEMORY.md       # 用户长期记忆
            └── 2026-04-22.md   # 用户每日记忆
```

---

## 📄 文件生成方式 & 时机

| 文件 | 生成方式 | 生成时机 | 内容格式 |
|------|----------|----------|----------|
| `AGENT.md` | 手动/初始化 | Agent 启动时检测不存在则创建 | Agent 人格设定 |
| `MEMORY.md` | Deep Dream | 退出时 + 手动 `distill()` | 精炼的长期记忆（~50条） |
| `YYYY-MM-DD.md` | Flush | 上下文裁剪时 + 手动 `flush()` | LLM 总结的对话摘要 |
| `memory.db` | 自动 | 添加/更新记忆时 | 向量 + 文本块 + FTS5 |
| `context.db` | 自动 | 每次对话后 | Session 历史 |

---

## 🗄️ SQLite 存储结构

### memory.db（记忆数据库）

```sql
-- 文本块表
CREATE TABLE chunks (
    id TEXT PRIMARY KEY,           -- hash(path:start:end)
    path TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding TEXT,                -- 向量 (JSON)
    scope TEXT NOT NULL DEFAULT 'shared',
    user_id TEXT,
    hash TEXT NOT NULL,
    created_at INTEGER
);

-- FTS5 全文索引
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    text,
    path,
    content='chunks',
    tokenize='unicode61'
);

-- 文件元数据表（增量同步）
CREATE TABLE files (
    path TEXT PRIMARY KEY,
    hash TEXT NOT NULL,
    mtime INTEGER NOT NULL,
    size INTEGER NOT NULL
);
```

### context.db（Session 历史）

```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT,
    messages TEXT,                 -- JSON 格式消息列表
    created_at INTEGER,
    updated_at INTEGER
);
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
# 对话模型
OPENAI_API_KEY=your-api-key
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini

# 嵌入模型（用于向量检索）
EMBEDDING_API_KEY=your-embedding-key
EMBEDDING_API_BASE=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
EOF
```

### Step 2: 使用示例

```python
from config import Config
from agent import SimpleAgent

# 创建 Agent
config = Config()
agent = SimpleAgent(config, user_id="teacher")

# 对话
result = agent.chat("你好")
print(result["response"])

# 手动 Flush
agent.flush()

# 手动蒸馏
agent.distill(lookback_days=3)

# 退出时自动处理
agent.exit()  # 自动 flush + distill
```

---

## 📊 命令速查表

| 方法 | 功能 | 数据存储 |
|------|------|----------|
| `chat(input)` | 对话 | context.db |
| `flush()` | 总结写入每日记忆 | YYYY-MM-DD.md + memory.db |
| `distill(days)` | 蒸馏长期记忆 | MEMORY.md + memory.db |
| `exit()` | 退出处理（flush + distill） | - |
| `clear_history()` | 清空对话历史 | 删除 context.db 记录 |

---

## 📂 项目结构

```
minimal_agent/
├── config.py              # 配置管理
├── context.py             # 上下文管理（内存 + 裁剪 + 摘要注入）
├── context_store.py       # Session 历史持久化（SQLite）
├── agent.py               # Agent 主类
├── memory/
│   ├── storage.py         # 存储层（SQLite + 向量 + FTS5）
│   ├── embedding.py       # 向量嵌入
│   ├── chunker.py         # 文本分块
│   ├── manager.py         # 记忆管理器（混合检索）
│   ├── flusher.py         # 对话总结 + 写入天级
│   └── deep_dream.py      # 记忆蒸馏
├── prompt/
│   └── builder.py         # Prompt 构建
└── tools/
    ├── memory_tools.py    # 记忆工具
    └── file_tools.py      # 文件操作工具
```

---

## 与 CowAgent 对比

| 特性 | CowAgent | minimal_agent |
|------|----------|---------------|
| **短期记忆** | `agent.messages` 内存 | `Context.messages` + SQLite |
| **中期记忆** | `YYYY-MM-DD.md` | `YYYY-MM-DD.md` ✅ |
| **长期记忆** | `MEMORY.md` | `MEMORY.md` ✅ |
| **记忆检索** | 向量 + 关键词混合 | 向量 + 关键词混合 ✅ |
| **上下文裁剪** | 轮次 + Token 双重限制 | 仅轮次限制 |
| **Flush 触发** | 裁剪 + 溢出 + 定时 + 手动 | 裁剪 + 手动 |
| **Deep Dream** | 定时 + 手动 | 退出时 + 手动 |
| **上下文摘要注入** | ✅ | ✅ |
| **异步 Flush** | ✅ | ❌（同步） |

---

## 许可证

MIT License
