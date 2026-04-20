"""文本分块 - 与 CowAgent 实现一致"""

from dataclasses import dataclass
from typing import List


@dataclass
class TextChunk:
    """文本块"""
    text: str
    start_line: int
    end_line: int


class TextChunker:
    """
    文本分块器

    CowAgent 实现:
    - max_tokens: 500
    - overlap_tokens: 50 (约 20% 重叠)
    - 按行分块，保持语义完整性
    """

    def __init__(self, max_tokens: int = 500, overlap_tokens: int = 50):
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        # 估算: 中英文混合约 4 字符 = 1 token
        self.chars_per_token = 4

    def chunk_text(self, text: str) -> List[TextChunk]:
        """将文本分块"""
        if not text.strip():
            return []

        lines = text.split('\n')
        chunks = []

        max_chars = self.max_tokens * self.chars_per_token
        overlap_chars = self.overlap_tokens * self.chars_per_token

        current_chunk = []
        current_chars = 0
        start_line = 1

        for i, line in enumerate(lines, start=1):
            line_chars = len(line)

            # 单行超长，强制分割
            if line_chars > max_chars:
                if current_chunk:
                    chunks.append(TextChunk(
                        text='\n'.join(current_chunk),
                        start_line=start_line,
                        end_line=i - 1
                    ))
                    current_chunk = []
                    current_chars = 0

                # 分割长行
                for sub in self._split_long_line(line, max_chars):
                    chunks.append(TextChunk(text=sub, start_line=i, end_line=i))
                start_line = i + 1
                continue

            # 添加到当前块
            if current_chars + line_chars > max_chars and current_chunk:
                # 保存当前块
                chunks.append(TextChunk(
                    text='\n'.join(current_chunk),
                    start_line=start_line,
                    end_line=i - 1
                ))

                # 新块带重叠
                overlap_lines = self._get_overlap_lines(current_chunk, overlap_chars)
                current_chunk = overlap_lines + [line]
                current_chars = sum(len(l) for l in current_chunk)
                start_line = i - len(overlap_lines)
            else:
                current_chunk.append(line)
                current_chars += line_chars

        # 最后一块
        if current_chunk:
            chunks.append(TextChunk(
                text='\n'.join(current_chunk),
                start_line=start_line,
                end_line=len(lines)
            ))

        return chunks

    def _split_long_line(self, line: str, max_chars: int) -> List[str]:
        """分割长行"""
        return [line[i:i + max_chars] for i in range(0, len(line), max_chars)]

    def _get_overlap_lines(self, lines: List[str], target_chars: int) -> List[str]:
        """获取重叠部分"""
        overlap = []
        chars = 0
        for line in reversed(lines):
            if chars + len(line) > target_chars:
                break
            overlap.insert(0, line)
            chars += len(line)
        return overlap
