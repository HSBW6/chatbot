# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HSBW6
"""DeepSeek 多轮对话命令行机器人。

用法:
    pip install openai                     # 首次安装依赖
    python chatbot.py                      # 密钥从 .env 自动读取

.env 文件内容（与 chatbot.py 同目录）:
    DEEPSEEK_API_KEY=sk-你的key

输入 exit / quit / 退出 结束对话。
"""

import json
import os
import sys
from pathlib import Path
from typing import List

from openai import OpenAI

from schema import TOOLS
from tools import TOOL_MAP

# ============ 可配置项 ============
BASE_DIR = Path(__file__).resolve().parent  # 项目根目录（.env、progress.json 都相对它定位）
BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-chat"  # 通用对话模型；想用推理模型改为 deepseek-reasoner
MAX_HISTORY_TURNS = 10  # 最多保留的对话轮数，超出后丢弃最旧的轮次
MAX_TOOL_ROUNDS = 5  # 单轮对话最多允许的连续工具调用次数，防止模型异常时死循环
MAX_TOOL_RESULT_CHARS = 8000  # 单条工具结果写入历史的最大字符数，防止上下文膨胀
MAX_CONTEXT_CHARS=30000   # 整个上下文（system+历史）的总字符预算，防止单次请求超长
SYSTEM_PROMPT = "你是一个ROS学习助手，帮助用户学习ROS/ROS2与机器人编程。用户告诉你学习进度时用save_progress保存；用户问'学到哪了'时用get_progress查询；用户问ROS命令怎么用时用ros_cheatsheet查询；用户问概念、原理、代码示例等学习内容时用kb_search在知识库中检索。回答简洁，用中文。"

# ================================


def load_env_file(path=None) -> None:
    """极简 .env 读取：每行 KEY=VALUE，自动去除 BOM 与引号，已存在的环境变量优先。

    不依赖 python-dotenv，Windows 记事本/PowerShell 产生的 UTF-8 BOM 也能正确处理。
    不传 path 时默认读取项目根目录（脚本所在目录）的 .env，与启动时的当前目录无关。
    """
    if path is None:
        path = BASE_DIR / ".env"
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                key, sep, value = line.partition("=")
                if not sep:
                    continue
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, value)
    except FileNotFoundError:
        pass  # 没有 .env 文件时静默，交给环境变量处理


def _msg_chars(m: dict) -> int:
    """估算一条消息占用的字符数：content + 工具调用参数都要算。"""
    n = len(m.get("content") or "")
    for tc in m.get("tool_calls") or []:
        n += len(tc.get("function", {}).get("arguments", ""))
    return n


def trim_history(messages: List[dict]) -> List[dict]:
    """控制上下文长度：
    1) 条数限制：只保留 system + 最近 MAX_HISTORY_TURNS 轮；
    2) 字符预算：仍超 MAX_CONTEXT_CHARS 时，从最旧的历史消息开始丢（system 和最后一轮用户消息始终保留）。
    """
    max_messages = 1 + MAX_HISTORY_TURNS * 4
    if len(messages) > max_messages:
        messages = [messages[0]] + messages[-(max_messages - 1):]

    total = sum(_msg_chars(m) for m in messages)
    while total > MAX_CONTEXT_CHARS and len(messages) > 2:
        dropped = messages.pop(1)  # 从最旧的历史消息开始丢（index 0 是 system）
        total -= _msg_chars(dropped)
    return _cleanup_message_pairs(messages)



def _cleanup_message_pairs(messages: List[dict]) -> List[dict]:
    """清理工具调用配对，防止孤儿 tool 消息导致 API 400。

    OpenAI 兼容 API 要求 role=tool 消息前面必须有配对的
    assistant.tool_calls；裁剪可能拆散配对，这里统一修补：
    1) 丢弃前面没有配对声明的孤儿 tool 消息；
    2) 移除 assistant.tool_calls 中响应已被裁掉的 call；
    3) assistant 消息若既无 content 也无 tool_calls，整条移除。
    """
    responded: set = set()   # 已配对成功的 call_id
    pending: set = set()     # 正在等待 tool 响应的 call_id
    first_pass = []
    for m in messages:
        if m["role"] == "assistant" and m.get("tool_calls"):
            first_pass.append(m)
            for tc in m["tool_calls"]:
                pending.add(tc["id"])
        elif m["role"] == "tool":
            cid = m.get("tool_call_id")
            if cid in pending:          # 前面有声明 → 合法，保留
                pending.discard(cid)
                responded.add(cid)
                first_pass.append(m)
            else:
                pass                    # 孤儿 tool 消息 → 丢弃
        else:
            if m["role"] == "user":     # 新一轮开始，作废没等到响应的声明
                pending.clear()
            first_pass.append(m)

    result = []
    for m in first_pass:
        if m["role"] == "assistant" and m.get("tool_calls"):
            alive = [tc for tc in m["tool_calls"] if tc["id"] in responded]
            if not alive and not (m.get("content") or ""):
                continue                # 空壳 assistant → 整条移除
            if alive != m["tool_calls"]:
                m = {**m, "tool_calls": alive}   # 只保留有响应的 call
        result.append(m)
    return result


