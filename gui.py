"""DeepSeek 多轮对话机器人 - 简单 GUI 版（tkinter）

运行方式:
    cd D:\Deepseek\chatbot
    .\.venv\Scripts\activate
    python gui.py

依赖: 只用 Python 自带的 tkinter，无需额外安装。
"""
import json
import os
import queue
import threading
import tkinter as tk
from tkinter import scrolledtext

from openai import OpenAI

from schema import TOOLS
from tools import TOOL_MAP
from chatbot import (assemble_tool_calls, build_assistant_message,
                     load_env_file, trim_history)

# ============ 可配置项 ============
BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-chat"
SYSTEM_PROMPT = "你是一个乐于助人的助手。"
# ================================


def run_tool_and_feedback(messages, tool_calls, msg_queue):
    """执行工具并把结果回填历史，同时把日志发给 GUI 队列。"""
    messages.append(build_assistant_message(tool_calls))
    for call in tool_calls:
        name = call["name"]
        try:
            args = json.loads(call["arguments"] or "{}")
        except json.JSONDecodeError:
            args = {}
        msg_queue.put(("tool", f"  [调用工具] {name}({args})"))
        try:
            result = TOOL_MAP[name](**args)
        except Exception as e:
            result = f"工具执行出错: {e}"
        messages.append({
            "role": "tool",
            "tool_call_id": call["id"],
            "content": str(result),
        })


def chat_worker(user_text, messages, msg_queue):
    """后台线程：跑完整的多轮对话逻辑，输出经队列送回 GUI。"""
    load_env_file()
    client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url=BASE_URL)

    messages.append({"role": "user", "content": user_text})
    messages = trim_history(messages)

    try:
        while True:
            stream = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                stream=True,
                tools=TOOLS,
            )
            all_chunks = list(stream)
            tool_calls = assemble_tool_calls(all_chunks)
            content_parts = [
                c.choices[0].delta.content or ""
                for c in all_chunks
                if c.choices[0].delta.content
            ]

            if tool_calls:
                run_tool_and_feedback(messages, tool_calls, msg_queue)
                continue

            reply = "".join(content_parts).strip()
            if reply:
                msg_queue.put(("ai", reply))
                messages.append({"role": "assistant", "content": reply})
            break
    except Exception as exc:
        msg_queue.put(("error", f"请求失败: {exc}"))


class ChatGUI:
    """一个简单的聊天窗口。"""

    def __init__(self, root):
        self.root = root
        self.root.title("DeepSeek 聊天机器人")
        self.root.geometry("520x620")

        # 聊天记录区（只读文本框）
        self.chat_area = scrolledtext.ScrolledText(
            root, wrap=tk.WORD, state="disabled", font=("Microsoft YaHei", 11))
        self.chat_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        # 文字配色：蓝色=你，黑色=AI，灰色=工具日志，红色=错误
        self.chat_area.tag_config("user", foreground="#1a73e8")
        self.chat_area.tag_config("ai", foreground="#000000")
        self.chat_area.tag_config("tool", foreground="#808080")
        self.chat_area.tag_config("error", foreground="#d93025")

        # 底部输入区
        bottom = tk.Frame(root)
        bottom.pack(fill=tk.X, padx=10, pady=(0, 10))

        self.entry = tk.Entry(bottom, font=("Microsoft YaHei", 11))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.entry.bind("<Return>", lambda e: self.send())

        self.send_btn = tk.Button(bottom, text="发送", command=self.send,
                                  font=("Microsoft YaHei", 11))
        self.send_btn.pack(side=tk.RIGHT, padx=(8, 0))

        # 消息队列 + 定时轮询（线程安全的关键）
        self.msg_queue = queue.Queue()
        self.root.after(100, self.poll_queue)

        # 对话历史（system 开头）
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.busy = False  # 防止连点发送导致并发

    # ---------- 界面操作 ----------
    def append_chat(self, tag, text):
        self.chat_area.config(state="normal")
        self.chat_area.insert(tk.END, text + "\n", tag)
        self.chat_area.config(state="disabled")
        self.chat_area.see(tk.END)  # 自动滚到底部

    def send(self):
        if self.busy:
            return
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, tk.END)
        self.append_chat("user", f"你: {text}")
        self.busy = True
        self.send_btn.config(state="disabled")
        # 开线程跑对话，避免界面卡死
        threading.Thread(
            target=chat_worker,
            args=(text, self.messages, self.msg_queue),
            daemon=True,
        ).start()

    def poll_queue(self):
        """每隔 100ms 检查后台线程有没有新消息，有就显示。"""
        try:
            while True:
                kind, text = self.msg_queue.get_nowait()
                if kind == "tool":
                    self.append_chat("tool", text)
                elif kind == "ai":
                    self.append_chat("ai", f"AI: {text}")
                    self.busy = False
                    self.send_btn.config(state="normal")
                elif kind == "error":
                    self.append_chat("error", text)
                    self.busy = False
                    self.send_btn.config(state="normal")
        except queue.Empty:
            pass
        self.root.after(100, self.poll_queue)


def main():
    load_env_file()
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("未找到 DEEPSEEK_API_KEY，请检查 .env 文件。")
        return

    root = tk.Tk()
    ChatGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
