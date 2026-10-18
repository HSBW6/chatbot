# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HSBW6
"""react_agent.py 的单元测试：注入假 chat_fn，不联网、不花额度。

覆盖：计划解析 / 工具调用 / 未知工具 / 重规划 / 解析失败兜底 / 工具轮数上限。
运行：python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import react_agent as ra


def _reply(content="", tool_calls=None):
    return {"content": content, "tool_calls": tool_calls or []}


def _tool(cid, name, arguments="{}"):
    return {"id": cid, "name": name, "arguments": arguments}


class FakeChat:
    """按脚本顺序返回预设响应；脚本用完就报错，防止测试悄悄漏掉调用。"""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def __call__(self, messages, tools=None):
        self.calls.append({"messages": messages, "tools": tools})
        if not self.script:
            raise AssertionError("FakeChat 脚本已用完：调用次数比预期多")
        return self.script.pop(0)


class FakeTools:
    def __init__(self):
        self.calls = []

    def calculate(self, expression):
        self.calls.append(expression)
        return "1024"

    def as_map(self):
        return {"calculate": self.calculate}


class TestPlanParsing(unittest.TestCase):
    def test_plan_json_with_fence(self):
        fake = FakeChat([_reply("```json\n{\"steps\": [{\"goal\": \"算一下\"}]}\n```")])
        agent = ra.ReActAgent(chat_fn=fake)
        steps = agent.plan("算 2**10")
        self.assertEqual(steps, [{"goal": "算一下", "hint": ""}])

    def test_plan_invalid_json_falls_back_to_single_step(self):
        fake = FakeChat([_reply("我先想想，可能要先查资料")])
        agent = ra.ReActAgent(chat_fn=fake)
        steps = agent.plan("查资料")
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["goal"], "查资料")

    def test_extract_json_returns_none_for_garbage(self):
        self.assertIsNone(ra._extract_json("完全没有 JSON"))
        self.assertIsNone(ra._extract_json(""))

    def test_as_steps_accepts_plain_string_items(self):
        steps = ra._as_steps({"steps": ["第一步", {"goal": "第二步"}]}, "兜底")
        self.assertEqual([s["goal"] for s in steps], ["第一步", "第二步"])


class TestRun(unittest.TestCase):
    def test_full_flow_with_tool_call(self):
        tools = FakeTools()
        fake = FakeChat([
            _reply('{"steps": [{"goal": "计算 2**10"}]}'),
            _reply("", [_tool("c1", "calculate", '{"expression": "2**10"}')]),
            _reply("结果是 1024"),
            _reply('{"decision": "done", "reason": "完成"}'),
            _reply("最终答案：1024"),
        ])
        agent = ra.ReActAgent(chat_fn=fake, tool_map=tools.as_map())
        answer = agent.run("算 2**10")
        self.assertEqual(answer, "最终答案：1024")
        self.assertEqual(tools.calls, ["2**10"])
        self.assertEqual(agent.observations, ["结果是 1024"])
        self.assertEqual(agent.last_tool_calls, ["calculate"])

    def test_unknown_tool_is_reported_not_crashed(self):
        fake = FakeChat([
            _reply('{"steps": [{"goal": "用不存在的工具"}]}'),
            _reply("", [_tool("c1", "nope")]),
            _reply("工具不可用"),
            _reply('{"decision": "done"}'),
            _reply("最终答复"),
        ])
        agent = ra.ReActAgent(chat_fn=fake, tool_map={})
        answer = agent.run("试试")
        self.assertEqual(answer, "最终答复")
        # 工具错误应作为 tool 消息回喂给模型，而不是被吞掉
        tool_msgs = [m for m in fake.calls[2]["messages"] if m.get("role") == "tool"]
        self.assertTrue(tool_msgs)
        self.assertIn("未知工具", tool_msgs[-1]["content"])

    def test_replan_replaces_remaining_steps(self):
        fake = FakeChat([
            _reply('{"steps": [{"goal": "A"}, {"goal": "B"}]}'),
            _reply("A 完成"),
            _reply('{"decision": "replan"}'),
            _reply('{"steps": [{"goal": "新步骤"}]}'),
            _reply("新步骤完成"),
            _reply('{"decision": "done"}'),
            _reply("最终答复"),
        ])
        agent = ra.ReActAgent(chat_fn=fake)
        answer = agent.run("做点什么")
        self.assertEqual(answer, "最终答复")
        self.assertEqual(agent.replans, 1)
        self.assertEqual(len(agent.steps), 2)  # 已完成的 A + 重规划的新步骤
        self.assertEqual(agent.observations, ["A 完成", "新步骤完成"])

    def test_tool_round_limit_returns_notice(self):
        fake = FakeChat([
            _reply('{"steps": [{"goal": "一直调工具"}]}'),
            _reply("", [_tool("c1", "calculate", '{"expression": "1"}')]),
            _reply("", [_tool("c2", "calculate", '{"expression": "2"}')]),
            _reply('{"decision": "done"}'),
            _reply("收尾"),
        ])
        tools = FakeTools()
        agent = ra.ReActAgent(chat_fn=fake, tool_map=tools.as_map(), max_tool_rounds=2)
        agent.run("循环")
        self.assertIn("2 次工具", agent.observations[0])

    def test_empty_task(self):
        agent = ra.ReActAgent(chat_fn=FakeChat([]))
        self.assertEqual(agent.run("   "), "任务为空")


if __name__ == "__main__":
    unittest.main()
