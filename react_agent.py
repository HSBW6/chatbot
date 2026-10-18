#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HSBW6
"""Plan-and-Execute + ReAct 多步 Agent。

和 chatbot.py 的区别（面试里最容易被追问的点）：
- chatbot.py：一条用户消息 → 最多 5 次工具调用 → 回答。循环是隐式的，
  没有显式计划，也没有"做完这步要不要改计划"的判断。
- react_agent.py：先让模型产出**显式计划**（JSON 步骤列表），再逐步执行；
  每一步内部是 ReAct 循环（思考 → 选工具 → 观察 → 再决定），
  每步结束后做一次反思，决定继续 / 重规划 / 提前结束。

拆开的好处：
1. 计划是结构化数据，可展示、可测试，不依赖模型自由发挥；
2. 单步失败不会拖垮整个任务：该步标记 failed，反思阶段可以重规划；
3. 上下文只带"已完成的观察摘要"，不随步数线性膨胀。

用法：
    python react_agent.py "查一下 ROS2 topic 的常用命令，再算 2**10，最后把结果写到 notes.txt"
    python react_agent.py            # 交互式输入任务
"""
import json
import sys

from chatbot import BASE_URL, MODEL, load_env_file
from schema import TOOLS
from tools import TOOL_MAP

# 单条工具结果写入上下文的字符上限（和 chatbot.py 保持同一口径）
MAX_TOOL_RESULT_CHARS = 8000
# 每个步骤内部最多允许几次工具调用；超过就判定该步"没做完"
DEFAULT_MAX_TOOL_ROUNDS = 4
# 整个任务最多允许几次重规划，防止模型反复改计划绕圈
DEFAULT_MAX_REPLANS = 2

_PLANNER_PROMPT = (
    "你是任务规划器。把用户的任务拆成 2~6 个可执行步骤，每步只做一件明确的事。\n"
    "只输出 JSON，不要解释，格式：\n"
    '{"steps": [{"goal": "这一步要完成什么", "hint": "建议用哪个工具，可留空"}]}\n'
    "要求：步骤之间尽量独立；能用工具完成的要写成工具能做的动作；"
    "最后一步必须是给出最终答复。"
)

_EXECUTOR_PROMPT = (
    "你是一个会使用工具的执行者。现在只处理当前这一个步骤。\n"
    "规则：\n"
    "1. 需要外部信息或计算时，调用工具，不要编造；\n"
    "2. 拿到工具结果后，用一句话给出这一步的结论；\n"
    "3. 不要复述整个计划，不要处理其它步骤；\n"
    "4. 工具失败就如实说明，并给出你还能给出的结论。"
)

_REFLECT_PROMPT = (
    "你是任务监督者。根据已完成步骤的观察，判断下一步怎么走。\n"
    "只输出 JSON：\n"
    '{"decision": "continue|replan|done", "reason": "一句话理由"}\n'
    "continue = 按原计划继续；replan = 原计划已不适用，需要改；"
    "done = 任务目标已经达成，可以收尾。"
)

_REPLAN_PROMPT = (
    "原计划执行不下去了。根据已经完成的观察，重新规划剩余步骤。\n"
    "只输出 JSON：\n"
    '{"steps": [{"goal": "剩余步骤", "hint": "建议工具，可留空"}]}\n'
    "不要重复已经完成的步骤。"
)

_SYNTH_PROMPT = (
    "你是最终汇总者。根据任务和每个步骤的观察，给出面向用户的完整答复。\n"
    "要求：直接回答任务；不要罗列内部步骤编号；不确定的地方如实说明。"
)


def _extract_json(text):
    """从模型输出里取 JSON：容忍 ```json 围栏、前后废话。失败返回 None。"""
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        # 去掉第一行围栏与结尾围栏
        lines = text.splitlines()
        if len(lines) >= 2:
            text = "\n".join(lines[1:]).rstrip("`").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return None


