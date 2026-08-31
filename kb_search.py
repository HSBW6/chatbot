#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识库轻量检索：在 kb/ 目录的 Markdown 文件上做关键词/词频检索。

方案 A（零外部依赖）：
- 把 kb/**/*.md 按标题层级切成块
- 查询分词：英文单词 + 中文 2-gram
- 打分：词频（标题命中加权），返回 Top-K 块
"""
import re
from pathlib import Path

KB_DIR = Path(__file__).resolve().parent / "kb"

_CJK = re.compile(r"[\u4e00-\u9fff]+")
_WORD = re.compile(r"[a-zA-Z0-9]+")


def _tokenize(text: str) -> list:
    """中文按 2-gram（滑动窗口）、英文数字按整词。"""
    tokens = []
    for m in _CJK.finditer(text):
        seg = m.group()
        tokens += [seg[i:i + 2] for i in range(max(0, len(seg) - 1))]
    tokens += _WORD.findall(text.lower())
    return tokens


def _load_chunks() -> list:
    """返回 [{path, title, text}]，按标题切块，块过大按空行再切。"""
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


def kb_search(query: str, top_k: int = 3, max_chars: int = 2000) -> str:
    """在知识库中检索与 query 相关的章节片段，返回可直接阅读的文本。

    Args:
        query: 检索关键词/问题（中英文均可）。
        top_k: 返回的片段数量。
        max_chars: 每个片段截断长度。
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
    for i, s in enumerate(scored[:top_k], 1):
        if s[0] <= 0:
            break
        c = s[1]
        text = c["text"][:max_chars]
        out.append(f"【片段{i}】来源: {c['path']}（相关度 {s[0]}）")
        out.append(text)
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "话题"
    print(kb_search(q))
