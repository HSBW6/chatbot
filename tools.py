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



# 工具注册表：模型返回的工具名 -> 实际执行的函数
TOOL_MAP = {
    "get_weather": get_weather,
    "calculate": calculate,
    "read_local_file": read_local_file,
}
