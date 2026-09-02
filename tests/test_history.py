# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HSBW6
"""chatbot.py 历史裁剪与工具调用配对清理的单元测试。

背景：06148b1 引入字符预算裁剪后，逐条 pop 可能拆散
assistant(tool_calls) -> tool 的配对结构，孤儿 tool 消息会导致
DeepSeek API 返回 400。本文件覆盖 trim_history 与
_cleanup_message_pairs 的配对不变量，防止回归。

运行方式（在项目根目录 D:\\Deepseek\\chatbot 下）：
    python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

# 让测试能 import 到项目根目录的模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chatbot


def round_msgs(round_id, tool_len=4500, text_len=100):
    """构造一轮带 kb_search 工具调用的 4 条消息（一轮=1 次调用）。"""
    cid = f"call_{round_id}"
    return [
        {"role": "user", "content": f"第{round_id}轮问题"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": cid, "type": "function",
             "function": {"name": "kb_search", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": cid, "content": "结果" + "y" * tool_len},
        {"role": "assistant", "content": "回答" + "z" * text_len},
    ]


def base_history(n_rounds):
    msgs = [{"role": "system", "content": "sys"}]
    for i in range(1, n_rounds + 1):
        msgs.extend(round_msgs(i))
    return msgs


def pairing_errors(messages):
    """返回违反 API 配对规则的位置列表；空列表表示合法。"""
    errors = []
    pending, responded = set(), set()
    for i, m in enumerate(messages):
        if m["role"] == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                pending.add(tc["id"])
        elif m["role"] == "tool":
            cid = m.get("tool_call_id")
            if cid not in pending:
                errors.append(f"孤儿tool@{i}:{cid}")
            else:
                pending.discard(cid)
                responded.add(cid)
        elif m["role"] == "user":
            pending.clear()
    for i, m in enumerate(messages):
        if m["role"] == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                if tc["id"] not in responded:
                    errors.append(f"无响应call@{i}:{tc['id']}")
    return errors


class TestCleanupMessagePairs(unittest.TestCase):
    """_cleanup_message_pairs 的定向用例。"""

    def test_orphan_tool_removed(self):
        """没有配对声明的孤儿 tool 消息应被删除。"""
        msgs = [{"role": "system", "content": "s"},
                {"role": "tool", "tool_call_id": "call_9", "content": "孤儿"},
                {"role": "user", "content": "hi"}]
        out = chatbot._cleanup_message_pairs(msgs)
        self.assertEqual([m["role"] for m in out], ["system", "user"])

    def test_call_without_response_removed(self):
        """tool 响应已被裁掉的 call 应从 tool_calls 中移除。"""
        msgs = [{"role": "system", "content": "s"},
                {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "c1", "type": "function",
                     "function": {"name": "kb_search", "arguments": "{}"}},
                    {"id": "c2", "type": "function",
                     "function": {"name": "kb_search", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "c2", "content": "有响应"},
                {"role": "user", "content": "hi"}]
        out = chatbot._cleanup_message_pairs(msgs)
        assistant = next(m for m in out if m["role"] == "assistant")
        self.assertEqual([tc["id"] for tc in assistant["tool_calls"]], ["c2"])

    def test_empty_assistant_removed(self):
        """既无 content 也无 tool_calls 的 assistant 应整条移除。"""
        msgs = [{"role": "system", "content": "s"},
                {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "c1", "type": "function",
                     "function": {"name": "kb_search", "arguments": "{}"}}]},
                {"role": "user", "content": "hi"}]
        out = chatbot._cleanup_message_pairs(msgs)
        self.assertEqual([m["role"] for m in out], ["system", "user"])

    def test_intact_pair_kept(self):
        """完整配对应原样保留，不误删。"""
        msgs = base_history(1)
        out = chatbot._cleanup_message_pairs(msgs)
        self.assertEqual(out, msgs)

    def test_user_resets_pending(self):
        """user 消息之后迟到的 tool 响应视为孤儿。"""
        msgs = [{"role": "system", "content": "s"},
                {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "c1", "type": "function",
                     "function": {"name": "kb_search", "arguments": "{}"}}]},
                {"role": "user", "content": "新问题"},
                {"role": "tool", "tool_call_id": "c1", "content": "迟到响应"}]
        out = chatbot._cleanup_message_pairs(msgs)
        # 迟到的 tool 被丢弃；assistant 声明作废后成空壳，也一并移除
        self.assertEqual([m["role"] for m in out], ["system", "user"])


class TestTrimHistory(unittest.TestCase):
    """trim_history 的字符预算与配对不变量。"""

    def setUp(self):
        # 默认预算 30000 太大，测试统一调小到 6000，方便少量轮次触发裁剪
        self.budget_patcher = mock.patch.object(chatbot, "MAX_CONTEXT_CHARS", 6000)
        self.budget_patcher.start()
        self.addCleanup(self.budget_patcher.stop)

    def test_within_budget_untouched(self):
        """预算内不裁剪，消息原样返回。"""
        msgs = base_history(1)
        out = chatbot.trim_history([dict(m) for m in msgs])
        self.assertEqual(out, msgs)

    def test_trim_drops_oldest_keeps_pairing(self):
        """超预算时从最旧裁剪，且工具配对始终完好。"""
        msgs = base_history(3)
        out = chatbot.trim_history([dict(m) for m in msgs])
        # 确实发生了裁剪
        self.assertLess(len(out), len(msgs))
        # system 仍保留在首位
        self.assertEqual(out[0]["role"], "system")
        # 配对不变量：无孤儿 tool、无无响应 call
        self.assertEqual(pairing_errors(out), [])

    def test_multi_call_round_pairing(self):
        """一轮多次工具调用（6 条结构）裁剪后配对仍完好。"""
        msgs = [{"role": "system", "content": "sys"}]
        for r in range(1, 4):
            c1, c2 = f"call_{r}_1", f"call_{r}_2"
            msgs += [
                {"role": "user", "content": f"第{r}轮"},
                {"role": "assistant", "content": None, "tool_calls": [
                    {"id": c1, "type": "function",
                     "function": {"name": "kb_search", "arguments": "{}"}},
                    {"id": c2, "type": "function",
                     "function": {"name": "kb_search", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": c1, "content": "y" * 4500},
                {"role": "tool", "tool_call_id": c2, "content": "y" * 4500},
                {"role": "assistant", "content": "z" * 100},
            ]
        out = chatbot.trim_history([dict(m) for m in msgs])
        self.assertEqual(pairing_errors(out), [])
        # 裁剪后 assistant 里声明的 call 不应有多余未响应项
        for m in out:
            if m["role"] == "assistant" and m.get("tool_calls"):
                self.assertTrue(m["tool_calls"], "空 tool_calls 不应出现")

    def test_keep_system_and_last_message(self):
        """裁剪后至少保留 system 与最后一条消息。"""
        msgs = base_history(3)
        out = chatbot.trim_history([dict(m) for m in msgs])
        self.assertGreaterEqual(len(out), 2)
        self.assertEqual(out[0], msgs[0])
        self.assertEqual(out[-1], msgs[-1])


if __name__ == "__main__":
    unittest.main()
