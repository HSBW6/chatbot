"""工具声明（Schema）：告诉模型有哪些工具可用、怎么用。

注意：TOOLS 列表的顺序、字段名要与 tools.py 里的函数保持一致。
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询某个城市的天气情况",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名，比如 北京"
                    }
                },
                "required": ["city"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "计算数学表达式",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式，比如 (3+5)*2"
                    }
                },
                "required": ["expression"]
            }
        }
    },
        {
        "type": "function",
        "function": {
            "name": "read_local_file",
            "description": "读取本地文本文件的内容，输入文件的完整路径",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件的完整路径，比如 D:/test.txt"
                    }
                },
                "required": ["path"]
            }
        }
    },

]
