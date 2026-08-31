#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建 ROS2 21讲 知识库：
1. 爬取 book.guyuehome.com 的 21 讲图文正文 → kb/docs/
2. 解析 ros2_21_tutorials 代码仓库（带注释代码） → kb/code/
用法: python build_kb.py
"""
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

try:
    from bs4 import BeautifulSoup
    import html2text
except ImportError:
    sys.exit("缺少依赖: pip install beautifulsoup4 html2text")

BASE = "https://book.guyuehome.com/"
REPO = Path(r"C:\Users\lenovo\AppData\Local\Temp\ros2_21_tutorials")
OUT = Path(__file__).resolve().parent / "kb"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) kb-builder"}


def fetch(url: str, timeout: int = 30) -> str:
    time.sleep(1)  # 每次请求前延时约 1 秒，降低对目标站点的抓取压力
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def check_robots() -> None:
    """抓取前检查目标站点 robots.txt，若禁止抓取则提示并停止。"""
    robots_url = urllib.parse.urljoin(BASE, "robots.txt")
    print(f"[robots] 检查 {robots_url}")
    try:
        body = fetch(robots_url)
    except Exception as e:
        print(f"[robots] 无法获取 robots.txt（{e}），按无限制继续")
        return
    blocked = False
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition(":")
        if key.strip().lower() == "disallow":
            path = value.strip()
            if path != "":
                blocked = True
    if blocked:
        print("[robots] 警告: robots.txt 存在 Disallow 规则（禁止抓取），已停止构建以避免版权/合规风险")
        sys.exit(1)
    print("[robots] 未发现禁止抓取规则，继续")


def collect_chapter_links() -> list:
    """从首页目录树按文档顺序收集 21 讲章节链接 [(标题, href)]。"""
    html = fetch(BASE)
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.match(r"^ROS2/\d\.", href) and not href.startswith("ROS2_Book"):
            links.append((a.get_text(" ", strip=True), href))
    seen, out = set(), []
    for title, href in links:  # 去重保序（目录树顺序即章节顺序）
        if href not in seen:
            seen.add(href)
            out.append((title, href))
    return out


def page_to_md(href: str) -> str:
    url = urllib.parse.urljoin(BASE, href)
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")
    article = soup.find("article") or soup.select_one(".md-content__inner") or soup.body
    h = html2text.HTML2Text()
    h.ignore_images = True   # 正文图片暂不下载（后续可增强）
    h.body_width = 0         # 不折行
    return h.handle(str(article)).strip()


def safe_name(href: str) -> str:
    """href -> 文件名，保留层级与序号（注意不能 with_suffix，会误伤 2.4 这类名字）。"""
    href = urllib.parse.unquote(href)  # 解码 URL 编码的中文
    parts = [re.sub(r'[\\/:*?"<>|]', "_", p) for p in href.strip("/").split("/") if p]
    last = parts[-1] + ".md"
    return str(Path(*parts[:-1], last))


# ---------- 1. 爬取图文正文 ----------
def build_docs() -> None:
    check_robots()
    doc_dir = OUT / "docs"
    doc_dir.mkdir(parents=True, exist_ok=True)
    links = collect_chapter_links()
    print(f"[docs] 发现 {len(links)} 个章节")
    ok = fail = 0
    for title, href in links:
        name = safe_name(href)
        dest = doc_dir / name
        if dest.exists():
            print(f"  skip  {name} (已存在)")
            ok += 1
            continue
        try:
            md = page_to_md(href)
            if len(md) < 50:
                print(f"  warn  {name} 内容过短({len(md)}字符): {title}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            # 每篇末尾追加来源标注（独立一行），声明素材出处与使用限制
            md += "\n\n> 来源：古月居《ROS2入门21讲》book.guyuehome.com，仅个人学习使用，勿公开分发"
            dest.write_text(md, encoding="utf-8")
            print(f"  ok    {name} ({len(md)} 字符)")
            ok += 1
        except Exception as e:
            print(f"  FAIL  {name}: {e}")
            fail += 1
    print(f"[docs] 完成: 成功 {ok}, 失败 {fail}")


# ---------- 2. 解析代码仓库 ----------
CODE_FILES = {".py", ".cpp", ".hpp", ".h", ".xml", ".yaml", ".urdf", ".xacro",
              ".sdf", ".msg", ".srv", ".action", ".launch", ".cmake"}
CODE_NAMES = {"CMakeLists.txt", "package.xml"}
SKIP_DIRS = {"__pycache__", ".git", "build", "install", "log"}


def build_code() -> None:
    code_dir = OUT / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    if not REPO.exists():
        print(f"[code] 仓库不存在: {REPO}，跳过")
        return
    chapters = sorted(p for p in REPO.iterdir() if p.is_dir() and p.name.startswith("learning_"))
    print(f"[code] 发现 {len(chapters)} 个章节")
    for chap in chapters:
        files = []
        for f in chap.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(chap)
            if any(part in SKIP_DIRS for part in rel.parts):
                continue
            if f.suffix in CODE_FILES or f.name in CODE_NAMES:
                files.append(f)
        if not files:
            print(f"  skip  {chap.name} (无代码文件)")
            continue
        lines = [f"# {chap.name}", "", f"> 章节: {chap.name} ｜ 共 {len(files)} 个文件", ""]
        for f in sorted(files, key=lambda p: str(p).lower()):
            rel = f.relative_to(chap).as_posix()
            lines += [f"## `{rel}`", ""]
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                text = f.read_text(encoding="gbk", errors="replace")
            lang = {"py": "python", "cpp": "cpp", "hpp": "cpp", "h": "cpp",
                    "xml": "xml", "yaml": "yaml", "urdf": "xml", "xacro": "xml",
                    "sdf": "xml", "msg": "text", "srv": "text", "action": "text",
                    "launch": "xml", "cmake": "cmake"}.get(f.suffix.lstrip("."), "text")
            lines += ["```" + lang, text.rstrip(), "```", ""]
        dest = code_dir / f"{chap.name}.md"
        dest.write_text("\n".join(lines), encoding="utf-8")
        print(f"  ok    {chap.name}.md ({len(files)} 文件)")
    print("[code] 完成")


# ---------- 3. 索引 ----------
def build_index() -> None:
    docs = sorted(OUT.glob("docs/**/*.md"))
    codes = sorted(OUT.glob("code/*.md"))
    lines = ["# ROS2 21讲 知识库", "",
             "> 素材来源: 古月居图文教程(book.guyuehome.com) + ros2_21_tutorials 代码仓库（个人学习用途，勿公开分发）", ""]
    lines += ["## 图文正文", ""]
    for f in docs:
        lines.append(f"- [{f.stem}](docs/{f.relative_to(OUT / 'docs').as_posix()})")
    lines += ["", "## 代码示例", ""]
    for f in codes:
        lines.append(f"- [{f.stem}](code/{f.name})")
    (OUT / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[index] 生成 INDEX.md: {len(docs)} docs + {len(codes)} code")


if __name__ == "__main__":
    build_docs()
    build_code()
    build_index()
    print("全部完成 ->", OUT)