def _as_steps(payload, fallback_task):
    """把规划 JSON 转成 [{"goal": str, "hint": str}]；结构不对就兜底成单步。"""
    steps = []
    if isinstance(payload, dict):
        raw = payload.get("steps")
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and str(item.get("goal", "")).strip():
                    steps.append({
                        "goal": str(item["goal"]).strip(),
                        "hint": str(item.get("hint", "") or "").strip(),
                    })
                elif isinstance(item, str) and item.strip():
                    steps.append({"goal": item.strip(), "hint": ""})
    if not steps:
        steps = [{"goal": fallback_task, "hint": ""}]
    return steps


class ReActAgent:
    """显式计划 + 逐步 ReAct 的 Agent。

    chat_fn 是唯一的 LLM 入口：
        chat_fn(messages, tools=None) -> {"content": str, "tool_calls": [ ... ]}
    默认实现走 OpenAI 兼容接口；测试时注入假函数，不联网、不花钱。
    """

    def __init__(self, chat_fn=None, model=MODEL, tools=None, tool_map=None,
                 max_steps=10, max_tool_rounds=DEFAULT_MAX_TOOL_ROUNDS,
                 max_replans=DEFAULT_MAX_REPLANS):
        self.model = model
        self.tools = TOOLS if tools is None else tools
        self.tool_map = TOOL_MAP if tool_map is None else tool_map
        self.max_steps = max_steps
        self.max_tool_rounds = max_tool_rounds
        self.max_replans = max_replans
        self._chat_fn = chat_fn or self._make_default_chat_fn()
        # 运行状态（run 时重置）
        self.steps = []
        self.observations = []
        self.replans = 0
        self.last_tool_calls = []

    # ---------------- LLM 入口 ----------------

    def _make_default_chat_fn(self):
        import os
        from openai import OpenAI
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise SystemExit("未找到 DEEPSEEK_API_KEY，请先在项目根目录的 .env 里配置")
        client = OpenAI(api_key=api_key, base_url=BASE_URL)

        def _chat(messages, tools=None):
            kwargs = {"model": self.model, "messages": messages, "temperature": 0}
            if tools:
                kwargs["tools"] = tools
            resp = client.chat.completions.create(**kwargs)
            msg = resp.choices[0].message
            calls = []
            for tc in (getattr(msg, "tool_calls", None) or []):
                calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments or "{}",
                })
            return {"content": (msg.content or "").strip(), "tool_calls": calls}

        return _chat

    # ---------------- 工具执行 ----------------

    def _call_tool(self, name, arguments):
        try:
            args = json.loads(arguments or "{}")
        except Exception:
            args = {}
        if not isinstance(args, dict):
            args = {}
        fn = self.tool_map.get(name)
        if fn is None:
            return "未知工具：%s（可用：%s）" % (name, ", ".join(sorted(self.tool_map)))
        try:
            result = str(fn(**args))
        except Exception as exc:
            return "工具执行出错：%s: %s" % (type(exc).__name__, exc)
        if len(result) > MAX_TOOL_RESULT_CHARS:
            result = result[:MAX_TOOL_RESULT_CHARS] + "\n...[工具结果过长已截断]"
        return result

    # ---------------- 规划 / 执行 / 反思 ----------------

    def plan(self, task):
        messages = [
            {"role": "system", "content": _PLANNER_PROMPT},
            {"role": "user", "content": "任务：%s" % task},
        ]
        reply = self._chat_fn(messages)
        return _as_steps(_extract_json(reply.get("content", "")), task)

    def execute_step(self, task, step):
        """执行单个步骤：内部是 ReAct 循环（工具调用 → 观察 → 再决定）。"""
        context_lines = ["任务：%s" % task, "当前步骤：%s" % step["goal"]]
        if step.get("hint"):
            context_lines.append("工具建议：%s" % step["hint"])
        if self.observations:
            context_lines.append("已完成步骤的观察：")
            for i, obs in enumerate(self.observations, 1):
                context_lines.append("  %d. %s" % (i, obs))
        messages = [
            {"role": "system", "content": _EXECUTOR_PROMPT},
            {"role": "user", "content": "\n".join(context_lines)},
        ]

        for _ in range(self.max_tool_rounds):
            reply = self._chat_fn(messages, tools=self.tools)
            tool_calls = reply.get("tool_calls") or []
            if not tool_calls:
                content = (reply.get("content") or "").strip()
                if content:
                    return content
                return "（本步骤没有输出结论）"
            # 把 assistant 的工具声明与逐个工具结果写回历史
            messages.append({
                "role": "assistant",
                "content": reply.get("content") or None,
                "tool_calls": [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["name"], "arguments": c["arguments"]}}
                    for c in tool_calls
                ],
            })
            for call in tool_calls:
                result = self._call_tool(call["name"], call["arguments"])
                self.last_tool_calls.append(call["name"])
                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": result,
                })
        return "（本步骤调用了 %d 次工具仍未得出结论，已停止）" % self.max_tool_rounds

    def reflect(self, task):
        joined = "\n".join(
            "%d. %s" % (i, obs) for i, obs in enumerate(self.observations, 1)
        ) or "（还没有完成的步骤）"
        messages = [
            {"role": "system", "content": _REFLECT_PROMPT},
            {"role": "user", "content": "任务：%s\n已完成步骤的观察：\n%s" % (task, joined)},
        ]
        reply = self._chat_fn(messages)
        payload = _extract_json(reply.get("content", "")) or {}
        decision = str(payload.get("decision", "continue")).strip().lower()
        if decision not in ("continue", "replan", "done"):
            decision = "continue"
        return decision

    def replan(self, task):
        joined = "\n".join(
            "%d. %s" % (i, obs) for i, obs in enumerate(self.observations, 1)
        ) or "（还没有完成的步骤）"
        messages = [
            {"role": "system", "content": _REPLAN_PROMPT},
            {"role": "user", "content": "任务：%s\n已完成步骤的观察：\n%s" % (task, joined)},
        ]
        reply = self._chat_fn(messages)
        return _as_steps(_extract_json(reply.get("content", "")), task)

    def synthesize(self, task):
        joined = "\n".join(
            "步骤 %d：%s" % (i, obs) for i, obs in enumerate(self.observations, 1)
        ) or "（没有任何执行结果）"
        messages = [
            {"role": "system", "content": _SYNTH_PROMPT},
            {"role": "user", "content": "任务：%s\n\n各步骤观察：\n%s" % (task, joined)},
        ]
        reply = self._chat_fn(messages)
        return (reply.get("content") or "").strip() or "（未能生成最终答复）"

    # ---------------- 主流程 ----------------

    def run(self, task):
        """执行完整任务，返回最终答复。过程中会更新 self.steps / observations。"""
        task = (task or "").strip()
        if not task:
            return "任务为空"
        self.steps = self.plan(task)
        self.observations = []
        self.replans = 0
        self.last_tool_calls = []

        cursor = 0
        while cursor < len(self.steps) and cursor < self.max_steps:
            step = self.steps[cursor]
            try:
                result = self.execute_step(task, step)
            except Exception as exc:
                result = "步骤异常：%s: %s" % (type(exc).__name__, exc)
            self.observations.append(result)
            step["status"] = "done"
            cursor += 1

            decision = self.reflect(task)
            if decision == "done":
                break
            if decision == "replan" and self.replans < self.max_replans:
                self.replans += 1
                new_steps = self.replan(task)
                # 保留已完成的步骤，替换剩余部分
                self.steps = self.steps[:cursor] + new_steps

        return self.synthesize(task)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    load_env_file()
    task = " ".join(argv).strip()
    if not task:
        try:
            task = input("任务：").strip()
        except (EOFError, KeyboardInterrupt):
            return 1
    if not task:
        print("任务为空")
        return 1
    print("任务：%s" % task)
    agent = ReActAgent()
    answer = agent.run(task)
    print("\n===== 最终答复 =====")
    print(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
