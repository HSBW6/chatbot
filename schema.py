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
    {
        "type": "function",
        "function": {
            "name": "save_progress",
            "description": "保存用户当前学习到的ROS知识点或进度，比如用户说'我学到话题了'就调用",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "当前学到的主题，比如 话题Topic"
                    }
                },
                "required": ["topic"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_progress",
            "description": "查询用户之前保存的学习进度，回答'我学到哪了''上次学到什么'时调用",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
        {
        "type": "function",
        "function": {
            "name": "ros_cheatsheet",
            "description": "查询ROS2常用命令速查表，比如用户问 ros2 topic、ros2 node、ros2 launch 等命令怎么用时调用",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "想查的主题，可选：topic / node / launch / pkg / run / colcon / param / service"
                    }
                },
                "required": ["topic"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kb_search",
            "description": "在ROS2 21讲知识库中检索某个概念、原理、命令用法或代码示例，返回相关章节内容。用户问'什么是话题/节点/服务''怎么实现XX''ros2命令怎么用'等学习问题时调用",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "要检索的知识点关键词或问题，比如 话题 或 如何创建功能包 或 colcon build"
                    }
                },
                "required": ["query"]
            }
        }
    }

]
