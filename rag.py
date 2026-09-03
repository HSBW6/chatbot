#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HSBW6
"""简单 RAG：本地向量化 + 余弦相似度检索知识库。

三段式：
1) 切块：复用 kb_search.py 的切块逻辑，把 kb/**/*.md 切成小块
2) 向量化：用本地模型 BGE-small-zh-v1.5 把每块文字转成 512 维向量
3) 检索：把用户问题也转成向量，和所有块算余弦相似度，取最像的 Top-K
"""
# ========== 环境准备 ==========
# 用处：模型若需联网下载/校验时走国内镜像。HF_HUB_DISABLE_XET=1 是
# 强制关掉新版 HuggingFace 的 Xet 加速协议（国内不通、会 401 报错）。
# 模型已缓存到本地后这两行几乎不影响速度。
import os
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

import pickle
from pathlib import Path

# 用处：numpy 负责向量运算（算相似度）；fastembed 负责加载本地向量模型。
# TextEmbedding 是 fastembed 的入口类，embed() 输入文字、输出向量。
import numpy as np
from fastembed import TextEmbedding

# 用处：直接复用 kb_search.py 里现成的切块函数，不重复造轮子。
# _load_chunks() 返回 [{path, title, text}]；_cache_key() 返回语料指纹。
from kb_search import _cache_key, _load_chunks

# ========== 配置区 ==========
MODEL_NAME = "BAAI/bge-small-zh-v1.5"   # 用处：中文向量模型名，输出 512 维向量
# 用处：向量缓存文件放 kb/ 下。kb/ 已被 gitignore，缓存不会误提交。
CACHE_FILE = Path(__file__).resolve().parent / "kb" / "_rag_cache.pkl"
# 用处：向量模型缓存目录（修复 P1-1）。不指定时 fastembed 默认存到
# 系统临时目录 %TEMP%\fastembed_cache，被磁盘清理/清临时文件就没了，
# 重下要走慢速网络卡几十分钟。放 kb/ 下既稳定又不会被 git 误提交。
MODEL_DIR = Path(__file__).resolve().parent / "kb" / "_models"
# 用处：切块规则版本。以后改过切块/向量化逻辑就 +1，旧缓存自动作废重建。
SPLIT_VERSION = 1
# 用处：相似度阈值（余弦）。低于它的结果视为"知识库没相关内容"。
SIM_THRESHOLD = 0.55
# 用处：进程内缓存，避免同一次运行里二次查询重复向量化。
_mem_cache = {"fp": None, "chunks": None, "vectors": None}
_model = None


def get_model():
    """用处：模型单例。模型加载要几百毫秒，只加载一次，别每次检索都重读。"""
    global _model
    if _model is None:
        _model = TextEmbedding(model_name=MODEL_NAME, cache_dir=str(MODEL_DIR))
    return _model


def load_vectors():
    """用处：返回 (指纹, 块列表, 单位向量矩阵)。语料没变就吃缓存，变了重新向量化。

    指纹 = 文件指纹 + 切块版本 + 模型名。文件指纹是 kb 里所有 md 的
    (路径+修改时间+大小)；掺入切块版本和模型名后，改切块规则或换模型时
    旧缓存自动作废，绝不静默复用。
    """
    key = _cache_key()
    if key is None or not key:      # 用处：修复 P2-3。不仅拦"知识库不存在"，
        return None, [], None       # 也拦"目录在但一个 md 都没有"的空元组情况

    # 用处：拼完整指纹。key 只表示"文件变没变"，这里再加"逻辑变没变"。
    fp = (key, SPLIT_VERSION, MODEL_NAME)

    if _mem_cache["fp"] == fp:      # 用处：内存缓存命中，同进程二次查询不再读盘
        return _mem_cache["fp"], _mem_cache["chunks"], _mem_cache["vectors"]

    if CACHE_FILE.exists():         # 没命中内存，再看磁盘缓存
        try:
            with open(CACHE_FILE, "rb") as f:
                data = pickle.load(f)
            if data["fingerprint"] == fp:   # 指纹一致才复用
                vecs = np.array(data["vectors"], dtype=np.float32)
                _mem_cache.update(fp=fp, chunks=data["chunks"], vectors=vecs)
                return fp, data["chunks"], vecs
        except Exception:           # 缓存损坏/版本不对就忽略，走重建
            pass

    chunks = _load_chunks()         # 没缓存或过期：重新切块
    if not chunks:                  # 用处：切出来是空的也直接退出，别喂给 embed()
        return fp, [], None
    texts = [c["text"] for c in chunks]
    print("正在向量化 %d 个知识块..." % len(chunks), flush=True)
    raw = np.array(list(get_model().embed(texts)), dtype=np.float32)
    # 用处：向量归一化成单位长度（只保留方向）。余弦相似度只关心方向，
    # 单位化后点积就等于余弦相似度，省掉每次查询都算一遍向量长度。
    norms = np.linalg.norm(raw, axis=1, keepdims=True) + 1e-9
    vecs = raw / norms
    with open(CACHE_FILE, "wb") as f:   # 写磁盘缓存，下次秒开
        pickle.dump({"fingerprint": fp, "chunks": chunks,
                     "vectors": vecs.tolist()}, f)
    _mem_cache.update(fp=fp, chunks=chunks, vectors=vecs)  # 同步进内存缓存
    return fp, chunks, vecs



def search_similar(query, top_k=3):
    """用处：核心检索。问题转向量后与所有块算余弦相似度，返回最像的 Top-K。

    向量在 load_vectors 里已归一化，这里问题向量也归一化后直接点积就是余弦。
    低于 SIM_THRESHOLD 的结果会被丢弃（修复 P1-2）：知识库没相关内容时返回
    空列表，上层可以说"不知道"，而不是硬凑一段最像的废话。
    """
    _, chunks, vectors = load_vectors()
    if vectors is None or len(vectors) == 0:
        return []
    qv = np.array(list(get_model().embed([query])), dtype=np.float32)[0]
    qn = np.linalg.norm(qv) + 1e-9              # 问题向量长度（+1e-9 防除零）
    sims = vectors @ (qv / qn)                  # 单位向量点积 = 余弦相似度
    idx = np.argsort(sims)[::-1][:top_k]        # 从大到小排，取前 top_k 个下标
    out = []
    for i in idx:                               # 只留相似度达标的
        if sims[i] < SIM_THRESHOLD:
            break                               # 后面只会更小，直接停
        out.append((chunks[i], float(sims[i])))
    return out



if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "ROS2 怎么创建一个发布节点"
    results = search_similar(q)
    if not results:
        print("  知识库里没找到相关内容（都低于阈值 %.2f）" % SIM_THRESHOLD)
    for chunk, score in results:
        print(f"  相似度 {score:.3f} | {chunk['path']}")
        print("  " + chunk["text"][:120].replace("\n", " "))


    
