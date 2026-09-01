# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HSBW6
"""tools.py 与 kb_search.py 的单元测试。

运行方式（在项目根目录 D:\\Deepseek\\chatbot 下）：
    python -m unittest discover -s tests -v
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# 让测试能 import 到项目根目录的模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tools
import kb_search


class TestCalculate(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(tools.calculate("1+1"), "2")
        self.assertEqual(tools.calculate("(3+5)*2"), "16")
        self.assertEqual(tools.calculate("10/4"), "2.5")

    def test_illegal_chars(self):
        self.assertEqual(tools.calculate("1; rm -rf"), "表达式包含非法字符")
        self.assertEqual(tools.calculate("__import__('os')"), "表达式包含非法字符")

    def test_error(self):
        self.assertIn("计算出错", tools.calculate("1/0"))


class TestReadLocalFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_file_not_found(self):
        result = tools.read_local_file("D:/不存在的文件_12345.txt")
        self.assertIn("文件不存在", result)

    def test_is_dir(self):
        result = tools.read_local_file(self.tmp.name)
        self.assertIn("文件夹", result)

    def test_sensitive_path(self):
        env_file = Path(self.tmp.name) / ".env"
        env_file.write_text("SECRET=123", encoding="utf-8")
        result = tools.read_local_file(str(env_file))
        self.assertIn("敏感", result)

    def test_normal_utf8(self):
        f = Path(self.tmp.name) / "a.txt"
        f.write_text("你好，ROS", encoding="utf-8")
        self.assertEqual(tools.read_local_file(str(f)), "你好，ROS")

    def test_too_large(self):
        f = Path(self.tmp.name) / "big.txt"
        f.write_text("x" * 300_000, encoding="utf-8")
        result = tools.read_local_file(str(f))
        self.assertIn("文件太大", result)

    def test_auto_truncate(self):
        f = Path(self.tmp.name) / "long.txt"
        f.write_text("y" * 6000, encoding="utf-8")
        result = tools.read_local_file(str(f))
        self.assertIn("已截断", result)


class TestProgress(unittest.TestCase):
    """save_progress / get_progress：必须把 PROGRESS_FILE 指向临时文件，否则会污染真实进度！"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fake_progress = Path(self.tmp.name) / "progress.json"
        patcher = mock.patch.object(tools, "PROGRESS_FILE", self.fake_progress)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_get_progress_empty(self):
        self.assertEqual(tools.get_progress(), "还没有保存过学习进度")

    def test_save_and_get(self):
        tools.save_progress("话题 Topic")
        self.assertIn("话题 Topic", tools.get_progress())

    def test_save_writes_json(self):
        tools.save_progress("节点 Node")
        data = json.loads(self.fake_progress.read_text(encoding="utf-8"))
        self.assertEqual(data["topic"], "节点 Node")
        self.assertIn("updated_at", data)


class TestRosCheatsheet(unittest.TestCase):
    def test_exact_keyword(self):
        result = tools.ros_cheatsheet("topic")
        self.assertIn("ros2 topic list", result)

    def test_chinese_keyword(self):
        result = tools.ros_cheatsheet("话题")
        self.assertIn("ros2 topic list", result)

    def test_unknown_topic(self):
        result = tools.ros_cheatsheet("不存在的主题")
        self.assertIn("没有找到", result)


class TestKbSearch(unittest.TestCase):
    def test_empty_query(self):
        self.assertEqual(kb_search.kb_search("  "), "检索关键词为空")

    def test_no_kb_dir(self):
        with mock.patch.object(kb_search, "KB_DIR", Path("D:/不存在的kb目录_12345")):
            result = kb_search.kb_search("话题")
            self.assertIn("知识库尚未构建", result)

    def test_tokenize(self):
        self.assertIn("话题", kb_search._tokenize("什么是话题"))
        self.assertIn("topic", kb_search._tokenize("ROS2 topic"))

    def test_split_by_heading(self):
        content = "# 标题\n\n## 第一小节\n内容\n\n## 第二小节\n更多内容"
        blocks = kb_search._split_by_heading(content)
        self.assertGreaterEqual(len(blocks), 2)

    def test_real_search(self):
        if kb_search.KB_DIR.exists():
            result = kb_search.kb_search("话题")
            self.assertIsInstance(result, str)
            self.assertTrue(len(result) > 0)
        else:
            self.skipTest("kb/ 目录不存在，跳过真实检索测试")


class TestGetWeather(unittest.TestCase):
    """get_weather 走网络，必须 mock，否则测试又慢又不稳定。"""

    def test_network_error(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("网络断开")):
            result = tools.get_weather("北京")
            self.assertIn("查询天气失败", result)

    def test_success(self):
        fake_json = json.dumps({
            "current_condition": [{
                "temp_C": "28",
                "lang_zh": [{"value": "晴"}],
            }]
        })
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = fake_json.encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False
        with mock.patch("urllib.request.urlopen", return_value=mock_resp):
            result = tools.get_weather("北京")
        self.assertIn("晴", result)
        self.assertIn("28", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
