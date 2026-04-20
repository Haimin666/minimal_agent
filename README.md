# Minimal Agent

一个最小化的 AI Agent 实现，包含：
- 记忆系统（向量检索 + 关键词检索 + 混合检索）
- 记忆隔离（用户级隔离）
- 自动记忆（LLM 自动保存重要信息）
- 上下文管理
- Prompt 模块化构建

## 快速开始

```bash
# 1. 克隆项目
git clone https://github.com/your-username/minimal_agent.git
cd minimal_agent

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 API Key

# 4. 运行 Demo
python demo/realtime_demo.py
```

## 功能特性

### 记忆系统
- **向量检索**：基于 bge-m3 嵌入模型
- **关键词检索**：LIKE 模糊匹配（支持中文）
- **混合检索**：向量 + 关键词加权融合
- **时间衰减**：30天半衰期，旧记忆权重降低

### 记忆隔离
- `shared`: 共享记忆，所有用户可见
- `user`: 用户私有记忆，仅该用户可见

### 自动记忆
- LLM 自动识别需要记忆的内容
- 自动调用 `memory_save` 工具保存

### 交互界面
- 历史记录（↑/↓ 键）
- 命令补全（Tab 键）
- 多行输入支持

## 命令说明

| 命令 | 功能 |
|------|------|
| `<直接输入>` | 与助手对话（支持自动记忆） |
| `history` | 查看历史对话 |
| `prompt` | 查看系统提示词 |
| `messages` | 查看完整消息列表（含记忆注入位置） |
| `memory <关键词>` | 搜索记忆 |
| `save <内容>` | 主动保存记忆 |
| `clear` | 清空对话历史 |
| `q` | 退出 |

## 项目结构

```
minimal_agent/
├── config.py              # 配置管理
├── context.py             # 上下文管理
├── agent.py               # Agent 主类
├── memory/
│   ├── storage.py         # 存储层（SQLite）
│   ├── embedding.py       # 向量嵌入
│   ├── chunker.py         # 文本分块
│   └── manager.py         # 记忆管理器
├── prompt/
│   └── builder.py         # Prompt 构建
├── tools/
│   └── memory_tools.py    # 记忆工具
├── demo/
│   ├── realtime_demo.py   # 交互 Demo
│   ├── profession_generator.py  # 职业人设生成
│   ├── clean.py           # 清理脚本
│   └── README.md          # Demo 说明
├── .env.example           # 环境变量示例
├── requirements.txt       # 依赖列表
└── README.md              # 项目说明
```

## 配置说明

在 `.env` 文件中配置：

```env
# 对话模型
OPENAI_API_KEY=your-api-key
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini

# 嵌入模型
EMBEDDING_API_KEY=your-embedding-key
EMBEDDING_API_BASE=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
```

## 存储机制

### 记忆存储（两份）
- **文件**：`workspace/memory/users/{user_id}/*.md`（人类可读）
- **数据库**：`workspace/*.db`（SQLite，机器检索）

### 上下文存储
- **内存**：会话级，程序退出后丢失

## 许可证

MIT License
