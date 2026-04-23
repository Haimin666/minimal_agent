"""
层次化索引 - 三级检索架构

一级索引：标题向量（粗筛）
二级索引：块摘要向量（中筛）
三级索引：块内容向量（精筛）

存储：workspace/memory.db（统一数据库）
"""

from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
import sqlite3
import json
import hashlib


# ==================== 标题定义 ====================

TITLE_DEFINITIONS = {
    "基本信息": {
        "description": "用户的身份、职业、姓名、工作单位、个人背景、年龄、性别",
        "keywords": ["姓名", "名字", "职业", "工作", "身份", "老师", "教师", "工程师", "医生", "学生"],
    },
    "偏好": {
        "description": "用户的喜好、饮食习惯、兴趣爱好、生活方式、音乐、电影偏好",
        "keywords": ["喜欢", "不喜欢", "爱吃", "不吃", "爱好", "习惯", "口味"],
    },
    "待办": {
        "description": "用户的计划、任务、待办事项、日程安排、重要日期",
        "keywords": ["明天", "下周", "计划", "要", "需要", "待办", "记得"],
    },
    "项目": {
        "description": "用户的工作项目、开发任务、技术内容、代码工作",
        "keywords": ["项目", "开发", "代码", "系统", "功能", "需求"],
    },
    "关系": {
        "description": "用户的家人、朋友、同事、社交关系、重要联系人",
        "keywords": ["家人", "朋友", "同事", "同学", "妻子", "丈夫", "孩子"],
    },
    "地点": {
        "description": "用户的住址、常去地点、位置信息、工作地点",
        "keywords": ["住", "地址", "去", "在", "地点", "公司", "家"],
    },
    "其他": {
        "description": "无法归类的其他信息、杂项记录",
        "keywords": [],
    },
}


# ==================== 数据模型 ====================

@dataclass
class TitleEntry:
    """标题索引条目"""
    title: str
    description: str
    keywords: List[str]
    embedding: Optional[List[float]] = None


@dataclass
class BlockEntry:
    """块索引条目"""
    block_id: str           # 格式: {file_path}:{title}
    file_path: str          # 来源文件
    title: str              # 所属标题
    content: str            # 块原始内容
    summary: str = ""       # LLM 生成的摘要
    summary_embedding: Optional[List[float]] = None
    content_embedding: Optional[List[float]] = None
    timestamp: int = 0
    metadata: Dict = field(default_factory=dict)


@dataclass
class ProcessedQuery:
    """处理后的查询"""
    original: str
    expanded: str           # 扩展后的查询
    hypothesis: str         # 预设答案
    intent: str             # 意图分类
    target_titles: List[str]  # 预测的目标标题
    entities: List[str]     # 提取的实体
    rewritten: str = ""     # 改写后的查询（用于检索）
    embedding: Optional[List[float]] = None


# ==================== Query 改写提示词 ====================

QUERY_REWRITE_PROMPT = """你是一个查询改写助手，用于优化记忆检索效果。

用户问题可能模糊或口语化，请将其改写为更明确的检索语句。

改写规则：
1. 补充上下文关键词（如：身份、职业、偏好等）
2. 保留原始意图，不添加虚构信息
3. 改写后应该是陈述句或名词短语，便于向量匹配
4. 控制在 20 字以内

示例：
- "我是谁" → "用户的身份信息 姓名 职业"
- "我喜欢什么" → "用户的偏好 兴趣爱好 饮食习惯"
- "明天干嘛" → "用户的计划 日程安排 待办事项"
- "王老师是做什么的" → "王老师的职业 工作单位 身份"

用户问题：{query}
改写结果："""


# ==================== Query 处理器 ====================

