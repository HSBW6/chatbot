"""工具函数与注册表。

新增工具三步走：
1. 在这里写一个普通 Python 函数；
2. 在 schema.py 里声明它的调用说明；
3. 在下方 TOOL_MAP 里登记"名字 -> 函数"。
"""


def get_weather(city: str) -> str:
    """调用 wttr.in 获取真实天气（免费，无需 key）。"""
    import json
    import urllib.parse
    import urllib.request
    try:
        url = f"https://wttr.in/{urllib.parse.quote(city)}?format=j1&lang=zh"
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        cur = data["current_condition"][0]
        temp = cur["temp_C"]
        desc = cur["lang_zh"][0]["value"] if "lang_zh" in cur else cur["weatherDesc"][0]["value"]
        return f"{city} 当前 {desc}，气温 {temp}℃"
    except Exception as e:
        return f"查询天气失败: {e}"



def calculate(expression: str) -> str:
    """计算数学表达式，只允许数字和运算符，防止注入。"""
    allowed = "0123456789+-*/(). "
    if not all(c in allowed for c in expression):
        return "表达式包含非法字符"
    try:
        return str(eval(expression))
    except Exception as e:
        return f"计算出错: {e}"

def read_local_file(path: str) -> str:
    """读取本地文本文件内容（限制大小，避免刷屏）。"""
    import os
    try:
        if not os.path.exists(path):
            return f"文件不存在: {path}"
        if os.path.isdir(path):
            return f"这是一个文件夹，不是文件: {path}"
        size = os.path.getsize(path)
        if size > 200_000:
            return f"文件太大（{size} 字节），超过 200KB 限制，请换个小文件"
        # 先试 UTF-8，失败再试 GBK（Windows 中文文件常见）
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(path, "r", encoding="gbk", errors="replace") as f:
                content = f.read()
        if len(content) > 5000:
            content = content[:5000] + f"\n...[内容过长已截断，文件共 {len(content)} 字符]"
        return content
    except Exception as e:
        return f"读取文件出错: {e}"
PROGRESS_FILE = r"D:/Deepseek/chatbot/progress.json"

def save_progress(topic: str) -> str:
    """保存当前学习进度到本地 JSON 文件（重启不丢）。"""
    import json
    import os
    try:
        data = {"topic": topic, "updated_at": "2026-08-30"}
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return f"已记住学习进度：{topic}"
    except Exception as e:
        return f"保存进度失败: {e}"

def get_progress() -> str:
    """读取已保存的学习进度。"""
    import json
    import os
    try:
        if not os.path.exists(PROGRESS_FILE):
            return "还没有保存过学习进度"
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return f"你上次学到：{data['topic']}"
    except Exception as e:
        return f"读取进度失败: {e}"
ROS_CHEATSHEET = {
    "topic": [
        "ros2 topic list                # 列出所有话题",
        "ros2 topic echo <话题名>        # 查看话题实时消息",
        "ros2 topic pub <话题名> <类型> '{data}'  # 手动发布消息",
        "ros2 topic hz <话题名>          # 查看话题发布频率",
        "ros2 topic info <话题名>        # 查看话题类型和信息",
    ],
    "node": [
        "ros2 node list                 # 列出所有节点",
        "ros2 node info <节点名>         # 查看节点详情",
    ],
    "launch": [
        "ros2 launch <包名> <启动文件>   # 启动launch文件",
        "ros2 launch <包名> <文件> --show-args  # 查看launch支持的参数",
    ],
    "pkg": [
        "ros2 pkg list                  # 列出所有功能包",
        "ros2 pkg create <包名>         # 创建新功能包",
    ],
    "run": [
        "ros2 run <包名> <可执行文件>    # 运行一个节点",
    ],
    "colcon": [
        "colcon build                   # 编译工作空间",
        "source install/setup.bash      # 编译后刷新环境变量",
    ],
    "param": [
        "ros2 param list                # 列出所有参数",
        "ros2 param get <节点> <参数>    # 获取参数值",
        "ros2 param set <节点> <参数> <值>  # 设置参数",
    ],
    "service": [
        "ros2 service list              # 列出所有服务",
        "ros2 service call <服务名> <类型> '{data}'  # 调用服务",
    ],
}

_ROS_KEYWORDS = {
    "topic": ["topic", "话题", "消息"],
    "node": ["node", "节点"],
    "launch": ["launch", "启动"],
    "pkg": ["pkg", "package", "包"],
    "run": ["run", "运行"],
    "colcon": ["colcon", "编译", "构建"],
    "param": ["param", "参数"],
    "service": ["service", "服务"],
}

def ros_cheatsheet(topic: str) -> str:
    """查询 ROS2 常用命令速查表，支持中英文关键词。"""
    key = topic.strip().lower()
    for name, keywords in _ROS_KEYWORDS.items():
        if key == name or key in keywords:
            lines = [f"【{name} 速查】"] + ROS_CHEATSHEET[name]
            return "\n".join(lines)
    names = " / ".join(ROS_CHEATSHEET.keys())
    return f"没有找到关于「{topic}」的命令。可选主题：{names}"





# 工具注册表：模型返回的工具名 -> 实际执行的函数
TOOL_MAP = {
    "get_weather": get_weather,
    "calculate": calculate,
    "read_local_file": read_local_file,
    "save_progress": save_progress,
    "get_progress": get_progress,
    "ros_cheatsheet": ros_cheatsheet,
}
