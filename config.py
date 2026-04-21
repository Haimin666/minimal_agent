"""配置管理 - 从环境变量加载配置"""

from dataclasses import dataclass, field
from typing import Optional
import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()


@dataclass
class Config:
    """Agent 配置"""

    # 对话模型配置
    api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    api_base: str = field(default_factory=lambda: os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"))
    model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

    # Embedding 配置
    embedding_api_key: str = field(default_factory=lambda: os.getenv("EMBEDDING_API_KEY", os.getenv("OPENAI_API_KEY", "")))
    embedding_api_base: str = field(default_factory=lambda: os.getenv("EMBEDDING_API_BASE", os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")))
    embedding_model: str = field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"))
    embedding_dimensions: int = field(default_factory=lambda: int(os.getenv("EMBEDDING_DIMENSIONS", "1536")))

    # 记忆配置
    db_path: str = "memory.db"
    context_db_path: str = "context.db"  # Session 历史数据库
    chunk_max_tokens: int = 500
    chunk_overlap_tokens: int = 50
    vector_weight: float = 0.7
    keyword_weight: float = 0.3
    max_results: int = 10

    # 工作空间（相对路径）
    workspace_dir: str = "./workspace"

    # 时间衰减 (天)
    half_life_days: float = 30.0
