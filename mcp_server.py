#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HSBW6
"""把 tools.py 的 7 个工具暴露成 MCP server（stdio 传输）。

MCP（Model Context Protocol）是 Agent 生态里事实上的工具接入标准：
Claude Desktop / Cursor 等客户端挂上本 server 就能直接调用这些工具。

版本适配：mcp 2.x 把原来的 FastMCP 改名为 MCPServer
（``mcp.server.mcpserver.MCPServer``），低层 ``Server.list_tools`` 装饰器也已移除。
这里用 ``MCPServer.add_tool``，schema 由 tools.py 的函数签名与 type hints 自动生成——
所以**函数签名就是对外协议**，改签名等于破坏客户端契约。

设计要点：
- 工具 description 复用 ``schema.TOOLS``，避免两处文案漂移；
- 工具实现直接复用 ``tools.TOOL_MAP``，不复制逻辑；
- stdio 传输下 **stdout 是协议通道**，任何 print 都会污染 JSON-RPC，调试一律写 stderr。

启动：
    python mcp_server.py

客户端配置（Claude Desktop / Cursor 的 mcpServers）：
    {
      "mcpServers": {
        "ros-assistant": {
          "command": "python",
          "args": ["D:/Deepseek/chatbot/mcp_server.py"]
        }
      }
    }
"""
import sys

from mcp.server.mcpserver import MCPServer

from schema import TOOLS
from tools import TOOL_MAP

SERVER_NAME = "ros-assistant"
SERVER_VERSION = "1.0.0"


def _descriptions():
    """从 schema.TOOLS 取每个工具的 description（单一来源）。"""
    out = {}
    for item in TOOLS:
        fn = item.get("function") or {}
        name = fn.get("name")
        if name:
            out[name] = fn.get("description", "")
    return out


def build_server():
    """构造并注册全部工具的 MCP server（不启动，便于单测）。"""
    server = MCPServer(SERVER_NAME, version=SERVER_VERSION)
    descriptions = _descriptions()
    for name, fn in TOOL_MAP.items():
        server.add_tool(
            fn,
            name=name,
            description=descriptions.get(name) or (fn.__doc__ or name),
        )
    return server


def dispatch(name, arguments):
    """同步执行一次工具调用（测试与非协议场景复用）。

    错误不抛到调用方：把异常转成可读文本，避免一次工具失败拖垮整个会话。
    """
    fn = TOOL_MAP.get(name)
    if fn is None:
        return "未知工具：%s（可用：%s）" % (name, ", ".join(sorted(TOOL_MAP)))
    args = arguments or {}
    if not isinstance(args, dict):
        return "工具参数必须是对象，实际收到：%r" % (type(args).__name__,)
    try:
        return str(fn(**args))
    except TypeError as exc:
        return "参数不匹配：%s" % exc
    except Exception as exc:
        return "工具执行出错：%s: %s" % (type(exc).__name__, exc)


def main():
    build_server().run(transport="stdio")


if __name__ == "__main__":
    # 注意：不要把日志打到 stdout（协议通道），需要调试请用 stderr
    print("MCP server 已启动（stdio）", file=sys.stderr)
    main()
