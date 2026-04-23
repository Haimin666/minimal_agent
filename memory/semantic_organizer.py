"""
语义组织器 - 按标题分块 + 语义去重

功能:
    1. 按 Markdown 标题分块
    2. 语义匹配找到目标标题
    3. 块内语义去重
    4. 无匹配时新建标题
"""

from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
import re
import hashlib


@dataclass
class MemoryBlock:
    """记忆块 - 对应一个标题下的内容"""
    title: str           # 标题（如 "基本信息"）
    level: int           # 标题级别（2 表示 ##）
    items: List[str]     # 条目列表
    embedding: Optional[List[float]] = None  # 块的语义向量（用于标题匹配）

    @property
    def title_line(self) -> str:
        return "#" * self.level + " " + self.title

    def to_markdown(self) -> str:
        """转换为 Markdown"""
        lines = [self.title_line]
        for item in self.items:
            if not item.startswith("-"):
                item = f"- {item}"
            lines.append(item)
        return "\n".join(lines)


@dataclass
class MemoryItem:
    """单条记忆"""
    content: str
    embedding: Optional[List[float]] = None
    content_hash: str = ""

    def __post_init__(self):
        if not self.content_hash:
            self.content_hash = hashlib.md5(self.content.encode()).hexdigest()


# 预定义的标题及其语义描述
DEFAULT_SECTIONS = {
    "基本信息": "用户的身份信息，包括姓名、职业、身份、工作单位等",
    "偏好": "用户的喜好和习惯，包括饮食、爱好、生活习惯等",
    "待办": "用户提到的重要计划和待办事项",
    "项目": "用户正在做的项目和工作内容",
    "关系": "用户提到的重要人际关系，家人、朋友、同事等",
    "地点": "用户常去的地点、住址等位置信息",
}

# 语义相似度阈值
TITLE_MATCH_THRESHOLD = 0.3    # 标题匹配阈值
DEDUP_SIMILARITY_THRESHOLD = 0.85  # 去重相似度阈值