class QueryProcessor:
    """
    Query 预处理层

    功能：
    1. 意图识别
    2. 查询扩展
    3. 查询改写（新增）
    4. 预设答案生成 (Hypothesis)
    5. 实体抽取
    6. 目标标题预测
    """

    def __init__(
        self,
        embedding_provider: Any = None,
        llm_client: Any = None,
        api_base: str = None,
        api_key: str = None,
        model: str = None
    ):
        self.embedding_provider = embedding_provider
        self.llm_client = llm_client
        self.api_base = api_base
        self.api_key = api_key
        self.model = model

        # 标题关键词映射（用于快速匹配）
        self._title_keywords = {}
        for title, info in TITLE_DEFINITIONS.items():
            for kw in info["keywords"]:
                if kw not in self._title_keywords:
                    self._title_keywords[kw] = []
                self._title_keywords[kw].append(title)

        # 标题向量（由外部设置）
        self._title_embeddings = {}

    def process(self, query: str) -> ProcessedQuery:
        """完整处理 query"""
        # 查询改写
        rewritten = self._rewrite_query(query)

        return ProcessedQuery(
            original=query,
            expanded=self._expand_query(query),
            rewritten=rewritten,
            hypothesis=self._generate_hypothesis(query),
            intent=self._classify_intent(query),
            target_titles=self._predict_titles(query),
            entities=self._extract_entities(query),
            # 优先使用改写后的查询生成 embedding
            embedding=self._get_embedding(rewritten or query) if self.embedding_provider else None
        )

    def _rewrite_query(self, query: str) -> str:
        """
        查询改写

        将模糊/口语化的问题改写为更明确的检索语句
        """
        # 如果有 LLM 配置，使用 LLM 改写
        if self.api_base and self.api_key and self.model:
            return self._rewrite_with_llm(query)

        # 回退：规则改写
        return self._rewrite_with_rules(query)

    def _rewrite_with_llm(self, query: str) -> str:
        """使用 LLM 改写查询"""
        try:
            import requests

            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": QUERY_REWRITE_PROMPT.format(query=query)}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 50
                },
                timeout=10
            )

            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            pass

        return self._rewrite_with_rules(query)

    def _rewrite_with_rules(self, query: str) -> str:
        """规则改写查询"""
        # 预定义改写规则
        rewrite_rules = {
            "我是谁": "用户的身份信息 姓名 职业 工作单位",
            "我是谁？": "用户的身份信息 姓名 职业 工作单位",
            "我是做什么的": "用户的职业 工作岗位 身份",
            "我喜欢什么": "用户的偏好 兴趣爱好 饮食习惯",
            "我喜欢吃什么": "用户的饮食偏好 食物喜好",
            "我明天": "用户的计划 日程安排 待办事项",
            "我下周": "用户的计划 日程安排 待办事项",
            "我的工作": "用户的职业 工作单位 岗位",
            "我的家人": "用户的家庭成员 亲戚关系",
            "我住在哪": "用户的住址 居住地点 地址",
        }

        # 精确匹配
        if query in rewrite_rules:
            return rewrite_rules[query]

        # 模糊匹配
        for pattern, rewritten in rewrite_rules.items():
            if pattern in query:
                return rewritten

        # 无法改写，返回原查询
        return query

    def _expand_query(self, query: str) -> str:
        """查询扩展"""
        # 同义词扩展
        synonyms = {
            "教": ["教学", "科目", "课程", "授课"],
            "工作": ["职业", "职位", "岗位"],
            "喜欢": ["爱好", "偏好", "感兴趣"],
            "明天": ["未来", "计划", "安排"],
        }

        expanded_words = [query]
        for word, syns in synonyms.items():
            if word in query:
                expanded_words.extend(syns)

        return " ".join(expanded_words)

    def _generate_hypothesis(self, query: str) -> str:
        """生成假设答案（用于 HyDE）"""
        # 简单规则生成，避免 LLM 调用
        hypothesis_templates = {
            "什么": f"答案可能是关于{query.replace('什么', '')}的具体信息",
            "谁": f"答案可能是某个人的身份信息",
            "哪": f"答案可能是某个地点或位置",
            "几": f"答案可能是某个数字或时间",
            "吗": f"答案可能是是或否",
        }

        for keyword, template in hypothesis_templates.items():
            if keyword in query:
                return template

        return f"答案包含关于{query}的相关信息"

    def _classify_intent(self, query: str) -> str:
        """意图分类"""
        intent_patterns = {
            "查询": ["什么", "谁", "哪", "几", "怎么", "如何"],
            "确认": ["吗", "是否", "有没有"],
            "操作": ["帮我", "请", "添加", "删除", "修改"],
        }

        for intent, patterns in intent_patterns.items():
            for pattern in patterns:
                if pattern in query:
                    return intent

        return "查询"

    def _predict_titles(self, query: str) -> List[str]:
        """预测目标标题"""
        # 1. 关键词匹配（使用子串匹配，而非单字符）
        matched_titles = set()
        for keyword, titles in self._title_keywords.items():
            if keyword in query:
                matched_titles.update(titles)

        # 2. 如果有 embedding，计算语义相似度
        if self.embedding_provider and self._title_embeddings:
            query_emb = self.embedding_provider.embed(query)
            title_scores = []
            for title, emb in self._title_embeddings.items():
                score = self._cosine_similarity(query_emb, emb)
                title_scores.append((title, score))
            title_scores.sort(key=lambda x: x[1], reverse=True)

            # 融合关键词匹配和语义匹配
            for title, score in title_scores[:3]:
                if score > 0.3:
                    matched_titles.add(title)

        return list(matched_titles) if matched_titles else ["其他"]

    def _extract_entities(self, query: str) -> List[str]:
        """实体抽取（简单规则）"""
        import re

        entities = []

        # 人名模式（X老师、X医生、X先生）
        name_patterns = [
            r'(\w{1,2}老师)',
            r'(\w{1,2}医生)',
            r'(\w{1,2}先生)',
            r'(\w{1,2}女士)',
        ]
        for pattern in name_patterns:
            matches = re.findall(pattern, query)
            entities.extend(matches)

        return list(set(entities))

    def _get_embedding(self, text: str) -> List[float]:
        """获取向量"""
        if self.embedding_provider:
            return self.embedding_provider.embed(text)
        return None

    def set_title_embeddings(self, title_embeddings: Dict[str, List[float]]):
        """设置标题向量（由 HierarchicalIndex 初始化时调用）"""
        self._title_embeddings = title_embeddings

    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """余弦相似度"""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        dot = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)


