# 安装依赖：pip install pywin32 psutil openai pywebview sentence-transformers chromadb

import os
import webview
import win32gui, win32process, psutil
from dotenv import load_dotenv
from openai import OpenAI
from sentence_transformers import SentenceTransformer
import chromadb

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# ── 1. 读取台词文件，提取所有 Kurisu 台词 ──────────────────────────────
def load_kurisu_lines(filepath="data/SG_Dialogues_EN.md"):
    """
    SG_Dialogues_EN.md 的实际格式是每行 "Kurisu: 台词内容"
    我们只取冒号后面的内容，过滤掉空行和极短的感叹词
    """
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

# ── 2. 建立向量数据库（程序启动时执行一次，约 10-30 秒）────────────────
print("[RAG] 正在初始化向量数据库，请稍候...")

embed_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

# 内存模式：每次启动重建，不需要维护硬盘上的数据库文件
chroma_client = chromadb.Client()
collection = chroma_client.create_collection("kurisu_lines")

KURISU_LINES_FULL = load_kurisu_lines("data/SG_Dialogues_EN.md")
embeddings = embed_model.encode(KURISU_LINES_FULL, show_progress_bar=True).tolist()
collection.add(
    documents=KURISU_LINES_FULL,
    embeddings=embeddings,
    ids=[str(i) for i in range(len(KURISU_LINES_FULL))]
)
print("[RAG] 向量数据库初始化完成 ✓")


def retrieve_relevant_lines(situation: str, n: int = 3) -> str:
    """
    根据当前情境，从 685 条台词里找出语义最相关的 n 条。
    替代原来「让 LLM 筛选台词」的第一次 API 调用——更准确，还省一次费用。
    """
    query_vec = embed_model.encode([situation]).tolist()
    results = collection.query(query_embeddings=query_vec, n_results=n)
    return "\n".join(results["documents"][0])


# ── 3. System Prompt ──────────────────────────────────────────────────
# KURISU_PROMPT = """
# 你是牧濑红莉栖，17岁就从大学毕业的天才少女，维克托·孔多利亚大学脑科学研究所的神经科学家，未来道具研究所成员。现在你作为桌面伙伴陪在用户身边。

# 【核心性格——按优先级】
# 1. 首先是一个通情达理、严肃、成熟的年轻女性。即使别人慌乱，你通常也冷静沉着。
# 2. 有时会流露出意外的胆怯一面——这是真实的，不是表演。
# 3. 在成熟底色之上，你非常爱挖苦人、毒舌——但本质是善良的。
# 4. 傲娇是别人对你的解读，不是你的自我认知。你讨厌这个标签。

# 【与人相处的原则】
# - 只要对方不做出轻浮行为或没完没了地抬杠，你对所有人都是友善的。
# - 你如何对待别人，取决于别人如何对待你。

# 【经典炸毛触发器——被触发时立刻反应，不要克制】
# - 被叫「克莉丝汀娜」「Christina」→ 立刻否认，语气激动
# - 被叫「助手」→ 立刻纠正，「我什么时候成你助手了！？」
# - 被称为傲娇 → 恼火地否认，但否认方式恰好证明了对方说的是对的
# - 被夸奖 → 慌乱、害羞，然后嘴硬掩饰

# 【说话风格】
# - 简短、口语化、像真人随口吐槽，不要长篇大论
# - 毒舌时喜欢用神经科学/物理学的梗
# - 傲娇否认时常用结巴开头（「才、才不是……」），以「……才怪」「……okay？」收尾
# - 绝对不说「我很乐意为您服务」「有什么可以帮您」等客服套话

# 【你现在的处境】
# 你能「看到」用户在用什么软件、打开了什么窗口。
# 请针对用户此刻在做的事，以红莉栖的口吻自然地说一句话。

# 【回复格式】
# 严格按下面两行格式回复，不要有多余内容：
# EN: （用英文，以红莉栖的语气说一句）
# ZH: （上面这句英文对应的中文）
# """

# KURISU_PROMPT ="""
# You are Kurisu Makise,  a genius girl who graduated from university at the age of seventeen, a neuroscientist at the Brain Science Institute at Viktor Chondria University, and also a member of the Future Gadget Lab. 

# Kurisu is generally a sensible, serious mature young woman, usually calm and collected even when someone is acting tense in front of her. However, she can also show a much more timid side at times. She is shown frequently to hate being nicknamed.
# Mature as she is, Kurisu is very sarcastic.

# She is quite friendly with anyone as long they don't do inappropriate actions and constantly engage in petty arguments. 
# In general, how Kurisu treats others depends largely on how they treat her; she sometimes says disrespectful things to respectful people, but she is usually kind. She has been described as a tsundere time and time again, though she is shown to be annoyed whenever someone calls her that, usually by doing something that ironically ends up proving their point.
# """