def build_assistant_message(tool_calls, content=""):
    """把流式拼装出的工具调用转成标准 assistant 消息，用于回填历史。"""
    return {
        "role": "assistant",
        "content": content or None,
        "tool_calls": [
            {
                "id": c["id"],
                "type": "function",
                "function": {
                    "name": c["name"],
                    "arguments": c["arguments"],
                },
            }
            for c in tool_calls
        ],
    }


def process_tool_calls(messages, tool_calls):
    """执行工具并把结果回填进对话历史。"""
    messages.append(build_assistant_message(tool_calls))
    for call in tool_calls:
        name = call["name"]
        try:
            args = json.loads(call["arguments"] or "{}")
        except json.JSONDecodeError:
            args = {}
        print(f"\n  [调用工具] {name}({args})")
        try:
            result = TOOL_MAP[name](**args)
        except Exception as e:
            result = f"工具执行出错: {e}"
        result = str(result)
        if len(result) > MAX_TOOL_RESULT_CHARS:
            result = (result[:MAX_TOOL_RESULT_CHARS]
                      + f"\n...[工具结果过长已截断，共 {len(result)} 字符]")
        messages.append({
            "role": "tool",
            "tool_call_id": call["id"],
            "content": result,
        })


def assemble_tool_calls(chunks):
    """流式模式下把增量返回的 tool_calls 拼装成完整结构。

    返回 [{id, name, arguments}, ...]，arguments 是 JSON 字符串。
    """
    calls = {}
    order = []
    for chunk in chunks:
        for tc in chunk.choices[0].delta.tool_calls or []:
            idx = tc.index
            if idx not in calls:
                calls[idx] = {"id": "", "name": "", "arguments": ""}
                order.append(idx)
            if tc.id:
                calls[idx]["id"] = tc.id
            if tc.function and tc.function.name:
                calls[idx]["name"] += tc.function.name
            if tc.function and tc.function.arguments:
                calls[idx]["arguments"] += tc.function.arguments
    return [calls[i] for i in order]



def main() -> None:
    load_env_file()  # 先从同目录 .env 读取密钥
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("未找到 DEEPSEEK_API_KEY。")
        print(f"请检查 {BASE_DIR} 目录下是否有 .env 文件，内容为：")
        print("    DEEPSEEK_API_KEY=sk-你的key")
        print("注意：文件名必须是 .env（不是 .env.txt），等号两边不要有空格。")
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url=BASE_URL)
    messages: List[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    print("DeepSeek 多轮对话已启动。输入 exit / quit / 退出 结束对话。\n")

    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):  # Ctrl+D / Ctrl+C 也能退出
            print("\n再见！")
            break

        if user_input.lower() in ("exit", "quit", "退出"):
            print("再见！")
            break
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})
        messages = trim_history(messages)
        user_idx = len(messages) - 1  # 记录用户消息位置，出错时回滚本轮全部消息

        try:
            # 工具调用循环：模型可能要连续调多次工具，直到给出最终回答
            tool_rounds = 0
            while True:
                stream = client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    stream=True,  # 流式输出
                    tools=TOOLS,  # 声明可用工具
                )
                all_chunks = list(stream)  # 收集完整流，才能判断是回复还是工具调用
                tool_calls = assemble_tool_calls(all_chunks)
                content_parts = [
                    c.choices[0].delta.content or ""
                    for c in all_chunks
                    if c.choices[0].delta.content
                ]

                if tool_calls:
                    # 模型要调工具：执行并回填结果，继续下一轮推理
                    process_tool_calls(messages, tool_calls)
                    tool_rounds += 1
                    if tool_rounds >= MAX_TOOL_ROUNDS:
                        print(f"\n  [提示] 工具调用已达上限（{MAX_TOOL_ROUNDS} 次），停止本轮调用")
                        break
                    continue

                # 没有工具调用：正常输出回复
                reply = "".join(content_parts).strip()
                if reply:
                    print("AI: " + reply)
                    messages.append({"role": "assistant", "content": reply})
                break
        except Exception as exc:  # 网络、鉴权、余额不足等错误
            print(f"\n请求失败: {exc}")
            del messages[user_idx:]  # 撤掉本轮无人应答的消息与工具痕迹，避免污染历史


if __name__ == "__main__":
    main()
