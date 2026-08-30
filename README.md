---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 110f755b5028546ed56b284ce71f603e_332d26dca43a11f192a2525400287e28
    ReservedCode1: O5CsfhW0/uOMzfYoGp8JCqabT0aWopr3mALtWxKgJ9nkLSRCfFNcrss7+NTwURwY+UXRHrFXrIVS2xtX/+IExz4kqIgijF1GrWsVtlhzIIpZeDLXPBNYCSUrWmENjMS5J2IypahIH85vXTb3lEJQTzgZUIDtuzBAA7q213Jt0Q9lPMAqaJA0XDAodA8=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 110f755b5028546ed56b284ce71f603e_332d26dca43a11f192a2525400287e28
    ReservedCode2: O5CsfhW0/uOMzfYoGp8JCqabT0aWopr3mALtWxKgJ9nkLSRCfFNcrss7+NTwURwY+UXRHrFXrIVS2xtX/+IExz4kqIgijF1GrWsVtlhzIIpZeDLXPBNYCSUrWmENjMS5J2IypahIH85vXTb3lEJQTzgZUIDtuzBAA7q213Jt0Q9lPMAqaJA0XDAodA8=
---

# DeepSeek 命令行 / GUI Agent 聊天机器人

一个基于 DeepSeek API 的 **Python 多轮对话机器人**，已升级为带**工具调用（function calling）的 Agent**。支持流式输出、多轮对话，并能自动调用工具完成查天气、数学计算、读取本地文件等操作。

提供两种使用入口：

- **命令行版**（`chatbot.py`）：轻量、直接，适合终端与脚本场景
- **GUI 版**（`gui.py`）：基于 tkinter 的图形聊天窗口，线程 + 队列防卡死

---

## 功能特性

- **流式输出**：基于 `stream=True` 实时接收模型回复
- **多轮对话**：自动维护对话历史，保留最近 `MAX_HISTORY_TURNS` 轮（默认 10 轮）
- **工具调用（Agent）**：模型可自动决定调用以下内置工具，并支持一次连续调用多个工具：
  - `get_weather(city)`：查询真实天气（基于 wttr.in，免费、无需 key，支持中文城市名）
  - `calculate(expression)`：计算数学表达式（字符白名单防注入）
  - `read_local_file(path)`：读取本地文本文件内容（UTF-8 / GBK 自动识别，≤200KB，超长自动截断）
- **命令行 / GUI 双入口**：同一套对话逻辑，两种交互方式
- **一键启动**：提供 `start.bat` 双击即用
- **密钥安全**：API Key 存放于本地 `.env`，已由 `.gitignore` 排除，不会误传 GitHub

## 快速开始

### 环境要求