# ==================== 摘要生成器 ====================

class SummaryGenerator:
    """
    块摘要生成器

    为每个块生成简洁摘要，用于二级索引
    """

    SUMMARY_PROMPT = """请用一句话（不超过15字）概括以下记忆内容的核心信息：

{content}

摘要："""

    def __init__(
        self,
        api_base: str = None,
        api_key: str = None,
        model: str = None
    ):
        self.api_base = api_base
        self.api_key = api_key
        self.model = model

    def generate(self, content: str) -> str:
        """生成摘要"""
        # 如果内容很短，直接返回
        if len(content) <= 20:
            return content

        # 尝试 LLM 生成
        if self.api_base and self.api_key and self.model:
            return self._generate_with_llm(content)

        # 回退：规则生成
        return self._generate_with_rules(content)

    def _generate_with_llm(self, content: str) -> str:
        """使用 LLM 生成摘要"""
        try:
            import requests

            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": self.SUMMARY_PROMPT.format(content=content)}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 50
                },
                timeout=10
            )

            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            pass

        return self._generate_with_rules(content)

    def _generate_with_rules(self, content: str) -> str:
        """规则生成摘要"""
        # 提取第一行关键信息
        lines = [l.strip() for l in content.split('\n') if l.strip() and not l.startswith('#')]
        if lines:
            first_line = lines[0]
            # 移除 "- " 前缀
            if first_line.startswith('- '):
                first_line = first_line[2:]
            # 截断到 20 字符
            return first_line[:20] + ('...' if len(first_line) > 20 else '')
        return content[:20]


# ==================== Reranker ====================

