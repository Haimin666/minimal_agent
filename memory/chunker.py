"""文本分块 - 支持 Markdown 标题分块"""

from dataclasses import dataclass
from typing import List
import re


@dataclass
class TextChunk:
    """文本块"""
    text: str
    start_line: int
    end_line: int
    title: str = ""  # 所属标题


class TextChunker:
    """
    文本分块器

    支持两种模式：
    1. Markdown 标题分块（推荐）- 按标题切分，保持语义完整
    2. 字符数分块（回退）- 当无标题或段落过长时使用
    """

    def __init__(self, max_tokens: int = 500, overlap_tokens: int = 50):
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.chars_per_token = 4

    def chunk_text(self, text: str) -> List[TextChunk]:
        """
        将文本分块

        优先按 Markdown 标题分块，保持语义完整性
        """
        if not text.strip():
            return []

        lines = text.split('\n')

        # 检测是否有 Markdown 标题
        has_headers = any(line.strip().startswith('#') for line in lines)

        if has_headers:
            return self._chunk_by_headers(lines)
        else:
            return self._chunk_by_chars(lines)

    def _chunk_by_headers(self, lines: List[str]) -> List[TextChunk]:
        """按 Markdown 标题分块"""
        chunks = []
        current_section = []
        current_title = ""
        start_line = 1

        for i, line in enumerate(lines, start=1):
            # 检测标题（#, ##, ### 等）
            header_match = re.match(r'^(#{1,6})\s+(.+)$', line.strip())

            if header_match:
                # 保存上一个 section
                if current_section:
                    section_text = '\n'.join(current_section)
                    # 如果段落太长，需要拆分
                    if len(section_text) > self.max_tokens * self.chars_per_token:
                        sub_chunks = self._split_long_section(
                            current_section, start_line, current_title
                        )
                        chunks.extend(sub_chunks)
                    else:
                        chunks.append(TextChunk(
                            text=section_text,
                            start_line=start_line,
                            end_line=i - 1,
                            title=current_title
                        ))

                # 开始新 section
                current_section = [line]
                current_title = header_match.group(2).strip()
                start_line = i
            else:
                current_section.append(line)

        # 最后一个 section
        if current_section:
            section_text = '\n'.join(current_section)
            if len(section_text) > self.max_tokens * self.chars_per_token:
                sub_chunks = self._split_long_section(
                    current_section, start_line, current_title
                )
                chunks.extend(sub_chunks)
            else:
                chunks.append(TextChunk(
                    text=section_text,
                    start_line=start_line,
                    end_line=len(lines),
                    title=current_title
                ))

        return chunks

    def _split_long_section(
        self,
        lines: List[str],
        start_line: int,
        title: str
    ) -> List[TextChunk]:
        """拆分过长的 section"""
        chunks = []
        max_chars = self.max_tokens * self.chars_per_token

        current_chunk = []
        current_chars = 0
        chunk_start = start_line

        for i, line in enumerate(lines):
            line_chars = len(line)

            if current_chars + line_chars > max_chars and current_chunk:
                chunks.append(TextChunk(
                    text='\n'.join(current_chunk),
                    start_line=chunk_start,
                    end_line=start_line + i - 1,
                    title=title
                ))
                current_chunk = [line]
                current_chars = line_chars
                chunk_start = start_line + i
            else:
                current_chunk.append(line)
                current_chars += line_chars

        if current_chunk:
            chunks.append(TextChunk(
                text='\n'.join(current_chunk),
                start_line=chunk_start,
                end_line=start_line + len(lines) - 1,
                title=title
            ))

        return chunks

    def _chunk_by_chars(self, lines: List[str]) -> List[TextChunk]:
        """按字符数分块（无标题时的回退方案）"""
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

                for sub in self._split_long_line(line, max_chars):
                    chunks.append(TextChunk(text=sub, start_line=i, end_line=i))
                start_line = i + 1
                continue

            # 添加到当前块
            if current_chars + line_chars > max_chars and current_chunk:
                chunks.append(TextChunk(
                    text='\n'.join(current_chunk),
                    start_line=start_line,
                    end_line=i - 1
                ))

                overlap_lines = self._get_overlap_lines(current_chunk, overlap_chars)
                current_chunk = overlap_lines + [line]
                current_chars = sum(len(l) for l in current_chunk)
                start_line = i - len(overlap_lines)
            else:
                current_chunk.append(line)
                current_chars += line_chars

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
