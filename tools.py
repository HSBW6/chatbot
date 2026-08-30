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


# 工具注册表：模型返回的工具名 -> 实际执行的函数
TOOL_MAP = {
    "get_weather": get_weather,
    "calculate": calculate,
}
