# cooldown_module.py — 冷却时间 + 时段感知模块
# 无额外依赖，纯标准库

import time
from datetime import datetime


# ── 冷却配置 ──────────────────────────────────────────────
SAME_APP_COOLDOWN = 120      # 同一个 app 触发间隔（秒），默认 2 分钟
GLOBAL_COOLDOWN   = 10       # 全局最短触发间隔（秒），防止极速连点

# ── 时段定义 ─────────────────────────────────────────────
# 格式：(起始小时, 结束小时, 时段标签)，左闭右开
TIME_SLOTS = [
    (5,  9,  "morning"),     # 早晨
    (9,  12, "forenoon"),    # 上午
    (12, 14, "noon"),        # 午休
    (14, 18, "afternoon"),   # 下午
    (18, 22, "evening"),     # 晚上
    (22, 24, "midnight"),    # 深夜
    (0,  5,  "midnight"),    # 深夜（跨零点）
]

# 时段 → 红莉栖语气提示（追加到 user message，让 AI 感知时段）
TIME_SLOT_HINT = {
    "morning":   "（现在是早晨，你稍微带点睡眼惺忪但还是毒舌的语气）",
    "forenoon":  "（现在是上午，状态正常）",
    "noon":      "（现在是午休时间，你语气懒懒的，像刚睡醒）",
    "afternoon": "（现在是下午，状态正常，精力充沛）",
    "evening":   "（现在是晚上，你语气稍微温柔一点点，但还是毒舌）",
    "midnight":  "（现在是深夜，你语气更低沉，带点担心用户熬夜的意味）",
}

# ── 状态记录（模块级，进程内有效）─────────────────────────
_last_trigger_time: float = 0.0          # 全局上次触发时间
_app_last_time: dict[str, float] = {}    # 每个 app 上次触发时间


def can_trigger(process_name: str) -> bool:
    """
    判断当前是否允许触发红莉栖（综合全局冷却 + 同 app 冷却）。
    """
    now = time.time()
    # 全局冷却
    if now - _last_trigger_time < GLOBAL_COOLDOWN:
        return False
    # 同 app 冷却
    last = _app_last_time.get(process_name, 0.0)
    if now - last < SAME_APP_COOLDOWN:
        return False
    return True


def record_trigger(process_name: str):
    """
    触发成功后调用，更新冷却时间戳。
    """
    global _last_trigger_time
    now = time.time()
    _last_trigger_time = now
    _app_last_time[process_name] = now


def get_time_slot() -> str:
    """返回当前时段标签，如 'midnight'"""
    hour = datetime.now().hour
    for start, end, label in TIME_SLOTS:
        if start <= hour < end:
            return label
    return "evening"


def get_time_hint() -> str:
    """返回追加到 user message 的时段提示文字"""
    return TIME_SLOT_HINT.get(get_time_slot(), "")


# 单独测试用
if __name__ == "__main__":
    proc = "chrome.exe"
    print(f"当前时段: {get_time_slot()}")
    print(f"时段提示: {get_time_hint()}")
    print(f"能触发吗: {can_trigger(proc)}")
    record_trigger(proc)
    print(f"记录后能触发吗: {can_trigger(proc)}")
