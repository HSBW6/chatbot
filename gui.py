# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HSBW6
"""DeepSeek 多轮对话机器人 - 简单 GUI 版（tkinter）

运行方式:
    cd D:\\Deepseek\\chatbot
    .\\.venv\\Scripts\\activate
    python gui.py

依赖: 只用 Python 自带的 tkinter，无需额外安装。
"""
import json
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import scrolledtext

from openai import OpenAI

from schema import TOOLS
from tools import TOOL_MAP
from chatbot import (MAX_TOOL_RESULT_CHARS,SYSTEM_PROMPT, assemble_tool_calls,
                     build_assistant_message, load_env_file, trim_history)

# ============ 可配置项 ============
BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-chat"
MAX_TOOL_ROUNDS = 5  # 单轮对话最多允许的连续工具调用次数，防止模型异常时死循环
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
        result = str(result)
        if len(result) > MAX_TOOL_RESULT_CHARS:
            result = (result[:MAX_TOOL_RESULT_CHARS]
                      + f"\n...[工具结果过长已截断，共 {len(result)} 字符]")
        messages.append({
            "role": "tool",
            "tool_call_id": call["id"],
            "content": result,
        })


def chat_worker(user_text, messages, msg_queue):
    """后台线程：跑完整的多轮对话逻辑，输出经队列送回 GUI。"""
    load_env_file()
    client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url=BASE_URL)

    messages.append({"role": "user", "content": user_text})
    messages = trim_history(messages)
    user_idx = len(messages) - 1  # 记录用户消息位置，出错时回滚本轮全部消息

    try:
        tool_rounds = 0
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
                tool_rounds += 1
                if tool_rounds >= MAX_TOOL_ROUNDS:
                    msg_queue.put(("tool", f"[提示] 工具调用已达上限（{MAX_TOOL_ROUNDS} 次），停止本轮调用"))
                    msg_queue.put(("ai_done", ""))
                    break
                continue

            reply = "".join(content_parts).strip()
            if reply:
                # 流式打字机：按小块逐条入队，每块间隔 50ms，GUI 才能边收边打
                for i in range(0, len(reply), 3):
                    msg_queue.put(("ai_chunk", reply[i:i+3]))
                    time.sleep(0.05)  # 关键：让小块"慢慢"进队列
                messages.append({"role": "assistant", "content": reply})
            msg_queue.put(("ai_done", ""))  # 结束标记，GUI 据此收尾并恢复按钮
            break


    except Exception as exc:
        del messages[user_idx:]  # 撤掉本轮无人应答的消息与工具痕迹，避免污染历史
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
        self.chat_area.tag_config("thinking", foreground="#808080")  # 新增：思考提示用灰色


        # 底部输入区
        bottom = tk.Frame(root)
        bottom.pack(fill=tk.X, padx=10, pady=(0, 10))

        self.entry = tk.Text(bottom, height=2, wrap=tk.WORD,
                             font=("Microsoft YaHei", 11))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.entry.bind("<Return>", self.on_enter)
        self.entry.bind("<Control-Return>", self.on_ctrl_enter)


        self.send_btn = tk.Button(bottom, text="发送", command=self.send,
                                  font=("Microsoft YaHei", 11))
        self.send_btn.pack(side=tk.RIGHT, padx=(8, 0))
                # 新增：清空对话按钮（放在发送按钮左边）
        self.clear_btn = tk.Button(bottom, text="清空", command=self.clear_chat,
                                   font=("Microsoft YaHei", 11))
        self.clear_btn.pack(side=tk.RIGHT, padx=(8, 0))


        # 消息队列 + 定时轮询（线程安全的关键）
        self.msg_queue = queue.Queue()
        self.root.after(100, self.poll_queue)

        # 对话历史（system 开头）
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.busy = False  # 防止连点发送导致并发
        self.ai_streaming = False  # 新增：打字机流是否正在进行

        

    # ---------- 界面操作 ----------
    def append_chat(self, tag, text):
        self.chat_area.config(state="normal")
        self.chat_area.insert(tk.END, text + "\n", tag)
        self.chat_area.config(state="disabled")
        self.chat_area.see(tk.END)  # 自动滚到底部
    def append_chunk(self, tag, text):
        """追加一小段文本（不换行），用于打字机效果。"""
        self.chat_area.config(state="normal")
        self.chat_area.insert(tk.END, text, tag)
        self.chat_area.config(state="disabled")
        self.chat_area.see(tk.END)  # 自动滚到底部

    def on_enter(self, event):
        """Enter 发送消息；return "break" 阻止 Text 默认插入换行。"""
        self.send()
        return "break"

    def on_ctrl_enter(self, event):
        """Ctrl+Enter 手动插入换行。"""
        self.entry.insert(tk.INSERT, "\n")
        return "break"



    def send(self):
        if self.busy:
            return
        text = self.entry.get("1.0", tk.END).strip()
        if not text:
            return
        self.entry.delete("1.0", tk.END)

        self.append_chat("user", f"你: {text}")
        self.busy = True
        self.send_btn.config(state="disabled")
        # ===== 新增：显示"AI 思考中..."（用 tag 标记，删除更精准） =====
        self.chat_area.config(state="normal")
        self.chat_area.insert(tk.END, "AI 思考中...\n", ("thinking", "thinking_marker"))
        self.chat_area.config(state="disabled")

        # ===== 新增：发送后自动聚焦输入框，不用再点鼠标 =====
        self.entry.focus_set()
        # 开线程跑对话，避免界面卡死
        threading.Thread(
            target=chat_worker,
            args=(text, self.messages, self.msg_queue),
            daemon=True,
        ).start()
    def clear_chat(self):
        """清空聊天区，重置对话历史（相当于新开一段对话）。"""
        if self.busy:
            return  # 请求还没结束不允许清空
        self.chat_area.config(state="normal")
        self.chat_area.delete("1.0", tk.END)
        self.chat_area.config(state="disabled")
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.entry.focus_set()

    def remove_thinking(self):
        """删除"AI 思考中..."提示（用 tag 精确定位，不受隐藏换行影响）。"""
        ranges = self.chat_area.tag_ranges("thinking_marker")
        if ranges:
            self.chat_area.config(state="normal")
            self.chat_area.delete(ranges[0], ranges[1])
            self.chat_area.tag_delete("thinking_marker")
            self.chat_area.config(state="disabled")


    def poll_queue(self):
        """每隔 100ms 检查后台线程有没有新消息，有就显示。"""
        try:
            while True:
                kind, text = self.msg_queue.get_nowait()
                if kind == "tool":
                    self.append_chat("tool", text)
                elif kind == "ai_chunk":
                    if not self.ai_streaming:
                        # 第一块：删掉"思考中"，带 "AI: " 前缀起头
                        self.remove_thinking()
                        self.append_chunk("ai", f"AI: {text}")
                        self.ai_streaming = True
                    else:
                        # 后续块：直接接着打
                        self.append_chunk("ai", text)
                elif kind == "ai_done":
                    if self.ai_streaming:
                        self.append_chat("ai", "")  # 打完了，补个换行收尾
                    self.ai_streaming = False
                    self.busy = False
                    self.send_btn.config(state="normal")

                elif kind == "error":
                    self.remove_thinking()  # 新增：报错也要删掉"思考中"
                    self.append_chat("error", text)
                    self.ai_streaming = False  # 出错时也要复位打字机状态
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
