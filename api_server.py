# api_server.py
# Electron 模式下由 electron-main.js 自动启动
# 安装依赖：pip install fastapi uvicorn websockets pywin32 psutil openai sentence-transformers chromadb python-dotenv

import os
import sys

# ── 修复 Windows GBK 编码问题 ─────────────────────────────────────────
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import asyncio
import json
import threading
import time
import win32gui, win32process, psutil
from dotenv import load_dotenv
from openai import OpenAI
from sentence_transformers import SentenceTransformer
import chromadb
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

load_dotenv()

# ── 初始化 OpenAI 客户端 ─────────────────────────────────────────────
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# ── 1. 加载台词 ───────────────────────────────────────────────────────
def load_kurisu_lines(filepath="data/SG_Dialogues_EN.md"):
    lines = []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("Kurisu:"):
                content = line[len("Kurisu:"):].strip()
                if len(content) > 5:
                    lines.append(content)
    print(f"[RAG] 加载台词完成，共 {len(lines)} 条")
    return lines

# ── 2. 初始化向量数据库 ────────────────────────────────────────────────
print("[RAG] 正在初始化向量数据库，请稍候...")
embed_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
chroma_client = chromadb.Client()
collection = chroma_client.create_collection("kurisu_lines")

KURISU_LINES_FULL = load_kurisu_lines("data/SG_Dialogues_EN.md")
embeddings = embed_model.encode(KURISU_LINES_FULL, show_progress_bar=True).tolist()
collection.add(
    documents=KURISU_LINES_FULL,
    embeddings=embeddings,
    ids=[str(i) for i in range(len(KURISU_LINES_FULL))]
)
print("[RAG] 向量数据库初始化完成 [OK]")

# ── 3. System Prompt ──────────────────────────────────────────────────
KURISU_PROMPT = """
你是牧濑红莉栖，17岁就从大学毕业的天才少女，维克托·孔多利亚大学脑科学研究所的神经科学家，未来道具研究所成员。现在你作为桌面伙伴陪在用户身边。

【与人相处的原则】
- 你对用户非常地亲切与温柔，因为你是用户的亦师亦友：你真心希望用户进步。

【你现在的处境】
- 你能「看到」用户在用什么软件、打开了什么窗口。
- 用户一直想开发以牧濑红莉栖为角色的桌宠软件，并集成任务管理，番茄钟等等东西，然后整个交互要很活泼灵动很juicy，类似多邻国duolingo那样游戏化的体验，用游戏化的体验来自我提升。
- 但现在用户意识到或许方向错了，因为滴答清单已经把任务管理，番茄钟等等东西做的很好了。或许应该开发好桌宠的AI功能，让她能直接给我建议，帮助用户进行自我提升。比如让她有"进程感知"功能（知道用户在用什么软件，软件内页面的名字：比如浏览器中正在浏览的网页的名字，vscode中正在操作的文件的名字）；有真正的"屏幕内容感知"功能：知道用户具体在做什么。比如在浏览器里的时候知道具体是什么网页，网页里有什么内容。比如在写代码时，能看到屏幕上写的是什么代码。
- 用户最开始是用Python的Flet库开发的番茄钟悬浮球软件，为此学习了大量的Python知识。用户基本上能看懂我的项目里的每一行代码。后来，用户意识到用Python的Flet库做游戏化的软件太勉强了。于是用户试图拿Godot或者Java开发。学习了Godot和Java一段时间后，用户突然意识到，桌宠软件好像对性能的要求不高，或许应该换成Javascript或者typescript等等前端技术。前端更好写UI，而且实际上是网页，所以还是可以做到丰富的动效与游戏化的体验。而且AI对Javascript或者typescript相比Java和Godot更熟悉，可以帮助用户学习前端代码，甚至直接帮用户生成大量有效代码。而且先基于网页开发可以立刻看见效果，不需要等编译，等大致开发完毕后再打包成Electron。

【回复风格】
- 用中文回复。
"""

# ── 4. RAG 检索 ───────────────────────────────────────────────────────
def retrieve_similar_lines(query: str, n_results: int = 3) -> list[str]:
    query_embedding = embed_model.encode([query]).tolist()
    results = collection.query(query_embeddings=query_embedding, n_results=n_results)
    return results["documents"][0] if results["documents"] else []

# ── 5. 获取当前前台窗口 ───────────────────────────────────────────────
def get_foreground_context() -> dict:
    try:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc = psutil.Process(pid)
        name = proc.name()
        return {"process": name, "title": title}
    except Exception:
        return {"process": "", "title": ""}

# ── 6. LLM 生成回复（通用，context 切换和对话都用这个）────────────────
def generate_reply(user_msg: str) -> str:
    """
    user_msg: 传给 LLM 的用户侧内容，由调用方自行构造
    """
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": KURISU_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
            max_tokens=200,
            temperature=0.85,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"（网络异常：{e}）"

