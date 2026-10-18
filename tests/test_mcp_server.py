# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HSBW6
"""mcp_server.py 的单元测试：不启动 stdio 会话，只验证工具注册与 dispatch。

运行：python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio

import mcp_server as ms
from tools import TOOL_MAP


class TestToolRegistration(unittest.TestCase):
    def setUp(self):
        self.server = ms.build_server()
        # MCPServer.list_tools 是协程，测试里用 asyncio.run 取一次
        self.tools = asyncio.run(self.server.list_tools())

    def test_tool_count_matches_registry(self):
        self.assertEqual(len(self.tools), len(TOOL_MAP))

    def test_tool_names_match_registry(self):
        self.assertEqual({t.name for t in self.tools}, set(TOOL_MAP))

    def test_every_tool_has_description(self):
        for tool in self.tools:
            self.assertTrue((tool.description or "").strip(),
                            "%s 缺少 description" % tool.name)


class TestDispatch(unittest.TestCase):
    def test_calculate_roundtrip(self):
        self.assertEqual(ms.dispatch("calculate", {"expression": "1+1"}), "2")

    def test_unknown_tool_returns_readable_error(self):
        out = ms.dispatch("no_such_tool", {})
        self.assertIn("未知工具", out)
        # 错误信息里要能看出有哪些可用工具，方便客户端自查
        self.assertIn("calculate", out)

    def test_non_dict_arguments(self):
        out = ms.dispatch("calculate", "not-a-dict")
        self.assertIn("参数必须是对象", out)

    def test_bad_argument_type_is_caught(self):
        # calculate 期望字符串，传 int 应在工具内部抛 TypeError，被兜底成可读文本
        out = ms.dispatch("calculate", {"expression": 123})
        self.assertIn("参数不匹配", out)


if __name__ == "__main__":
    unittest.main()