class SemanticOrganizer:
    """
    语义组织器

    按标题组织记忆内容，支持语义匹配和去重
    """

    def __init__(
        self,
        embedding_provider: Any = None,
        predefined_sections: Dict[str, str] = None
    ):
        self.embedding_provider = embedding_provider
        self.predefined_sections = predefined_sections or DEFAULT_SECTIONS

        # 预计算标题的语义向量
        self._title_embeddings: Dict[str, List[float]] = {}
        self._init_title_embeddings()

    def _init_title_embeddings(self):
        """预计算预定义标题的语义向量"""
        if not self.embedding_provider:
            return

        for title, description in self.predefined_sections.items():
            try:
                self._title_embeddings[title] = self.embedding_provider.embed(description)
            except Exception:
                pass

    # ==================== 文件解析 ====================

    def parse_file(self, file_path: Path) -> List[MemoryBlock]:
        """解析 Markdown 文件为块列表"""
        if not file_path.exists():
            return []

        content = file_path.read_text(encoding="utf-8")
        return self.parse_markdown(content)

    def parse_markdown(self, content: str) -> List[MemoryBlock]:
        """解析 Markdown 内容为块列表"""
        lines = content.split("\n")
        blocks = []

        current_block = None

        for line in lines:
            # 检测标题
            title_match = re.match(r'^(#{1,6})\s+(.+)$', line)

            if title_match:
                # 保存当前块
                if current_block and current_block.items:
                    blocks.append(current_block)

                # 开始新块
                level = len(title_match.group(1))
                title = title_match.group(2).strip()
                current_block = MemoryBlock(title=title, level=level, items=[])
            else:
                # 解析条目
                item = line.strip()
                if item and current_block:
                    # 移除 "- " 前缀（如果有）
                    if item.startswith("- "):
                        item = item[2:]
                    current_block.items.append(item)

        # 保存最后一个块
        if current_block and current_block.items:
            blocks.append(current_block)

        return blocks

    # ==================== 标题匹配 ====================

    def find_matching_section(
        self,
        content: str,
        existing_blocks: List[MemoryBlock]
    ) -> Tuple[Optional[str], float]:
        """
        找到内容最匹配的标题

        Args:
            content: 新内容
            existing_blocks: 现有块列表

        Returns:
            (标题, 相似度分数) 或 (None, 0.0) 表示无匹配
        """
        if not self.embedding_provider:
            return self._keyword_match(content, existing_blocks)

        # 计算内容的语义向量
        try:
            content_embedding = self.embedding_provider.embed(content)
        except Exception:
            return self._keyword_match(content, existing_blocks)

        best_match = None
        best_score = 0.0

        # 1. 先匹配预定义标题
        for title, embedding in self._title_embeddings.items():
            score = self._cosine_similarity(content_embedding, embedding)
            if score > best_score:
                best_score = score
                best_match = title

        # 2. 再匹配现有文件中的标题
        for block in existing_blocks:
            if not block.items:
                continue

            # 用块内所有条目的平均语义作为块的语义
            block_text = " ".join(block.items)
            try:
                block_embedding = self.embedding_provider.embed(block_text)
                score = self._cosine_similarity(content_embedding, block_embedding)
                if score > best_score:
                    best_score = score
                    best_match = block.title
            except Exception:
                pass

        if best_score >= TITLE_MATCH_THRESHOLD:
            return best_match, best_score

        return None, best_score

    def _keyword_match(
        self,
        content: str,
        existing_blocks: List[MemoryBlock]
    ) -> Tuple[Optional[str], float]:
        """关键词匹配（无 embedding 时的回退）"""
        content_lower = content.lower()

        # 关键词映射
        keyword_map = {
            "基本信息": ["姓名", "名字", "职业", "工作", "身份", "老师", "教师", "学生", "工程师"],
            "偏好": ["喜欢", "不喜欢", "爱吃", "不吃", "爱好", "习惯"],
            "待办": ["明天", "下周", "计划", "要", "需要", "待办"],
            "项目": ["项目", "开发", "代码", "系统", "功能"],
            "关系": ["家人", "朋友", "同事", "同学", "妻子", "丈夫"],
            "地点": ["住", "地址", "去", "在", "地点"],
        }

        for title, keywords in keyword_map.items():
            for kw in keywords:
                if kw in content_lower:
                    return title, 0.5

        return None, 0.0

    # ==================== 语义去重 ====================

    def deduplicate_items(
        self,
        existing_items: List[str],
        new_item: str
    ) -> Tuple[List[str], bool]:
        """
        语义去重

        Args:
            existing_items: 现有条目
            new_item: 新条目

        Returns:
            (合并后的条目列表, 是否添加了新内容)
        """
        if not existing_items:
            return [new_item], True

        if not self.embedding_provider:
            # Hash 去重
            new_hash = hashlib.md5(new_item.encode()).hexdigest()
            existing_hashes = {hashlib.md5(i.encode()).hexdigest() for i in existing_items}
            if new_hash in existing_hashes:
                return existing_items, False
            return existing_items + [new_item], True

        # 计算新条目的向量
        try:
            new_embedding = self.embedding_provider.embed(new_item)
        except Exception:
            return existing_items + [new_item], True

        # 检查是否与现有条目相似
        for i, existing in enumerate(existing_items):
            try:
                existing_embedding = self.embedding_provider.embed(existing)
                similarity = self._cosine_similarity(new_embedding, existing_embedding)

                if similarity >= DEDUP_SIMILARITY_THRESHOLD:
                    # 高度相似，检查是否需要更新（新条目可能更完整）
                    if len(new_item) > len(existing):
                        # 新条目更详细，替换
                        updated = list(existing_items)
                        updated[i] = new_item
                        return updated, True
                    # 现有条目足够好，跳过
                    return existing_items, False
            except Exception:
                pass

        # 不相似，添加新条目
        return existing_items + [new_item], True

    # ==================== 写入组织 ====================

    def organize_and_write(
        self,
        file_path: Path,
        new_items: List[str],
        header: str = None
    ) -> bool:
        """
        组织并写入记忆

        Args:
            file_path: 目标文件
            new_items: 新条目列表
            header: 文件头部（如 "# Daily Memory: 2026-04-23"）

        Returns:
            是否成功写入
        """
        # 1. 解析现有内容
        existing_blocks = self.parse_file(file_path)

        # 2. 为每个新条目找到目标块
        block_map = {b.title: b for b in existing_blocks}
        added_count = 0

        for new_item in new_items:
            # 找匹配的标题
            matched_title, score = self.find_matching_section(new_item, existing_blocks)

            if matched_title:
                # 找到匹配的块
                if matched_title in block_map:
                    block = block_map[matched_title]
                    new_items_list, added = self.deduplicate_items(block.items, new_item)
                    if added:
                        block.items = new_items_list
                        added_count += 1
                else:
                    # 标题存在于预定义但文件中还没有，创建新块
                    new_block = MemoryBlock(title=matched_title, level=2, items=[new_item])
                    block_map[matched_title] = new_block
                    existing_blocks.append(new_block)
                    added_count += 1
            else:
                # 无匹配，尝试从内容推断标题
                inferred_title = self._infer_title(new_item)
                if inferred_title in block_map:
                    block = block_map[inferred_title]
                    new_items_list, added = self.deduplicate_items(block.items, new_item)
                    if added:
                        block.items = new_items_list
                        added_count += 1
                else:
                    # 创建新块
                    new_block = MemoryBlock(title=inferred_title, level=2, items=[new_item])
                    block_map[inferred_title] = new_block
                    existing_blocks.append(new_block)
                    added_count += 1

        if added_count == 0:
            return False

        # 3. 按预定义顺序排序块
        sorted_blocks = self._sort_blocks(existing_blocks)

        # 4. 写入文件
        self._write_file(file_path, sorted_blocks, header)
        return True

    def _infer_title(self, content: str) -> str:
        """从内容推断标题"""
        # 简单规则推断
        if any(kw in content for kw in ["姓名", "名字", "是", "职业", "老师", "工程师"]):
            return "基本信息"
        if any(kw in content for kw in ["喜欢", "不喜欢", "爱吃", "不吃"]):
            return "偏好"
        if any(kw in content for kw in ["明天", "下周", "计划", "要", "需要"]):
            return "待办"
        if any(kw in content for kw in ["项目", "开发", "代码", "系统"]):
            return "项目"

        # 默认归类为"其他"
        return "其他"

    def _sort_blocks(self, blocks: List[MemoryBlock]) -> List[MemoryBlock]:
        """按预定义顺序排序块"""
        # 预定义顺序
        order = list(self.predefined_sections.keys()) + ["其他"]

        def get_order(block: MemoryBlock) -> int:
            if block.title in order:
                return order.index(block.title)
            return len(order)  # 未预定义的放最后

        return sorted(blocks, key=get_order)

    def _write_file(
        self,
        file_path: Path,
        blocks: List[MemoryBlock],
        header: str = None
    ):
        """写入文件"""
        file_path.parent.mkdir(parents=True, exist_ok=True)

        lines = []

        # 文件头
        if header:
            lines.append(header)
            lines.append("")
        else:
            today = datetime.now().strftime("%Y-%m-%d")
            lines.append(f"# Daily Memory: {today}")
            lines.append("")

        # 各块内容
        for i, block in enumerate(blocks):
            if i > 0:
                lines.append("")  # 块间空行
            lines.append(block.title_line)
            for item in block.items:
                if not item.startswith("-"):
                    item = f"- {item}"
                lines.append(item)

        file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ==================== 工具方法 ====================

    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """余弦相似度"""
        if len(vec1) != len(vec2):
            return 0.0

        dot = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot / (norm1 * norm2)