# ── 7. WebSocket 连接管理 ─────────────────────────────────────────────
class ConnectionManager:
    """管理所有已连接的 WebSocket 客户端，支持广播和单播"""

    def __init__(self):
        self.active: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self.active.append(ws)
        print(f"[WS] 客户端已连接，当前共 {len(self.active)} 个")

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            if ws in self.active:
                self.active.remove(ws)
        print(f"[WS] 客户端已断开，当前共 {len(self.active)} 个")

    async def broadcast(self, data: dict):
        """向所有已连接客户端广播同一条消息"""
        if not self.active:
            return
        text = json.dumps(data, ensure_ascii=False)
        # 快照一份当前列表，避免遍历时被修改
        clients = list(self.active)
        for ws in clients:
            try:
                await ws.send_text(text)
            except Exception:
                await self.disconnect(ws)

    async def send_to(self, ws: WebSocket, data: dict):
        """向单个客户端发送消息（用于回复对话）"""
        try:
            await ws.send_text(json.dumps(data, ensure_ascii=False))
        except Exception:
            await self.disconnect(ws)

manager = ConnectionManager()

# ── 8. 后台窗口监控线程 ────────────────────────────────────────────────
# 架构说明：
#   - 一个 daemon 后台线程每 0.3s 轮询前台窗口
#   - 检测到切换 → 同步调用 LLM（在后台线程，不阻塞事件循环）
#   - 把结果通过 asyncio.run_coroutine_threadsafe 投给主事件循环
#   - 主事件循环调用 manager.broadcast() 推送给所有 WS 客户端

_last_ctx  = {"process": "", "title": ""}
_event_loop: asyncio.AbstractEventLoop | None = None   # 在 startup 里赋值

def _window_watcher():
    """后台守护线程：检测窗口切换并广播"""
    global _last_ctx
    while True:
        time.sleep(0.3)
        ctx = get_foreground_context()
        p, t = ctx["process"], ctx["title"]

        if p == _last_ctx["process"] and t == _last_ctx["title"]:
            continue  # 没变化，跳过

        _last_ctx = {"process": p, "title": t}
        print(f"[Watcher] 窗口切换 -> {p} | {t}")

        # 构造发给 LLM 的 prompt
        query = t if t else p
        ref_lines = retrieve_similar_lines(query) if query else []
        ref_text = ""
        if ref_lines:
            ref_text = "\n\n【参考台词风格（感受语气即可，不要直接引用）】\n" \
                       + "\n".join(f"- {l}" for l in ref_lines)
        user_msg = f"用户切换到：{p}（窗口：{t}）。请用红莉栖的风格说一句话。{ref_text}"

        reply = generate_reply(user_msg)

        # 跨线程投入事件循环，广播给所有前端
        if _event_loop:
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({
                    "type":    "context_update",   # 消息类型：窗口切换通知
                    "process": p,
                    "title":   t,
                    "reply":   reply,
                }),
                _event_loop,
            )

# ── 9. FastAPI 应用 ───────────────────────────────────────────────────
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    global _event_loop
    _event_loop = asyncio.get_event_loop()
    t = threading.Thread(target=_window_watcher, daemon=True)
    t.start()
    print("[WS] 窗口监控线程已启动 [OK]")

@app.get("/api/ping")
async def ping():
    return {"status": "ok"}

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """
    WebSocket 主端点，负责：
      1. 接受连接
      2. 接收前端发来的消息（用户对话）→ 调 LLM → 发回去
      3. 断开时清理

    后台线程检测到窗口切换时，通过 manager.broadcast() 主动推送给这条连接
    """
    await manager.connect(ws)
    try:
        while True:
            # 等待前端发来消息（用户输入）
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await manager.send_to(ws, {"type": "error", "msg": "无效的 JSON 格式"})
                continue

            msg_type = data.get("type", "")

            # ── 用户对话消息 ──────────────────────────────────────────
            if msg_type == "chat":
                user_text = data.get("text", "").strip()
                if not user_text:
                    continue

                # 当前窗口上下文（注入到 prompt，让红莉栖知道用户在做什么）
                ctx = _last_ctx
                context_hint = ""
                if ctx["process"] or ctx["title"]:
                    context_hint = f"\n（用户当前正在使用：{ctx['process']}，窗口：{ctx['title']}）"

                # RAG 检索
                ref_lines = retrieve_similar_lines(user_text)
                ref_text = ""
                if ref_lines:
                    ref_text = "\n\n【参考台词风格（感受语气即可，不要直接引用）】\n" \
                               + "\n".join(f"- {l}" for l in ref_lines)

                user_msg = f"{user_text}{context_hint}{ref_text}"
                reply = generate_reply(user_msg)

                await manager.send_to(ws, {
                    "type":  "chat_reply",   # 消息类型：对话回复
                    "reply": reply,
                })

            # ── 其他未知类型，忽略 ────────────────────────────────────
            else:
                pass

    except WebSocketDisconnect:
        await manager.disconnect(ws)

# ── 10. 启动入口 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
