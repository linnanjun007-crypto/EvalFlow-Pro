"""ChunkingService — 把文档原始文本切成可索引的 chunk。

对每种文件类型采用不同策略：
- md / docx：按标题层级切分，章节路径前缀注入到 chunk 内容
- pdf：按段落（空行）切分，超长段交给滑窗
- txt：句子滑窗
- xlsx / csv：按行打包

每个 chunk 在内容头部带 "章节 > 子节" 前缀，metadata 写 heading_path，方便检索时定位。
"""

from __future__ import annotations

import re
from typing import Iterable

SENTENCE_DELIMITERS = re.compile(r"(?<=[。！？!?\n])")
PARAGRAPH_DELIMITERS = re.compile(r"\n\s*\n+")
MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
NUMERIC_HEADING_RE = re.compile(r"^[一二三四五六七八九十百千\d]+[、.．\s][^\n]{0,40}$")


def chunk_document(
    text: str,
    *,
    file_type: str,
    chunk_size: int = 500,
    chunk_overlap: int = 80,
) -> list[dict[str, object]]:
    """根据文件类型选择切分策略。返回 [{content, chunk_index, metadata}, ...]"""

    if not text or not text.strip():
        return []

    file_type = (file_type or "").lower().lstrip(".")

    # 自适应 chunk_size：短文本细切，长文本粗切
    total_len = len(text)
    if total_len < 2000:
        adaptive_size = min(chunk_size, 300)
    elif total_len > 10000:
        adaptive_size = max(chunk_size, 800)
    else:
        adaptive_size = chunk_size

    if file_type in {"xlsx", "xls", "csv"}:
        rows = [line.rstrip() for line in text.split("\n") if line.strip()]
        return _pack_rows(rows, chunk_size=adaptive_size)

    if file_type in {"md", "markdown", "docx"}:
        sections = _split_by_headings(text, file_type=file_type)
        return _build_chunks_from_sections(sections, adaptive_size, chunk_overlap)

    if file_type == "pdf":
        sections = _split_pdf_by_blocks(text)
        return _build_chunks_from_sections(sections, adaptive_size, chunk_overlap)

    # 默认：txt
    chunks = _sliding_window_by_sentence(text, adaptive_size, chunk_overlap)
    return _wrap_chunks([(c, []) for c in chunks])


def _build_chunks_from_sections(
    sections: list[tuple[list[str], str]],
    chunk_size: int,
    chunk_overlap: int,
) -> list[dict[str, object]]:
    """把 (heading_path, section_text) 序列展开成带前缀的 chunk 列表。"""
    out: list[tuple[str, list[str]]] = []
    for heading_path, section_text in sections:
        if not section_text.strip():
            continue
        if len(section_text) <= chunk_size:
            out.append((section_text.strip(), heading_path))
        else:
            for piece in _sliding_window_by_sentence(section_text, chunk_size, chunk_overlap):
                out.append((piece, heading_path))
    return _wrap_chunks(out)


def _wrap_chunks(items: Iterable[tuple[str, list[str]]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    idx = 0
    for content, heading_path in items:
        cleaned = content.strip()
        if not cleaned:
            continue
        if heading_path:
            prefix = " > ".join(heading_path)
            final_content = f"{prefix}\n{cleaned}"
            metadata: dict[str, object] = {"heading_path": list(heading_path)}
        else:
            final_content = cleaned
            metadata = {}
        out.append({"content": final_content, "chunk_index": idx, "metadata": metadata})
        idx += 1
    return out


def _sliding_window_by_sentence(text: str, chunk_size: int, overlap: int) -> list[str]:
    sentences = [s for s in SENTENCE_DELIMITERS.split(text) if s.strip()]
    if not sentences:
        return []

    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for sentence in sentences:
        s_len = len(sentence)
        if buf_len + s_len > chunk_size and buf:
            chunks.append("".join(buf).strip())
            tail = "".join(buf)[-overlap:] if overlap > 0 else ""
            buf = [tail] if tail else []
            buf_len = len(tail)
        buf.append(sentence)
        buf_len += s_len
    if buf:
        chunks.append("".join(buf).strip())
    return [c for c in chunks if c]


def _split_by_headings(text: str, *, file_type: str) -> list[tuple[list[str], str]]:
    """按 md / docx 标题切分，返回 (heading_path, section_text) 序列。

    md 用 # 数量定层级；docx 解析后多以 "数字、xxx" 或纯标题行开头，按数字层级近似。
    """
    lines = text.split("\n")
    sections: list[tuple[list[str], str]] = []
    stack: list[tuple[int, str]] = []  # (level, title)
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        section_text = "\n".join(buf).strip()
        if not section_text:
            buf.clear()
            return
        path = [title for _, title in stack]
        sections.append((path, section_text))
        buf.clear()

    for line in lines:
        stripped = line.strip()
        level: int | None = None
        title: str | None = None

        m = MD_HEADING_RE.match(stripped)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
        elif file_type == "docx" and stripped and len(stripped) <= 40 and NUMERIC_HEADING_RE.match(stripped):
            level = _numeric_heading_level(stripped)
            title = stripped

        if level is not None and title:
            flush()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            continue

        buf.append(line)

    flush()

    if not sections:
        return [([], text)]
    return sections


def _numeric_heading_level(line: str) -> int:
    """从 "1.2.3 标题" 这类前缀粗略推层级。"""
    head = line.split(maxsplit=1)[0]
    dots = head.count(".") + head.count("．")
    return max(1, min(6, dots + 1))


def _split_pdf_by_blocks(text: str) -> list[tuple[list[str], str]]:
    """PDF 没有可靠的标题结构，按空行切大段；超长段在外层会再走滑窗。"""
    blocks = [b.strip() for b in PARAGRAPH_DELIMITERS.split(text) if b.strip()]
    if not blocks:
        return [([], text)]
    return [([], block) for block in blocks]


def _pack_rows(rows: list[str], *, chunk_size: int) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    buf: list[str] = []
    buf_len = 0
    chunk_index = 0
    for row in rows:
        if buf_len + len(row) > chunk_size and buf:
            out.append({"content": "\n".join(buf), "chunk_index": chunk_index, "metadata": {"rows": len(buf)}})
            chunk_index += 1
            buf = []
            buf_len = 0
        buf.append(row)
        buf_len += len(row) + 1
    if buf:
        out.append({"content": "\n".join(buf), "chunk_index": chunk_index, "metadata": {"rows": len(buf)}})
    return out