- Python 3.9+（建议 3.10 及以上）
- 一个 DeepSeek API Key（在 [DeepSeek 开放平台](https://platform.deepseek.com/) 获取）
- Windows / macOS / Linux 均可运行

### 1. 克隆项目

```powershell
git clone https://github.com/HSBW6/chatbot.git
cd chatbot
```

### 2. 创建虚拟环境并安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\activate        # Windows
# source .venv/bin/activate     # macOS / Linux

pip install openai
```

> 本项目仅依赖 `openai` 一个第三方包；GUI 版使用 Python 自带的 tkinter，无需额外安装。

### 3. 配置 API Key

在项目根目录（`chatbot.py` 同目录）创建 `.env` 文件，内容为：

```ini
DEEPSEEK_API_KEY=sk-你的key
```

> 注意：
> - 文件名必须是 `.env`（不是 `.env.txt`）
> - 等号两边不要有空格
> - `.env` 已被 `.gitignore` 忽略，请勿提交到 Git

### 4. 启动

#### 方式一：命令行版（chatbot.py）

```powershell
cd D:\Deepseek\chatbot
.\.venv\Scripts\activate
python chatbot.py
```

或者直接双击 `start.bat`（会自动激活 `.venv` 并运行命令行版）。

输入 `exit` / `quit` / `退出` 结束对话。

#### 方式二：GUI 版（gui.py）

```powershell
cd D:\Deepseek\chatbot
.\.venv\Scripts\activate
python gui.py
```

在窗口底部输入文字，按回车或点击「发送」即可对话。GUI 使用线程 + 消息队列，对话期间界面不会卡死；发送按钮在请求未完成时自动禁用，防止并发。

## 使用示例

启动后直接输入即可对话：

```
你: 北京的天气
[调用工具] get_weather({'city': '北京'})
AI: 北京 当前 晴，气温 31℃

你: 帮我算 (3+5)*2
[调用工具] calculate({'expression': '(3+5)*2'})
AI: 16

你: 读取 D:/test.txt 的内容
[调用工具] read_local_file({'path': 'D:/test.txt'})
AI: （文件内容……）

你: 先算 100/4，再说说北京天气
[调用工具] calculate({'expression': '100/4'})
[调用工具] get_weather({'city': '北京'})
AI: 100/4 = 25。北京当前 晴，气温 31℃。
```

模型会根据对话内容自动决定是否调用工具、调用哪个工具，因此也可以用自然语言描述需求，例如「今天上海热吗」「算一下 2 的 10 次方」。

## 项目结构

```
D:\Deepseek\chatbot
├── chatbot.py          # 命令行主程序：对话主循环 + 流式工具调用拼装/回填/历史裁剪
├── gui.py              # tkinter GUI 版聊天界面：线程 + 队列防卡死，复用 chatbot.py 核心逻辑
├── tools.py            # 工具函数（get_weather / calculate / read_local_file）+ TOOL_MAP 注册表
├── schema.py           # 工具声明（TOOLS，OpenAI 兼容的 JSON Schema 格式）
├── start.bat           # 一键启动脚本（激活 .venv 后运行命令行版）
├── test.txt            # 测试 read_local_file 工具的示例文本文件
├── .env                # DeepSeek API Key（敏感，勿上传）
├── .gitignore          # 忽略 .env / .venv / __pycache__ / .idea / 备份文件等
└── .venv/              # Python 虚拟环境（勿上传）
```

> `chatbot_backup.py` 为改造前备份，已被 `.gitignore` 排除，仅本地保留。

## 配置说明

项目根目录 `.env` 文件支持以下配置：

| 变量 | 说明 | 示例 |
|------|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥，必填 | `sk-xxxxxxxx` |

代码内可配置项（位于 `chatbot.py` 顶部配置区）：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `BASE_URL` | `https://api.deepseek.com` | DeepSeek API 地址 |
| `MODEL` | `deepseek-chat` | 通用对话模型；想用推理模型可改为 `deepseek-reasoner` |
| `MAX_HISTORY_TURNS` | `10` | 最多保留的对话轮数，超出后丢弃最旧轮次（省 token 可调小到 5-6） |
| `SYSTEM_PROMPT` | `你是一个乐于助人的助手。` | 系统提示词 |

## 常见问题

**Q1：启动时报错「未找到 DEEPSEEK_API_KEY」？**

检查项目根目录是否有 `.env` 文件，且内容格式为 `DEEPSEEK_API_KEY=sk-你的key`。注意文件名是 `.env`（不是 `.env.txt`），等号两边不要有空格。修改后重新运行。

**Q2：提示 `ModuleNotFoundError: No module named 'openai'`？**

说明还没有安装依赖，执行：

```powershell
.\.venv\Scripts\activate
pip install openai
```

**Q3：请求失败 / 报错 / 提示余额不足？**

- 确认 API Key 是否有效、账户是否有余额
- 检查网络能否访问 `https://api.deepseek.com`
- 国内直连 GitHub 时 `Connection reset` / 443 超时属于偶发网络问题，重试即可；DeepSeek API 本身一般不受影响

**Q4：GUI 版打开后窗口无反应？**

- 确认已运行 `load_env_file` 能读到 `.env` 中的 Key（启动时会在终端提示）
- 对话期间发送按钮会暂时禁用，属正常防并发行为，等待返回即可
- GUI 需要显示桌面环境，若在无图形界面的服务器上运行请使用命令行版

**Q5：`read_local_file` 读取中文文件乱码？**

工具会优先按 UTF-8 解码，失败后自动回退 GBK（Windows 中文文件常见编码），一般无需手动处理。若仍有乱码，请确认文件编码属于上述两种之一。

**Q6：git add 时提示 "LF will be replaced by CRLF"？**

这是 Git 在 Windows 下的行尾转换提示，属于正常现象，不影响提交。

## 扩展新工具（开发者）

三步即可为 Agent 新增一个工具：

1. 在 `tools.py` 中编写普通 Python 函数
2. 在 `schema.py` 的 `TOOLS` 列表中声明调用说明（JSON Schema 格式）
3. 在 `tools.py` 底部的 `TOOL_MAP` 中登记「工具名 -> 函数」

## License

本项目仅供学习交流使用，请遵守 [DeepSeek 开放平台服务条款](https://platform.deepseek.com/)。
*（内容由AI生成，仅供参考）*
