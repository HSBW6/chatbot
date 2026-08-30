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
from typing import List

from openai import OpenAI

from schema import TOOLS
from tools import TOOL_MAP

# ============ 可配置项 ============
BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-chat"  # 通用对话模型；想用推理模型改为 deepseek-reasoner
MAX_HISTORY_TURNS = 10  # 最多保留的对话轮数，超出后丢弃最旧的轮次
SYSTEM_PROMPT = "你是一个乐于助人的助手。"
# ================================


def load_env_file(path: str = ".env") -> None:
    """极简 .env 读取：每行 KEY=VALUE，自动去除 BOM 与引号，已存在的环境变量优先。

    不依赖 python-dotenv，Windows 记事本/PowerShell 产生的 UTF-8 BOM 也能正确处理。
    """
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


def trim_history(messages: List[dict]) -> List[dict]:
    """控制上下文长度：只保留 system + 最近 MAX_HISTORY_TURNS 轮（每轮最多 4 条，含工具消息）。"""
    max_messages = 1 + MAX_HISTORY_TURNS * 4
    if len(messages) > max_messages:
        return [messages[0]] + messages[-(max_messages - 1):]
    return messages
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
        messages.append({
            "role": "tool",
            "tool_call_id": call["id"],
            "content": str(result),
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
        print("请检查 D:\\Deepseek\\chatbot 目录下是否有 .env 文件，内容为：")
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

        try:
            # 工具调用循环：模型可能要连续调多次工具，直到给出最终回答
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
                    continue

                # 没有工具调用：正常输出回复
                reply = "".join(content_parts).strip()
                if reply:
                    print("AI: " + reply)
                    messages.append({"role": "assistant", "content": reply})
                break
        except Exception as exc:  # 网络、鉴权、余额不足等错误
            print(f"\n请求失败: {exc}")
            messages.pop()  # 撤掉无人应答的用户消息，避免污染历史


if __name__ == "__main__":
    main()
