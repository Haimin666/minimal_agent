# Minimal Agent - CowAgent 核心机制最小实现

> 这是一个教学性质的最小实现，用于理解 AI Agent 的上下文管理、记忆系统和 Prompt 注入机制。

## 项目背景

基于 [CowAgent](/Users/lbc/CowAgent) 项目的核心机制分析，实现了一个约 600 行代码的最小版本，保留了：

- ✅ 向量检索（余弦相似度）
- ✅ 关键词检索（LIKE）
- ✅ 混合检索（加权融合）
- ✅ 文本分块（带重叠）
- ✅ 时间衰减
- ✅ 文件检索（memory_get）
- ✅ 真实 LLM 调用
- ✅ Prompt 模块化构建
- ✅ 上下文消息历史

## 目录结构

```
minimal_agent/
├── __init__.py           # 模块入口
├── config.py             # 配置 dataclass
├── context.py            # 上下文管理（会话消息历史）
├── agent.py              # Agent 主类（接入 LLM）
├── test.py               # 测试脚本
├── memory/
│   ├── __init__.py
│   ├── storage.py        # SQLite + 向量/关键词/混合检索
│   ├── embedding.py      # OpenAI 兼容 API 向量嵌入
│   ├── chunker.py        # 文本分块（带重叠）
│   └── manager.py        # 记忆管理器（整合上述组件）
├── prompt/
│   ├── __init__.py
│   └── builder.py        # Prompt 模块化构建
└── tools/
    ├── __init__.py
    └── memory_tools.py   # memory_search, memory_get 工具
```

## 核心机制说明

### 1. 上下文管理 (context.py)

CowAgent 中有两个 "Context" 概念：
- `bridge/context.py` 的 `Context` - 单条消息的容器 (type, content, kwargs)
- `Agent.messages` - 会话级别的对话历史

本实现简化为单一 `Context` 类，管理会话消息历史：

```python
@dataclass
class Context:
    session_id: str
    messages: List[Message] = field(default_factory=list)
    user_id: Optional[str] = None

    def add_message(self, role: str, content: str, **metadata)
    def get_openai_messages(self) -> List[Dict]
    def clear(self)
```

### 2. 记忆系统 (memory/)

#### 存储层 (storage.py)

SQLite 存储，embedding 以 JSON 格式存储：

```sql
CREATE TABLE chunks (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    start_line INTEGER,
    end_line INTEGER,
    text TEXT NOT NULL,
    embedding TEXT,  -- JSON 序列化的 float 数组
    metadata TEXT,
    created_at TIMESTAMP
)
```

#### 三种检索方式

1. **向量检索** - 余弦相似度
   ```python
   def search_vector(self, query_embedding, limit=10):
       # 取出所有有向量的 chunk
       # 在内存中计算余弦相似度
       # 排序返回 Top K
   ```

2. **关键词检索** - LIKE 模糊匹配
   ```python
   def search_keyword(self, query, limit=10):
       # 提取中英文关键词
       # LIKE 模糊匹配
   ```

3. **混合检索** - 加权融合
   ```python
   def search_hybrid(self, query, query_embedding, limit=10,
                     vector_weight=0.7, keyword_weight=0.3):
       # 分别执行向量和关键词检索
       # 合并去重，加权计算分数
       # 应用时间衰减
   ```

#### 时间衰减

日期记忆权重按指数衰减：

```python
# MEMORY.md: 不衰减 (evergreen)
# memory/2024-01-01.md: 按日期衰减

decay = exp(-ln2 / half_life_days * age_days)
# half_life_days 默认 30 天
```

#### 文本分块 (chunker.py)

```python
class TextChunker:
    max_tokens: 500       # 每块最大 token
    overlap_tokens: 50    # 重叠 token (约 20%)

    # 估算: 中英文混合约 4 字符 = 1 token
```

### 3. Prompt 注入 (prompt/builder.py)

模块化构建系统提示词：

```
1. 基础提示词
2. 🔧 工具说明
3. 🧠 记忆系统说明
4. 📂 工作空间说明
5. 📋 项目上下文 (AGENT.md, MEMORY.md)
6. ⚙️ 运行时信息
```

### 4. 工具系统 (tools/memory_tools.py)

- `memory_search` - 搜索长期记忆
- `memory_get` - 读取记忆文件

## 与 CowAgent 的差异

| 组件 | CowAgent | 最小实现 |
|------|----------|---------|
| FTS5 全文索引 | FTS5 + LIKE | 仅 LIKE |
| 技能系统 | SkillManager + SKILL.md | 删除 |
| 知识系统 | knowledge/ 目录 | 删除 |
| 流式输出 | SSE | 删除 |
| 多渠道 | 钉钉/微信/Web | 仅 CLI |
| 线程安全 | threading.Lock | 删除 |
| 上下文文件 | 5 个 | 2 个 |

## 使用方式

### 基础使用

```python
from minimal_agent import SimpleAgent, Config

config = Config(
    api_key="your-key",
    api_base="https://api.openai.com/v1",
    model="gpt-4o-mini",
    workspace_dir="./workspace"
)

agent = SimpleAgent(config)

# 添加记忆
agent.add_memory("用户喜欢 Python 编程")
agent.add_memory("用户正在研究 AI Agent 架构")

# 对话（自动检索相关记忆）
response = agent.chat("我之前跟你说过什么？")
print(response)
```

### 单独使用组件

```python
from minimal_agent.memory import MemoryStorage, MemoryChunk
from minimal_agent.memory import TextChunker
from minimal_agent.prompt import PromptBuilder

# 文本分块
chunker = TextChunker(max_tokens=500, overlap_tokens=50)
chunks = chunker.chunk_text(long_text)

# 存储和检索
storage = MemoryStorage("memory.db")
storage.save_chunk(MemoryChunk(id="1", text="测试内容", path="test.md"))
results = storage.search_keyword("测试")

# Prompt 构建
builder = PromptBuilder("./workspace")
prompt = builder.build(
    base_prompt="你是 AI 助手",
    tools=[...],
    runtime_info={"当前时间": "2024-01-20"}
)
```

## 测试

```bash
cd /Users/lbc/minimal_agent
python test.py
```

测试覆盖：
- 文本分块
- 关键词检索
- 时间衰减
- 上下文管理
- Prompt 构建
- 工具调用

## 后续开发方向

1. **添加 FTS5 全文索引** - 提升英文关键词检索效果
2. **添加工具注册机制** - 支持动态添加工具
3. **添加流式输出** - SSE 实时响应
4. **添加多渠道支持** - 钉钉/微信等
5. **添加技能系统** - SKILL.md 动态加载
6. **添加知识系统** - knowledge/ 结构化知识

## 参考资料

- CowAgent 源码: `/Users/lbc/CowAgent`
- 计划文档: `/Users/lbc/.claude/plans/misty-squishing-yeti.md`
