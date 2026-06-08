def ask_kurisu(window_title, process_name):
    situation = f"用户正在用 {process_name}，窗口标题是「{window_title}」"
    relevant = pick_relevant_lines(situation)        # ← 动态挑台词
    dynamic_examples = "\n".join(f"- 「{line}」" for line in relevant)

    messages = [
        {"role": "system", "content": KURISU_PROMPT + "\n\n【参考语气】\n" + dynamic_examples},
        {"role": "user", "content": situation + "，你作为红莉栖，对我说一句话。"}
    ]
    # …后面调用照旧


def ask_kurisu(window_title, process_name):
    # 把台词清单拼成一段，每句一行
    examples = "
".join(f"- {line}" for line in KURISU_LINES)

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": KURISU_PROMPT + "

【参考这些台词的语气】
" + examples},
            {"role": "user", "content":
             f"我现在正在用 {process_name}，窗口标题是「{window_title}」，"
             f"你作为红莉栖，对我说一句话。"}
        ]
    )
    return response.choices[0].message.content


def ask_kurisu(window_title, process_name):
    situation = f"我正在用 {process_name}，窗口标题是「{window_title}」"

    # —— 第一步：让 AI 从台词清单里挑 3 句最贴合当前情境的 ——
    all_lines = "
".join(f"{i}. {line}" for i, line in enumerate(KURISU_LINES))
    pick = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "你是一个台词筛选器。从下面的台词清单里，挑出语气最适合当前情境的3句，只返回这3句台词本身，每句一行，不要加序号和多余的话。"},
            {"role": "user", "content": f"当前情境：{situation}

台词清单：
{all_lines}"}
        ]
    )
    chosen_lines = pick.choices[0].message.content   # AI 挑好的 3 句

    # —— 第二步：拿挑好的台词当范本，正式让红莉栖开口 ——
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": KURISU_PROMPT + "

【参考这些台词的语气】
" + chosen_lines},
            {"role": "user", "content": situation + "，你作为红莉栖，对我说一句话。"}
        ]
    )
    return response.choices[0].message.content
