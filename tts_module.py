# tts_module.py — 语音播报模块
# 依赖：pip install edge-tts asyncio
# edge-tts 免费，音质好，有日语/中文/英文声库
# 红莉栖用：zh-CN-XiaoxiaoNeural（中文女声，成熟知性）
#           en-US-AriaNeural（英文女声，备用）

import asyncio
import edge_tts
import tempfile
import os
import subprocess

# 你可以换成别的声音，完整列表：edge-tts --list-voices
ZH_VOICE = "zh-CN-XiaoxiaoNeural"
EN_VOICE = "en-US-AriaNeural"


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


async def _speak_async(text: str, voice: str):
    """
    异步生成语音并播放。
    
    修复说明：
      原实现用 os.system('start /min wmplayer ...') 调用 Windows Media Player GUI，
      会弹出 wmplayer.exe 窗口，且因为 /play /close 参数在现代 Windows 上极不稳定，
      文件还没准备好就被读取，导致 wmplayer 1秒内闪退。
      
      修复方案：改用 PowerShell + WMPlayer.OCX COM 对象在后台静默播放 mp3，
      - 完全不创建任何可见窗口（-WindowStyle Hidden + CREATE_NO_WINDOW）
      - 等待 edge-tts 把 mp3 写完后再播放，不会出现文件未就绪的问题
      - 播放结束后自动清理临时文件
    """
    if not text:
        return

    communicate = edge_tts.Communicate(text, voice)

    # 写到临时 mp3 文件（delete=False，手动控制生命周期）
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
        tmp_path = f.name

    # 等待 edge-tts 把音频完整写入磁盘，再交给播放器
    await communicate.save(tmp_path)

    # 用 PowerShell + WMPlayer.OCX COM 静默播放
    # 注意：tmp_path 里可能有反斜杠，PowerShell 字符串用单引号包裹即可
    ps_script = (
        "$wmp = New-Object -ComObject WMPlayer.OCX; "
        "$wmp.settings.autoStart = $true; "
        "$wmp.settings.volume = 80; "
        "$media = $wmp.newMedia('" + tmp_path.replace("'", "''") + "'); "
        "$wmp.currentPlaylist = $wmp.newPlaylist('tts', ''); "
        "$wmp.currentPlaylist.appendItem($media); "
        "$wmp.controls.play(); "
        "Start-Sleep -Milliseconds 500; "
        "$dur = $media.duration; "
        "if ($dur -le 0) { Start-Sleep -Seconds 1; $dur = $media.duration }; "
        "if ($dur -gt 0) { Start-Sleep -Seconds ([math]::Ceiling($dur + 0.5)) } "
        "else { Start-Sleep -Seconds 5 }; "
        "$wmp.controls.stop(); "
        "[System.Runtime.Interopservices.Marshal]::ReleaseComObject($wmp) | Out-Null"
    )

    tmp_path_to_delete = tmp_path
    try:
        proc = subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-WindowStyle", "Hidden",
                "-Command", ps_script,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,  # Windows 专属：彻底不创建窗口
        )
        # 等待播放完成（最多 60 秒兜底，避免卡死）
        proc.wait(timeout=60)
    except subprocess.TimeoutExpired:
        proc.kill()
    except Exception as e:
        print(f"[TTS 播放警告] {e}")
    finally:
        # 播放结束后清理临时 mp3
        try:
            os.remove(tmp_path_to_delete)
        except OSError:
            pass


def speak(reply: str, lang: str = "zh"):
    """
    同步入口，供 main.py 直接调用。
    lang="zh" 读中文，lang="en" 读英文，lang="both" 先英后中。
    """
    en_text, zh_text = _parse_reply(reply)
    try:
        if lang == "en" and en_text:
            asyncio.run(_speak_async(en_text, EN_VOICE))
        elif lang == "both":
            if en_text:
                asyncio.run(_speak_async(en_text, EN_VOICE))
            if zh_text:
                asyncio.run(_speak_async(zh_text, ZH_VOICE))
        else:  # 默认读中文
            if zh_text:
                asyncio.run(_speak_async(zh_text, ZH_VOICE))
    except Exception as e:
        print(f"[TTS 错误] {e}")


# 单独测试用
if __name__ == "__main__":
    test_reply = "EN: Don't call me Christina!\nZH: 谁是克莉丝汀娜！"
    speak(test_reply, lang="zh")
    print("TTS 测试完成")