class Reranker:
    """
    重排序器

    使用 Cross-Encoder 对检索结果进行重排序，提升精度
    """

    def __init__(
        self,
        api_base: str = None,
        api_key: str = None,
        model: str = None,
        top_n: int = 5,
        enabled: bool = True
    ):
        self.api_base = api_base
        self.api_key = api_key
        self.model = model or "Qwen/Qwen3-Reranker-8B"
        self.top_n = top_n
        self.enabled = enabled

    def rerank(
        self,
        query: str,
        results: List[Dict],
        top_n: int = None
    ) -> List[Dict]:
        """
        重排序检索结果

        Args:
            query: 查询文本
            results: 检索结果列表
            top_n: 返回数量

        Returns:
            重排序后的结果列表
        """
        if not self.enabled or not results:
            return results

        if not self.api_base or not self.api_key:
            return results[:top_n or self.top_n]

        top_n = top_n or self.top_n

        # 提取文档文本
        documents = [r.get('content', r.get('snippet', '')) for r in results]

        try:
            import requests

            response = requests.post(
                f"{self.api_base}/rerank",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                json={
                    "model": self.model,
                    "query": query,
                    "documents": documents,
                    "top_n": min(top_n, len(documents)),
                    "return_documents": False
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                # data.results 是按相关性排序的索引列表
                reranked = []
                for item in data.get("results", []):
                    idx = item.get("index", 0)
                    score = item.get("relevance_score", 0.0)
                    if idx < len(results):
                        result = results[idx].copy()
                        result['rerank_score'] = score
                        result['score'] = score  # 用 rerank 分数覆盖
                        reranked.append(result)
                return reranked[:top_n]

        except Exception as e:
            print(f"[Reranker] 重排序失败: {e}")

        return results[:top_n]


# ==================== 层次化索引 ====================

class HierarchicalIndex:
    """
    层次化索引管理器

    三级索引：
    1. 标题索引（一级）
    2. 块摘要索引（二级）
    3. 块内容索引（三级）

    支持 Rerank 重排序
    """

    def __init__(
        self,
        db_path: str,
        embedding_provider: Any = None,
        api_base: str = None,
        api_key: str = None,
        model: str = None,
        # Rerank 配置
        rerank_api_base: str = None,
        rerank_api_key: str = None,
        rerank_model: str = None,
        rerank_top_n: int = 5,
        rerank_enabled: bool = True,
    ):
        self.db_path = db_path
        self.embedding_provider = embedding_provider
        self.api_base = api_base
        self.api_key = api_key
        self.model = model

        # 确保目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # 初始化数据库
        self.conn = sqlite3.connect(db_path, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_tables()

        # 初始化组件
        self.query_processor = QueryProcessor(
            embedding_provider=embedding_provider,
            api_base=api_base,
            api_key=api_key,
            model=model
        )
        self.summary_generator = SummaryGenerator(api_base, api_key, model)

        # 初始化 Reranker
        self.reranker = Reranker(
            api_base=rerank_api_base,
            api_key=rerank_api_key,
            model=rerank_model,
            top_n=rerank_top_n,
            enabled=rerank_enabled
        )

        # 初始化标题索引
        self._init_title_index()

    def _init_tables(self):
        """初始化数据库表"""
        # 一级索引：标题向量
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS title_index (
                title TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                keywords TEXT,
                embedding TEXT,
                created_at INTEGER DEFAULT (strftime('%s', 'now'))
            )
        """)

        # 二级索引：块摘要（添加 user_id 支持隔离）
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS block_index (
                block_id TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT,
                summary_embedding TEXT,
                content TEXT NOT NULL,
                content_embedding TEXT,
                content_hash TEXT,
                user_id TEXT,
                timestamp INTEGER DEFAULT 0,
                created_at INTEGER DEFAULT (strftime('%s', 'now'))
            )
        """)

        # 索引
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_block_title ON block_index(title)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_block_file ON block_index(file_path)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_block_user ON block_index(user_id)")

    def _init_title_index(self):
        """初始化标题索引"""
        title_embeddings = {}

        for title, info in TITLE_DEFINITIONS.items():
            # 检查是否已存在
            row = self.conn.execute(
                "SELECT embedding FROM title_index WHERE title = ?", (title,)
            ).fetchone()

            if row and row['embedding']:
                title_embeddings[title] = json.loads(row['embedding'])
            elif self.embedding_provider:
                # 生成标题向量
                embedding = self.embedding_provider.embed(info["description"])
                title_embeddings[title] = embedding

                # 存储
                self.conn.execute("""
                    INSERT OR REPLACE INTO title_index (title, description, keywords, embedding)
                    VALUES (?, ?, ?, ?)
                """, (title, info["description"], json.dumps(info["keywords"]), json.dumps(embedding)))
            else:
                # 无 embedding provider，只存储描述和关键词
                self.conn.execute("""
                    INSERT OR IGNORE INTO title_index (title, description, keywords)
                    VALUES (?, ?, ?)
                """, (title, info["description"], json.dumps(info["keywords"])))

        # 设置到 query_processor（即使为空也设置，用于关键词匹配）
        self.query_processor.set_title_embeddings(title_embeddings)

    # ==================== 索引构建 ====================

    def index_file(self, file_path: str, content: str):
        """
        索引文件

        按标题分块，为每个块生成摘要和向量
        """
        # 解析文件为块
        blocks = self._parse_file(content, file_path)

        for block in blocks:
            self._index_block(block)

    def _parse_file(self, content: str, file_path: str) -> List[BlockEntry]:
        """解析文件为块列表"""
        import re

        blocks = []
        lines = content.split('\n')

        current_title = "其他"
        current_content = []
        current_start_line = 1

        for i, line in enumerate(lines, start=1):
            # 检测标题
            title_match = re.match(r'^#{1,6}\s+(.+)$', line)

            if title_match:
                # 保存前一个块
                if current_content:
                    block_content = '\n'.join(current_content).strip()
                    if block_content:
                        blocks.append(BlockEntry(
                            block_id=f"{file_path}:{current_title}:L{current_start_line}",
                            file_path=file_path,
                            title=current_title,
                            content=block_content,
                            timestamp=int(datetime.now().timestamp())
                        ))

                # 开始新块
                current_title = title_match.group(1).strip()
                current_content = []
                current_start_line = i + 1
            else:
                # 解析条目
                item = line.strip()
                if item and not item.startswith('#'):
                    if item.startswith('- '):
                        item = item[2:]
                    current_content.append(item)

        # 保存最后一个块
        if current_content:
            block_content = '\n'.join(current_content).strip()
            if block_content:
                blocks.append(BlockEntry(
                    block_id=f"{file_path}:{current_title}:L{current_start_line}",
                    file_path=file_path,
                    title=current_title,
                    content=block_content,
                    timestamp=int(datetime.now().timestamp())
                ))

        return blocks

    def _index_block(self, block: BlockEntry):
        """索引单个块"""
        # 计算内容 hash
        content_hash = hashlib.md5(block.content.encode()).hexdigest()

        # 检查是否已存在且未变化
        row = self.conn.execute(
            "SELECT content_hash FROM block_index WHERE block_id = ?", (block.block_id,)
        ).fetchone()

        if row and row['content_hash'] == content_hash:
            return  # 未变化，跳过

        # 生成摘要
        block.summary = self.summary_generator.generate(block.content)

        # 生成向量
        if self.embedding_provider:
            block.summary_embedding = self.embedding_provider.embed(block.summary)
            block.content_embedding = self.embedding_provider.embed(block.content)

        # 从文件路径提取 user_id
        user_id = self._extract_user_id(block.file_path)

        # 存储
        self.conn.execute("""
            INSERT OR REPLACE INTO block_index
            (block_id, file_path, title, summary, summary_embedding, content, content_embedding, content_hash, user_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            block.block_id,
            block.file_path,
            block.title,
            block.summary,
            json.dumps(block.summary_embedding) if block.summary_embedding else None,
            block.content,
            json.dumps(block.content_embedding) if block.content_embedding else None,
            content_hash,
            user_id,
            block.timestamp
        ))

    def _extract_user_id(self, file_path: str) -> Optional[str]:
        """从文件路径提取 user_id"""
        # 路径格式: memory/users/{user_id}/...
        import re
        match = re.search(r'memory/users/([^/]+)/', file_path)
        if match:
            return match.group(1)
        return None

    # ==================== 检索 ====================

    def search(
        self,
        query: str,
        user_id: str = None,
        limit: int = 10,
        use_hyde: bool = True,
        use_rerank: bool = True,
        use_multi_query: bool = True
    ) -> List[Dict]:
        """
        层次化检索

        Args:
            query: 查询文本
            user_id: 用户 ID（用于用户隔离）
            limit: 返回数量
            use_hyde: 是否使用 HyDE
            use_rerank: 是否使用 Rerank
            use_multi_query: 是否使用多查询融合

        Returns:
            检索结果列表
        """
        # Step 1: Query 处理
        processed = self.query_processor.process(query)

        # Step 2: 多查询融合（可选）
        if use_multi_query:
            return self._multi_query_search(
                processed, user_id, limit, use_hyde, use_rerank
            )

        # 单查询模式
        return self._single_query_search(
            processed, user_id, limit, use_hyde, use_rerank
        )

    def _single_query_search(
        self,
        processed: ProcessedQuery,
        user_id: str,
        limit: int,
        use_hyde: bool,
        use_rerank: bool
    ) -> List[Dict]:
        """单查询检索"""
        # 一级索引 - 标题匹配
        candidate_titles = self._search_titles(processed, top_k=2)

        # 二级索引 - 块摘要匹配（带用户隔离）
        candidate_blocks = self._search_block_summaries(
            processed,
            candidate_titles,
            user_id=user_id,
            top_k=limit * 3
        )

        # 三级索引 - 内容匹配
        results = self._search_block_contents(
            processed,
            candidate_blocks,
            use_hyde=use_hyde,
            top_k=limit * 2
        )

        # Rerank 重排序
        if use_rerank and self.reranker.enabled and results:
            results = self.reranker.rerank(
                query=processed.rewritten or processed.original,
                results=results,
                top_n=limit
            )

        return results[:limit]

    def _multi_query_search(
        self,
        processed: ProcessedQuery,
        user_id: str,
        limit: int,
        use_hyde: bool,
        use_rerank: bool
    ) -> List[Dict]:
        """
        多查询融合检索

        同时使用原始查询、改写查询、HyDE 查询进行检索，
        合并去重后重排序
        """
        all_results = {}  # key: block_id, value: result

        # 查询 1: 原始查询
        results_original = self._single_query_search(
            processed, user_id, limit * 2, use_hyde=False, use_rerank=False
        )
        for r in results_original:
            key = r['block_id']
            if key not in all_results:
                all_results[key] = r
                all_results[key]['query_sources'] = ['original']
            else:
                all_results[key]['query_sources'].append('original')

        # 查询 2: 改写查询
        if processed.rewritten and processed.rewritten != processed.original:
            # 创建改写查询的 ProcessedQuery
            rewritten_processed = ProcessedQuery(
                original=processed.rewritten,
                expanded=processed.expanded,
                rewritten=processed.rewritten,
                hypothesis=processed.hypothesis,
                intent=processed.intent,
                target_titles=processed.target_titles,
                entities=processed.entities,
                embedding=self._get_embedding(processed.rewritten) if self.embedding_provider else None
            )
            results_rewritten = self._single_query_search(
                rewritten_processed, user_id, limit * 2, use_hyde=False, use_rerank=False
            )
            for r in results_rewritten:
                key = r['block_id']
                if key not in all_results:
                    all_results[key] = r
                    all_results[key]['query_sources'] = ['rewritten']
                else:
                    all_results[key]['query_sources'].append('rewritten')
                    # 融合分数：取最大值
                    all_results[key]['score'] = max(all_results[key]['score'], r['score'])

        # 查询 3: HyDE 查询（如果有 embedding）
        if use_hyde and self.embedding_provider and processed.hypothesis:
            hypothesis_processed = ProcessedQuery(
                original=processed.hypothesis,
                expanded=processed.hypothesis,
                rewritten=processed.rewritten,
                hypothesis=processed.hypothesis,
                intent=processed.intent,
                target_titles=processed.target_titles,
                entities=processed.entities,
                embedding=self._get_embedding(processed.hypothesis)
            )
            results_hyde = self._single_query_search(
                hypothesis_processed, user_id, limit * 2, use_hyde=False, use_rerank=False
            )
            for r in results_hyde:
                key = r['block_id']
                if key not in all_results:
                    all_results[key] = r
                    all_results[key]['query_sources'] = ['hyde']
                else:
                    all_results[key]['query_sources'].append('hyde')
                    all_results[key]['score'] = max(all_results[key]['score'], r['score'])

        # 转换为列表
        merged_results = list(all_results.values())

        # 根据命中的查询数量加权
        for r in merged_results:
            source_count = len(r.get('query_sources', []))
            r['multi_query_boost'] = min(source_count / 3.0, 1.0)  # 最多 3 个查询
            r['score'] = r['score'] * (0.7 + 0.3 * r['multi_query_boost'])

        # Rerank 重排序
        if use_rerank and self.reranker.enabled and merged_results:
            merged_results = self.reranker.rerank(
                query=processed.rewritten or processed.original,
                results=merged_results,
                top_n=limit
            )
        else:
            # 无 Rerank，按分数排序
            merged_results.sort(key=lambda x: x['score'], reverse=True)

        return merged_results[:limit]

    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """获取文本 embedding"""
        if self.embedding_provider:
            return self.embedding_provider.embed(text)
        return None

    def _search_titles(self, processed: ProcessedQuery, top_k: int = 2) -> List[str]:
        """一级索引：标题匹配"""
        if not processed.embedding:
            # 回退到关键词匹配
            return processed.target_titles[:top_k] if processed.target_titles else ["其他"]

        # 语义匹配
        rows = self.conn.execute(
            "SELECT title, embedding FROM title_index WHERE embedding IS NOT NULL"
        ).fetchall()

        scores = []
        for row in rows:
            emb = json.loads(row['embedding'])
            score = self._cosine_similarity(processed.embedding, emb)
            scores.append((row['title'], score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [t for t, s in scores[:top_k]]

    def _search_block_summaries(
        self,
        processed: ProcessedQuery,
        candidate_titles: List[str],
        user_id: str = None,
        top_k: int = 10
    ) -> List[Dict]:
        """二级索引：块摘要匹配（支持用户隔离）"""
        if not candidate_titles:
            candidate_titles = ["其他"]

        # 构建查询条件
        title_placeholders = ','.join('?' * len(candidate_titles))

        # 用户隔离条件
        if user_id:
            user_filter = "AND (user_id IS NULL OR user_id = ?)"
            user_params = [user_id]
        else:
            user_filter = ""
            user_params = []

        # 无 embedding 时，不要求 summary_embedding
        if processed.embedding:
            sql = f"""
                SELECT block_id, file_path, title, summary, summary_embedding, content, timestamp, user_id
                FROM block_index
                WHERE title IN ({title_placeholders})
                AND summary_embedding IS NOT NULL
                {user_filter}
            """
            rows = self.conn.execute(sql, candidate_titles + user_params).fetchall()
        else:
            # 回退：直接按标题匹配
            sql = f"""
                SELECT block_id, file_path, title, summary, summary_embedding, content, timestamp, user_id
                FROM block_index
                WHERE title IN ({title_placeholders})
                {user_filter}
            """
            rows = self.conn.execute(sql, candidate_titles + user_params).fetchall()

        if not processed.embedding:
            # 无 embedding 时，直接返回
            results = []
            for row in rows[:top_k]:
                results.append({
                    **dict(row),
                    'summary_score': 0.5  # 默认分数
                })
            return results

        # 计算摘要相似度
        results = []
        for row in rows:
            emb = json.loads(row['summary_embedding'])
            score = self._cosine_similarity(processed.embedding, emb)
            results.append({
                **dict(row),
                'summary_score': score
            })

        results.sort(key=lambda x: x['summary_score'], reverse=True)
        return results[:top_k]

    def _search_block_contents(
        self,
        processed: ProcessedQuery,
        candidate_blocks: List[Dict],
        use_hyde: bool = True,
        top_k: int = 5
    ) -> List[Dict]:
        """三级索引：内容匹配"""
        results = []

        for block in candidate_blocks:
            # 获取内容
            row = self.conn.execute(
                "SELECT content, content_embedding, timestamp FROM block_index WHERE block_id = ?",
                (block['block_id'],)
            ).fetchone()

            if not row:
                continue

            # 计算内容分数
            if row['content_embedding'] and processed.embedding:
                content_emb = json.loads(row['content_embedding'])

                # HyDE: 用假设答案向量检索
                if use_hyde and self.embedding_provider:
                    hypothesis_emb = self.embedding_provider.embed(processed.hypothesis)
                    content_score = self._cosine_similarity(hypothesis_emb, content_emb)
                else:
                    content_score = self._cosine_similarity(processed.embedding, content_emb)
            else:
                # 无 embedding 时，使用默认分数
                content_score = 0.5

            # 融合分数：摘要 30% + 内容 70%
            summary_score = block.get('summary_score', 0.5)
            final_score = 0.3 * summary_score + 0.7 * content_score

            results.append({
                'block_id': block['block_id'],
                'content': row['content'],
                'file_path': block['file_path'],
                'title': block['title'],
                'summary': block['summary'],
                'user_id': block.get('user_id'),
                'score': final_score,
                'timestamp': row['timestamp']
            })

        # 排序
        results.sort(key=lambda x: x['score'], reverse=True)

        return results[:top_k]

    # ==================== 工具方法 ====================

    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """余弦相似度"""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        dot = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    def get_stats(self) -> Dict:
        """获取统计信息"""
        title_count = self.conn.execute("SELECT COUNT(*) FROM title_index").fetchone()[0]
        block_count = self.conn.execute("SELECT COUNT(*) FROM block_index").fetchone()[0]
        block_with_emb = self.conn.execute(
            "SELECT COUNT(*) FROM block_index WHERE content_embedding IS NOT NULL"
        ).fetchone()[0]

        return {
            'titles': title_count,
            'blocks': block_count,
            'blocks_with_embedding': block_with_emb
        }

    def close(self):
        """关闭连接"""
        self.conn.close()
