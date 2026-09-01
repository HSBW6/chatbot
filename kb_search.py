#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HSBW6
"""知识库轻量检索：在 kb/ 目录的 Markdown 文件上做关键词/词频检索。

方案 A（零外部依赖）：
- 把 kb/**/*.md 按标题层级切成块
- 查询分词：英文单词 + 中文 2-gram
- 打分：词频（标题命中加权），返回 Top-K 块
"""
import re
from pathlib import Path

KB_DIR = Path(__file__).resolve().parent / "kb"
_MAX_TOTAL = 4500  # 单次检索返回的总字符上限，防止上下文膨胀

_CJK = re.compile(r"[\u4e00-\u9fff]+")
_WORD = re.compile(r"[a-zA-Z0-9]+")

# 模块级缓存：知识库文件未变化时，不重复扫描/解析
_cache = {"key": None, "chunks": None}


def _tokenize(text: str) -> list:
    """中文按 2-gram（滑动窗口）、英文数字按整词。"""
    tokens = []
    for m in _CJK.finditer(text):
        seg = m.group()
        tokens += [seg[i:i + 2] for i in range(max(0, len(seg) - 1))]
    tokens += _WORD.findall(text.lower())
    return tokens


def _cache_key():
    """以所有 md 文件的 (路径, mtime, 大小) 作为缓存键。"""
    if not KB_DIR.exists():
        return None
    key = []
    for f in sorted(KB_DIR.rglob("*.md")):
        if f.name == "INDEX.md":
            continue
        st = f.stat()
        key.append((str(f), st.st_mtime_ns, st.st_size))
    return tuple(key)


def _load_chunks() -> list:
    """返回 [{path, title, text}]，按标题切块，块过大按空行再切；带缓存。"""
    global _cache
    key = _cache_key()
    if key is None:
        return []
    if _cache["key"] == key:
        return _cache["chunks"]
    chunks = []
    for f in sorted(KB_DIR.rglob("*.md")):
        if f.name == "INDEX.md":
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        title = f.stem
        for block in _split_by_heading(content):
            text = block.strip()
            if len(text) < 20:
                continue
            chunks.append({"path": f.relative_to(KB_DIR).as_posix(),
                           "title": title, "text": text})
    _cache = {"key": key, "chunks": chunks}
    return chunks


def _split_by_heading(content: str) -> list:
    """按 ## / ### 标题切块；单块超过 6000 字符再按空行切。"""
    parts = re.split(r"\n(?=#{1,3} )", content)
    blocks = []
    for p in parts:
        if len(p) > 6000:
            blocks += [s for s in re.split(r"\n\s*\n", p) if len(s.strip()) >= 20]
        else:
            blocks.append(p)
    return blocks


def _score_chunk(query_tokens: list, chunk: dict) -> int:
    text = chunk["text"]
    title = chunk["title"]
    score = 0
    for tok in set(query_tokens):
        if not tok:
            continue
        cnt = text.lower().count(tok)
        if cnt:
            score += min(cnt, 20)          # 词频（封顶，防长文本刷分）
            if tok in title.lower():
                score += 30                # 标题命中加权
    return score


def kb_search(query: str, top_k: int = 3, max_chars: int = 2000,
              max_total: int = _MAX_TOTAL) -> str:
    """在知识库中检索与 query 相关的章节片段，返回可直接阅读的文本。

    Args:
        query: 检索关键词/问题（中英文均可）。
        top_k: 返回的片段数量。
        max_chars: 每个片段截断长度。
        max_total: 全部片段的总字符上限（防止结果撑爆上下文）。
    """
    if not KB_DIR.exists():
        return "知识库尚未构建：请先运行 build_kb.py 生成 kb/ 目录"
    query = (query or "").strip()
    if not query:
        return "检索关键词为空"
    tokens = _tokenize(query)
    if not tokens:
        return "未能从查询中提取关键词"

    chunks = _load_chunks()
    scored = sorted((( _score_chunk(tokens, c), c) for c in chunks),
                    key=lambda x: x[0], reverse=True)
    hits = [s for s, _ in scored if s > 0][:top_k]
    if not hits:
        return f"知识库中未找到与「{query}」相关的内容，请换个说法试试"

    out = [f"知识库检索到 {len(hits)} 个相关片段（关键词: {query}）：", ""]
    total = 0
    for i, s in enumerate(scored[:top_k], 1):
        if s[0] <= 0:
            break
        c = s[1]
        budget = max_total - total - 200  # 预留后续片段头部空间
        if budget <= 0:
            break
        text = c["text"][:min(max_chars, budget)]
        out.append(f"【片段{i}】来源: {c['path']}（相关度 {s[0]}）")
        out.append(text)
        out.append("")
        total += len(text)
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "话题"
    print(kb_search(q))
