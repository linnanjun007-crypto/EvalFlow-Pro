"""中文分词工具 — 基于 jieba，用于 BM25 tsvector 写入与查询。"""

from __future__ import annotations

import jieba


def tokenize_zh(text: str) -> str:
    """将中文文本切词后用空格拼接，供 PostgreSQL to_tsvector('simple', ...) 使用。"""
    return " ".join(w for w in jieba.cut_for_search(text or "") if w.strip())
