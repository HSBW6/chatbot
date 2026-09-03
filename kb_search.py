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
_MIN_SCORE = 3  # 关键词命中最低分；低于它视为噪声命中，交给语义兜底裁决


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


def _format_output(query, hits, top_k, max_chars, max_total, semantic=False):
    """用处：把命中的 [(分数, chunk)] 列表统一排版成可读文字。
    semantic=True 表示这批命中来自语义检索，分数是 0~1 的相似度；
    否则来自关键词检索，分数是词频整数。两种来源共用同一套排版，
    上层（模型/tools）看到的格式完全一致，这就是"对外零改动"的关键。"""
    out = [f"知识库检索到 {len(hits)} 个相关片段（关键词: {query}）：", ""]
    total = 0                                  # 累计已输出的字数
    for i, (s, c) in enumerate(hits[:top_k], 1):
        budget = max_total - total - 200       # 预留后续片段头部空间
        if budget <= 0:                        # 预算耗尽就停
            break
        text = c["text"][:min(max_chars, budget)]
        score = f"{s:.2f}" if semantic else str(s)   # 语义分保留2位小数，关键词分原样
        label = "语义匹配" if semantic else "相关度"  # 来源标签，方便日后排查
        out.append(f"【片段{i}】来源: {c['path']}（{label} {score}）")
        out.append(text)
        out.append("")
        total += len(text)
    return "\n".join(out)



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



    hits = [(s, c) for s, c in scored if s >= _MIN_SCORE][:top_k]
    if hits:
        # 用处：快路径——关键词有命中就直接返回，毫秒级，完全不碰语义模型
        return _format_output(query, hits, top_k, max_chars, max_total, semantic=False)

    # ===== 语义兜底：只有关键词零命中才走到这 =====
    # 用处：延迟 import。rag.py 顶部依赖 numpy/fastembed，而且 rag 顶部又
    # 反向 import 了 kb_search——如果 kb_search 顶层也 import rag，两个文件
    # 互相引用会循环导入直接崩。放函数内，快路径永远零额外依赖；
    # 只有真正需要兜底时才加载模型。rag 装不上/坏了就静默降级回原来的
    # "未找到"话术，绝不让主链路因为这个保险丝报错。
    try:
        from rag import search_similar
    except Exception:
        return f"知识库中未找到与「{query}」相关的内容，请换个说法试试"
    sem_hits = search_similar(query, top_k=top_k)   # 内部已过滤 <0.55 的块
    if not sem_hits:
        # 用处：语义也没找到达标的——保持原来的"未找到"话术，行为不变
        return f"知识库中未找到与「{query}」相关的内容，请换个说法试试"
    # 用处：sem_hits 是 [(chunk, 相似度)]，翻成 (分数, chunk) 统一结构去排版
    return _format_output(query, [(s, c) for c, s in sem_hits],
                          top_k, max_chars, max_total, semantic=True)



if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "话题"
    print(kb_search(q))
