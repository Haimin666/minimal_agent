# Minimal Agent vs CowAgent 功能对比

## 架构对比

| 特性 | Minimal Agent | CowAgent |
|------|---------------|----------|
| 定位 | 轻量级独立库 | 完整企业级 Agent |
| 依赖 | 仅 requests | 依赖 channel, bot, common 等 |
| 适用场景 | 嵌入式、教学、快速原型 | 生产环境、多渠道部署 |

## 三层记忆架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    短期记忆（Context）                           │
│                                                                 │
│  Minimal Agent: Context.messages + context.db (SQLite)         │
│  CowAgent:     同样使用 context.db                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓ 裁剪时 Flush
┌─────────────────────────────────────────────────────────────────┐
│              中期记忆（Daily: YYYY-MM-DD.md）                     │
│                                                                 │
│  Minimal Agent: workspace/memory/users/{user_id}/YYYY-MM-DD.md │
│  CowAgent:     同样路径结构                                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓ 退出时 Distill
┌─────────────────────────────────────────────────────────────────┐
│                 长期记忆（MEMORY.md）                             │
│                                                                 │
│  Minimal Agent: workspace/memory/users/{user_id}/MEMORY.md     │
│  CowAgent:     同样路径结构                                      │
└─────────────────────────────────────────────────────────────────┘
```

## 功能对比表

| 功能 | Minimal Agent | CowAgent | 说明 |
|------|:-------------:|:--------:|------|
| **短期记忆** |  |  |  |
| 内存消息列表 | ✅ | ✅ | 相同实现 |
| SQLite 持久化 | ✅ | ✅ | 相同实现 |
| 上下文裁剪 | ✅ | ✅ | 相同实现 |
| 摘要注入 | ✅ | ✅ | 相同实现 |
| **中期记忆** |  |  |  |
| Flush 到天级文件 | ✅ | ✅ | 相同实现 |
| LLM 总结 | ✅ | ✅ | 相同实现 |
| 异步 Flush | ❌ | ✅ | CowAgent 后台线程 |
| 去重写入 | ❌ | ✅ | CowAgent 基于 hash |
| **长期记忆** |  |  |  |
| Deep Dream 蒸馏 | ✅ | ✅ | 相同实现 |
| [MEMORY] 输出格式 | ✅ | ✅ | 相同实现 |
| 梦境日记 | ❌ | ✅ | CowAgent 生成 [DREAM] |
| 输入 hash 去重 | ❌ | ✅ | CowAgent 跳过相同输入 |
| **记忆检索** |  |  |  |
| 向量检索 | ✅ | ✅ | 相同实现 |
| FTS5 关键词检索 | ✅ | ❌ | Minimal Agent 特有 |
| 混合检索 | ✅ | ❌ | Minimal Agent 特有 |
| LIKE 中文检索 | ✅ | ❌ | Minimal Agent 特有 |
| **工具支持** |  |  |  |
| memory_save | ✅ | ✅ | 相同实现 |
| memory_search | ✅ | ✅ | 相同实现 |
| file_read/write/edit | ✅ | ❌ | Minimal Agent 特有 |
| **Prompt 构建** |  |  |  |
| AGENT.md 加载 | ✅ | ✅ | 相同实现 |
| MEMORY.md 加载 | ✅ | ✅ | 相同实现 |
| 运行时信息注入 | ✅ | ✅ | 相同实现 |

## 关键差异

### 1. 混合检索（Minimal Agent 特有）

Minimal Agent 实现了向量 + 关键词的混合检索：

```python
# Minimal Agent
results = agent.memory_manager.search(
    query="王老师",
    user_id="teacher",
    vector_weight=0.7,    # 向量权重
    keyword_weight=0.3    # 关键词权重
)
```

CowAgent 仅使用向量检索。

### 2. 梦境日记（CowAgent 特有）

CowAgent 在 Deep Dream 时生成两部分：
- `[MEMORY]`: 更新后的长期记忆
- `[DREAM]`: 梦境日记（记录整理发现）

```markdown
[MEMORY]
- 用户是王教授，在清华大学任教
- 用户喜欢听古典音乐

[DREAM]
今天的记忆整理发现了一些有趣的重复...
```

### 3. 异步 Flush（CowAgent 特有）

CowAgent 使用后台线程执行 Flush，不阻塞主流程：

```python
# CowAgent
thread = threading.Thread(
    target=self._flush_worker,
    args=(snapshot, user_id, reason, max_messages, callback),
    daemon=True,
)
thread.start()
```

Minimal Agent 是同步执行。

### 4. 去重机制（CowAgent 特有）

CowAgent 使用 hash 去重，避免重复写入：

```python
# CowAgent
h = hashlib.md5(text.encode("utf-8")).hexdigest()
if h not in self._trim_flushed_hashes:
    self._trim_flushed_hashes.add(h)
    deduped.append(m)
```

### 5. 文件操作工具（Minimal Agent 特有）

Minimal Agent 内置文件操作工具：

```python
# Minimal Agent
agent.chat("读取 config.json")  # 自动调用 file_read
agent.chat("写入 test.txt: hello")  # 自动调用 file_write
```

## 代码结构对比

```
Minimal Agent                    CowAgent
─────────────────────────────────────────────────────────────
minimal_agent/                   agent/
├── config.py                    ├── config.py
├── context.py                   ├── context.py
├── context_store.py             ├── context_store.py
├── agent.py                     ├── agent/
│                               │   ├── agent.py
│                               │   └── agent_stream.py
├── memory/                      ├── memory/
│   ├── storage.py               │   ├── storage.py
│   ├── embedding.py             │   ├── embedding.py
│   ├── chunker.py               │   ├── chunker.py
│   ├── manager.py               │   ├── manager.py
│   ├── flusher.py               │   └── summarizer.py  ← 包含 flusher + deep_dream
│   └── deep_dream.py            │
├── prompt/                      ├── prompt/
│   └── builder.py               │   └── builder.py
└── tools/                       └── tools/
    └── file_tools.py                └── (多种工具)
```

## 依赖对比

### Minimal Agent

```
requests
```

### CowAgent

```
requests
channel (钉钉、微信等)
bot
common (log, utils)
```

## 使用场景

### Minimal Agent 适合

- 嵌入到其他 Python 应用
- 教学/学习 Agent 架构
- 快速原型验证
- 轻量级命令行工具

### CowAgent 适合

- 企业级生产部署
- 多渠道消息接入（钉钉、微信等）
- 需要完整工具链
- 高并发场景

## 迁移建议

从 Minimal Agent 迁移到 CowAgent：

1. **记忆文件兼容**：直接复制 `workspace/memory/` 目录
2. **上下文兼容**：直接复制 `workspace/context.db`
3. **配置迁移**：大部分配置项通用

从 CowAgent 迁移到 Minimal Agent：

1. **功能裁剪**：移除异步 Flush、梦境日记等
2. **工具调整**：移除文件操作工具的依赖
3. **检索调整**：CowAgent 仅用向量检索，无需混合检索
