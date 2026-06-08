# toast_module.py — 桌面气泡通知模块
# 依赖：pip install winotify
# winotify 比 win10toast 更稳定，支持 Windows 10/11 原生通知

from winotify import Notification, audio


APP_ID = "Kurisu Desktop Pet"
ICON_PATH = ""   # 留空用默认图标；如有 kurisu.ico 改成绝对路径，如 r"D:\...\kurisu.ico"


def _parse_reply(reply: str) -> tuple[str, str]:
    """从 'EN: ...\nZH: ...' 格式中提取英文和中文"""
    en_text = ""
    zh_text = ""
    for line in reply.splitlines():
        line = line.strip()
        if line.startswith("EN:"):
            en_text = line[3:].strip()
        elif line.startswith("ZH:"):
            zh_text = line[3:].strip()
    return en_text, zh_text


def show_toast(reply: str, window_title: str = "", process_name: str = ""):
    """
    弹出右下角气泡通知。
    标题显示进程名，正文显示红莉栖的中文台词（附英文小字）。
    """
    en_text, zh_text = _parse_reply(reply)

    # 通知标题
    title = f"红莉栖"
    if process_name:
        title += f"  ·  {process_name}"

    # 正文：中文在前，英文在后（用 em dash 分隔）
    body = zh_text
    if en_text:
        body += f"\n— {en_text}"

    try:
        toast = Notification(
            app_id=APP_ID,
            title=title,
            msg=body,
            duration="short",   # "short"=5s, "long"=25s
            icon=ICON_PATH if ICON_PATH else "",
        )
        toast.set_audio(audio.Default, loop=False)
        toast.show()
    except Exception as e:
        # 降级：直接打印，不中断主程序
        print(f"[Toast 降级] {e}")
        print(f"  [{title}] {body}")


# 单独测试用
if __name__ == "__main__":
    test_reply = "EN: Don't call me Christina!\nZH: 谁是克莉丝汀娜！？我从没这么说过！"
    show_toast(test_reply, window_title="测试窗口", process_name="python.exe")
    print("Toast 测试已发送，请查看右下角通知")
