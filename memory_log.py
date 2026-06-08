# memory_log.py — 记忆日志模块
# 无额外依赖，纯标准库
# 功能：
#   1. 把每次红莉栖说的话写进 log 文件
#   2. 读取最近 N 条记录，供"她记得你在干什么"功能使用
#   3. 日志按日期自动滚动（每天一个文件）

import os
import json
from datetime import datetime


# ── 配置 ──────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")   # 日志目录（与脚本同级）
MAX_RECENT = 5    # get_recent_context() 默认返回最近几条


def _today_log_path() -> str:
    """返回今日日志文件路径，如 logs/2026-06-05.jsonl"""
    os.makedirs(LOG_DIR, exist_ok=True)
    filename = datetime.now().strftime("%Y-%m-%d") + ".jsonl"
    return os.path.join(LOG_DIR, filename)


def write_log(process_name: str, window_title: str, reply: str):
    """
    追加一条记录到今日日志。
    每条记录是一行 JSON（JSONL 格式），方便后续解析。
    """
    record = {
        "ts":      datetime.now().strftime("%H:%M:%S"),
        "process": process_name,
        "title":   window_title,
        "reply":   reply,
    }
    try:
        with open(_today_log_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[Log 写入错误] {e}")


def get_recent_context(n: int = MAX_RECENT) -> str:
    """
    读取今日日志最近 n 条，格式化成自然语言，
    用于追加到 user message，让红莉栖"记得"用户之前在干什么。
    返回空字符串代表今天还没有记录。
    """
    path = _today_log_path()
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        recent = lines[-n:] if len(lines) >= n else lines
        if not recent:
            return ""
        parts = []
        for line in recent:
            rec = json.loads(line)
            parts.append(f"[{rec['ts']}] {rec['process']}「{rec['title']}」→ {rec['reply']}")
        return "【你今天之前看到用户做过这些事，可以结合记忆自然提及】\n" + "\n".join(parts)
    except Exception as e:
        print(f"[Log 读取错误] {e}")
        return ""


def tail_log(n: int = 20) -> list[dict]:
    """调试用：返回今日最后 n 条记录的 dict 列表"""
    path = _today_log_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        return [json.loads(l) for l in lines[-n:]]
    except Exception:
        return []


# 单独测试用
if __name__ == "__main__":
    write_log("chrome.exe", "GitHub - kurisu", "EN: Are you even reading the docs?\nZH: 你到底有没有在看文档？")
    write_log("code.exe",   "main.py - VSCode", "EN: Still debugging?\nZH: 还在调 bug 呢？")
    print(get_recent_context())
    print("\n--- tail ---")
    for rec in tail_log():
        print(rec)
