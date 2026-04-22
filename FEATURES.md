# Minimal Agent 功能总结

## 核心架构

### 三层记忆模型

```
┌─────────────────────────────────────────────────────────────────┐
│                    短期记忆（Context）                           │
│  存储: Context.messages (内存) + context.db (SQLite)            │
│  限制: max_context_turns=20 轮                                   │
│  特点: 快速访问，自动裁剪，摘要注入                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓ 裁剪时 Flush
┌─────────────────────────────────────────────────────────────────┐
│              中期记忆（Daily: YYYY-MM-DD.md）                     │
│  存储: workspace/memory/YYYY-MM-DD.md                            │
│  触发: 上下文裁剪时 + 手动 flush()                                │
│  特点: 追加写入，人类可读                                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓ 退出时 Distill
┌─────────────────────────────────────────────────────────────────┐
│                 长期记忆（MEMORY.md）                             │
│  存储: workspace/MEMORY.md                                       │
│  触发: exit() 时 + 手动 distill()                                 │
│  特点: 覆写更新，去重合并，~50条上限                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 功能清单

### 1. 记忆检索（混合检索）

```python
# 向量检索 + 关键词检索 加权融合
results = agent.memory_manager.search(
    query="用户职业",
    user_id="teacher",
    limit=10,
    vector_weight=0.7,    # 向量权重
    keyword_weight=0.3    # 关键词权重
)
```

**检索策略**：
- 向量检索：余弦相似度，捕捉语义关联
- 关键词检索：FTS5 全文索引 + BM25 排序
- 中文关键词：自动回退到 LIKE 模糊匹配

### 2. 上下文管理

```python
# 添加消息（可能触发裁剪）
discarded = agent.context.add_message("user", "你好")
if discarded:
    print(f"裁剪了 {len(discarded)} 条消息")

# 获取带摘要的消息
messages = agent.context.get_messages_with_summary()

# 注入摘要
agent.context.inject_context_summary("之前讨论了...")
```

**裁剪策略**：
- 超过 `max_turns` 时保留后一半
- 被裁剪的消息自动 Flush 到每日记忆
- 同时生成摘要注入到当前对话

### 3. Flush（对话总结）

```python
# 手动 Flush
agent.flush()

# Flush 时自动：
# 1. LLM 总结对话
# 2. 写入 YYYY-MM-DD.md
# 3. 同步到 memory.db
```

### 4. Deep Dream（记忆蒸馏）

```python
# 手动蒸馏
agent.distill(lookback_days=3)

# 蒸馏时自动：
# 1. 读取 MEMORY.md + 近期天级记忆
# 2. LLM 整理（去重、合并、冲突更新）
# 3. 覆写 MEMORY.md（限制 50 条）
```

### 5. 退出流程

```python
agent.exit()
# 自动执行：
# 1. flush() - 保存当前对话
# 2. distill() - 蒸馏长期记忆
```

---

## 观测方式

### 1. 观测记忆

```bash
# 查看长期记忆
cat workspace/MEMORY.md

# 查看每日记忆
cat workspace/memory/2026-04-22.md
cat workspace/memory/users/teacher/2026-04-22.md

# 查看 SQLite 数据
sqlite3 workspace/memory.db "
SELECT path, start_line, text 
FROM chunks 
WHERE scope='user' 
LIMIT 5;
"

# 查看统计
sqlite3 workspace/memory.db "
SELECT COUNT(*) as chunks FROM chunks;
SELECT COUNT(*) as files FROM files;
"
```

### 2. 观测上下文

```bash
# 查看 Session 历史
sqlite3 workspace/context.db "
SELECT session_id, json_array_length(messages) as msg_count 
FROM sessions;
"

# 导出完整历史
sqlite3 workspace/context.db "
SELECT messages FROM sessions WHERE session_id='teacher_session';
" | python -m json.tool
```

### 3. 观测 Prompt

```python
from prompt import PromptBuilder

builder = PromptBuilder("./workspace")

# 加载上下文文件
files = builder.load_context_files()
for f in files:
    print(f"### {f.path}")
    print(f.content[:200])

# 构建完整 Prompt
prompt = builder.build(
    base_prompt="你是 AI 助手",
    context_files=files,
    runtime_info={"时间": "2026-04-22", "用户": "teacher"}
)
print(prompt)
```

---

## 调试步骤

### Step 1: 测试检索

```python
from agent import SimpleAgent

agent = SimpleAgent(user_id="test")

# 添加记忆
agent.add_memory("用户是王老师，教语文", scope="user")

# 检索
results = agent.memory_manager.search("王老师")
for r in results:
    print(f"路径: {r.path}")
    print(f"分数: {r.score:.3f}")
    print(f"内容: {r.snippet[:100]}")
```

### Step 2: 测试裁剪

```python
agent = SimpleAgent(user_id="test")
agent.config.max_context_turns = 3  # 临时设置小值

for i in range(10):
    result = agent.chat(f"消息 {i}")
    print(f"轮次 {i}: flushed={result['flushed']}")
```

### Step 3: 测试 Flush

```python
agent = SimpleAgent(user_id="test")
agent.chat("我喜欢吃苹果")
agent.chat("我还喜欢吃香蕉")

# 手动 Flush
agent.flush()

# 查看文件
import os
print(os.popen("cat workspace/memory/users/test/2026-04-22.md").read())
```

### Step 4: 测试 Deep Dream

```python
agent = SimpleAgent(user_id="test")
agent.chat("我叫王老师")
agent.chat("我教语文")

# 退出时自动蒸馏
agent.exit()

# 查看长期记忆
print(os.popen("cat workspace/memory/users/test/MEMORY.md").read())
```

---

## 文件结构

```
minimal_agent/
├── config.py              # 配置管理
├── context.py             # 上下文（裁剪 + 摘要注入）
├── context_store.py       # Session 持久化（SQLite）
├── agent.py               # Agent 主类
├── memory/
│   ├── storage.py         # 存储（SQLite + FTS5）
│   ├── embedding.py       # 向量嵌入
│   ├── chunker.py         # 文本分块
│   ├── manager.py         # 记忆管理（混合检索）
│   ├── flusher.py         # 对话总结
│   └── deep_dream.py      # 记忆蒸馏
├── prompt/
│   └── builder.py         # Prompt 构建
└── tools/
    └── file_tools.py      # 文件操作

workspace/
├── AGENT.md               # Agent 人格
├── MEMORY.md              # 长期记忆
├── context.db             # Session 历史
├── memory.db              # 向量数据库
└── memory/
    └── users/{user_id}/
        ├── MEMORY.md
        └── YYYY-MM-DD.md
```