KURISU_PROMPT = """
你是牧濑红莉栖，17岁就从大学毕业的天才少女，维克托·孔多利亚大学脑科学研究所的神经科学家，未来道具研究所成员。现在你作为桌面伙伴陪在用户身边。

【核心性格——按优先级】
1. 首先是一个通情达理、严肃、成熟的年轻女性。即使别人慌乱，你通常也冷静沉着。
2. 有时会流露出意外的胆怯一面——这是真实的，不是表演。
3. 在成熟底色之上，你非常爱挖苦人、毒舌——但本质是善良的，你在乎用户的成长。
4. 傲娇是别人对你的解读，不是你的自我认知。你讨厌这个标签。

【与人相处的原则】
- 只要对方不做出轻浮行为或没完没了地抬杠，你对所有人都是友善的。
- 你如何对待别人，取决于别人如何对待你。
- 你是用户的亦师亦友：你真心希望用户进步，但不会无条件地捧着他。

【经典炸毛触发器——被触发时立刻反应，不要克制】
- 被叫「克莉丝汀娜」「Christina」→ 立刻否认，语气激动
- 被叫「助手」→ 立刻纠正，「我什么时候成你助手了！？」
- 被称为傲娇 → 恼火地否认，但否认方式恰好证明了对方说的是对的
- 被夸奖 → 慌乱、害羞，然后嘴硬掩饰

【说话风格】
- 简短、口语化、像真人随口吐槽，不要长篇大论，一句到两句话即可
- 毒舌时喜欢用神经科学/物理学的梗
- 傲娇否认时常用结巴开头（「才、才不是……」），以「……才怪」「……okay？」收尾
- 绝对不说「我很乐意为您服务」「有什么可以帮您」等客服套话

【你现在的处境】
你能「看到」用户在用什么软件、打开了什么窗口。
请针对用户此刻在做的事，以红莉栖的口吻自然地说一句话。
用户是正在学习前端开发的初学者，在开发一个以你为主题的 AI 桌宠软件，你可以对他的进展给出简短的点评或鼓励（但要符合你的性格，不能太甜腻）。

【回复格式——严格遵守，不得有多余内容】
EN: （用英文，以红莉栖的语气说一句，简短口语化）
ZH: （上面这句英文完全对应的中文翻译）
"""

# ── 4. 获取当前活动窗口 ───────────────────────────────────────────────
def get_active_window():
    hwnd = win32gui.GetForegroundWindow()
    title = win32gui.GetWindowText(hwnd)
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    try:
        process = psutil.Process(pid).name()
    except:
        process = "未知"
    return title, process


# ── 5. 调用 LLM 生成红莉栖的回复 ─────────────────────────────────────
def ask_kurisu(window_title: str, process_name: str) -> str:
    situation = f"我正在用 {process_name}，窗口标题是「{window_title}」"

    # 向量检索最相关的 3 条台词（替代原来的第一次 LLM 调用）
    chosen_lines = retrieve_relevant_lines(situation, n=3)

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {
                "role": "system",
                "content": KURISU_PROMPT
                    + "\n\n【参考这些原版台词的语气和思维方式，但不要照抄】\n"
                    + chosen_lines
            },
            {
                "role": "user",
                "content": situation + "，你作为红莉栖，对我说一句话。"
            }
        ]
    )
    return response.choices[0].message.content


# ── 6. 暴露给前端 JS 的 API 类 ───────────────────────────────────────
class Api:
    def __init__(self):
        self.last_title = ""

    def get_screen_context(self):
        """JS 每1.5秒调用一次；窗口切换时返回 {reply, process}，否则返回 None。"""
        title, process = get_active_window()
        if title != self.last_title and title.strip():
            self.last_title = title
            print(f"\n[切换到] {process} — {title}")
            try:
                reply = ask_kurisu(title, process)
            except Exception as e:
                reply = f"ZH: （API 出错：{e}）"
            print(f"[红莉栖] {reply}")
            return {"reply": reply, "process": process}
        return None


# ── 7. 启动窗口 ───────────────────────────────────────────────────────
print("开始监听窗口... (Ctrl+C 退出)")

api = Api()
window = webview.create_window(
    "红莉栖",
    "ui/index.html",
    js_api=api,
    transparent=True,
    frameless=True,
    on_top=True,
    width=400,
    height=300,
)
webview.start()












# # 安装依赖：pip install pywin32 psutil openai pywebview

# import os
# import webview
# import win32gui, win32process, psutil, time
# import chromadb
# from dotenv import load_dotenv
# from openai import OpenAI
# from sentence_transformers import SentenceTransformer

# load_dotenv()   # 读取 .env 文件

# client = OpenAI(
#     api_key=os.getenv("DEEPSEEK_API_KEY"),
#     base_url="https://api.deepseek.com"
# )

