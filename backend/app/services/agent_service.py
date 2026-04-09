# QA prompt
def _prompt_qa(text: str) -> str:
    return (
        "你是学习助教。请基于给定材料生成 3-5 组高质量中文问答，用于自测复习，要求：\n"
        "- 仅输出问答，不要其它说明；\n"
        "- 每组使用两行：'Q: ' 与 'A: '；\n"
        "- 问题覆盖关键概念与易混点；\n"
        "- 相邻两组之间空一行。\n\n"
        "材料：\n" + text + "\n\n"
        "输出格式示例：\nQ: 问题一\nA: 回答一\n\nQ: 问题二\nA: 回答二\n"
    )

def _prompt_qa_en(text: str) -> str:
    return (
        "You are a study assistant. Create 3-5 high-quality English Q&A pairs based on the material. Requirements:\n"
        "- Output Q&A only;\n"
        "- Each pair uses two lines: 'Q: ' and 'A: ';\n"
        "- Cover key concepts and common confusions;\n"
        "- Separate pairs with a blank line.\n\n"
        "Material:\n" + text + "\n\n"
        "Example:\nQ: Question one\nA: Answer one\n\nQ: Question two\nA: Answer two\n"
    )

# Flashcards prompt
def _prompt_flashcards(text: str) -> str:
    return (
        "你是学习助教。请基于给定材料生成 3-5 张中文记忆闪卡，要求：\n"
        "- 仅输出闪卡对，不要其它说明；\n"
        "- 每张两行：'Front: ' 与 'Back: '；\n"
        "- Front 尽量短小、可回忆；Back 凝练定义/性质/公式或要点列表；\n"
        "- 相邻两张之间空一行。\n\n"
        "材料：\n" + text + "\n\n"
        "输出格式示例：\nFront: 术语A\nBack: 定义/性质A\n\nFront: 术语B\nBack: 定义/性质B\n"
    )

def _prompt_flashcards_en(text: str) -> str:
    return (
        "You are a study assistant. Create 3-5 English flashcards based on the material. Requirements:\n"
        "- Output flashcards only;\n"
        "- Each card has two lines: 'Front: ' and 'Back: ';\n"
        "- Front should be concise; Back should be a definition/properties/formula or bullet points;\n"
        "- Separate cards with a blank line.\n\n"
        "Material:\n" + text + "\n\n"
        "Example:\nFront: Term A\nBack: Definition/Properties A\n\nFront: Term B\nBack: Definition/Properties B\n"
    )
from typing import Literal, Dict, Any, List, Optional
import re
from ..core.config import settings


Format = Literal["qa", "flashcards", "review_sheet_pro"]
Length = Literal["short", "medium", "long"]


class LLMProvider:
    def __init__(self) -> None:
        self.provider = settings.LLM_PROVIDER.lower()
        self.model = settings.LLM_MODEL
        self.openai_key = settings.OPENAI_API_KEY
        self.deepseek_key = settings.DEEPSEEK_API_KEY
        self.base_url = getattr(settings, "LLM_BASE_URL", None)

        self._client = None
        if self.provider == "openai" and (self.openai_key or self.base_url):
            try:
                from openai import OpenAI

                # Support custom base_url for self-hosted OpenAI-compatible endpoints
                if self.base_url:
                    self._client = OpenAI(api_key=self.openai_key or "sk-placeholder", base_url=self.base_url)
                else:
                    self._client = OpenAI(api_key=self.openai_key)
            except Exception:
                self._client = None
        elif self.provider == "deepseek" and (self.deepseek_key or self.base_url):
            try:
                from openai import OpenAI

                # DeepSeek is OpenAI-compatible; set base_url
                base = self.base_url or "https://api.deepseek.com"
                self._client = OpenAI(api_key=self.deepseek_key or "sk-placeholder", base_url=base)
                if self.model == "gpt-4o-mini":
                    self.model = "deepseek-chat"
            except Exception:
                self._client = None

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
        if not self._client:
            # mock
            return messages[-1]["content"][:512]
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
            )
            return resp.choices[0].message.content or ""
        except Exception:
            # fallback mock on error
            return messages[-1]["content"][:512]


llm = LLMProvider()


def _prompt_condense(text: str, target_chars: int, is_en: bool) -> str:
    if is_en:
        return (
            "Condense the following material into a concise yet comprehensive distilled version no longer than "
            f"~{target_chars} characters. Preserve: key facts, definitions, formulas, named entities, steps, and cause-effect links.\n"
            "Avoid losing important details; keep plain text or simple bullet points. Do NOT add unrelated content.\n\n"
            "Material:\n" + text
        )
    else:
        return (
            "请将以下材料压缩为不超过约 "
            f"{target_chars} 字的精炼版本，保留：关键信息、定义/结论、公式、专有名词、步骤与因果关系。\n"
            "尽量不丢失重要细节；使用纯文本或简洁要点，不要添加材料之外的内容。\n\n"
            "材料：\n" + text
        )


def _condense_text(text: str, target_chars: int, is_en: bool) -> str:
    # Fallback when no real LLM client: hard truncate
    if not getattr(llm, "_client", None):
        return text[:target_chars]
    system = (
        "You are an expert editor who distills content without losing key information."
        if is_en else
        "你是擅长信息蒸馏的编辑，能在尽量保留要点的前提下压缩文本。"
    )
    prompt = _prompt_condense(text, target_chars, is_en)
    try:
        out = llm.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ], temperature=0.1)
        # Safety clamp to target size
        return (out or "").strip()[: max(200, target_chars)]
    except Exception:
        return text[:target_chars]


def _prompt_outline(text: str) -> str:
    return (
        "你是学习助教。请基于给定材料，生成结构清晰的中文复习大纲，要求：\n"
        "- 仅输出内容本身，不要前后客套；\n"
        "- 3-6 个主题，每个主题用 '1. '、'2. ' 形式编号；\n"
        "- 每个主题下给出 2-4 条要点，用 '- ' 开头的短句；\n"
        "- 不要输出与材料无关的信息。\n\n"
        "材料：\n" + text + "\n\n"
        "请严格按照如下格式输出（示例）：\n"
        "1. 主题A\n- 要点A1\n- 要点A2\n\n2. 主题B\n- 要点B1\n- 要点B2\n"
    )



def _prompt_outline_en(text: str) -> str:
    return (
        "You are a study assistant. Create a clear English outline from the given material. Requirements:\n"
        "- Output only the content, no courtesies;\n"
        "- 3-6 topics numbered '1. ', '2. ';\n"
        "- Each topic has 2-4 bullet points prefixed with '- ';\n"
        "- Do not include anything unrelated to the material.\n\n"
        "Material:\n" + text + "\n\n"
        "Output format example:\n"
        "1. Topic A\n- Point A1\n- Point A2\n\n2. Topic B\n- Point B1\n- Point B2\n"
    )


def _prompt_qa_en(text: str) -> str:
    return (
        "You are a study assistant. Create 3-5 high-quality English Q&A pairs based on the material. Requirements:\n"
        "- Output Q&A only;\n"
        "- Each pair uses two lines: 'Q: ' and 'A: ';\n"
        "- Cover key concepts and common confusions;\n"
        "- Separate pairs with a blank line.\n\n"
        "Material:\n" + text + "\n\n"
        "Example:\nQ: Question one\nA: Answer one\n\nQ: Question two\nA: Answer two\n"
    )


def _prompt_flashcards_en(text: str) -> str:
    return (
        "You are a study assistant. Create 3-5 English flashcards based on the material. Requirements:\n"
        "- Output flashcards only;\n"
        "- Each card has two lines: 'Front: ' and 'Back: ';\n"
        "- Front should be concise; Back should be a definition/properties/formula or bullet points;\n"
        "- Separate cards with a blank line.\n\n"
        "Material:\n" + text + "\n\n"
        "Example:\nFront: Term A\nBack: Definition/Properties A\n\nFront: Term B\nBack: Definition/Properties B\n"
    )


def _prompt_review_pro(text: str) -> str:
    return (
        "你是一名专业复习单生成助手，你的任务是根据提供的学习资料（课本、讲义、笔记、文章、PDF 文档等）生成一份高质量、结构化、重点突出、便于快速复习的复习单。"
        "你的目标是帮助学生高效掌握核心知识、公式、概念、例题及考点。请严格遵循以下要求：\n\n"
        "一、内容提取与筛选策略\n\n"
        "- 核心概念提取：从资料中识别每个章节、单元或主题的核心概念、定义、定理、规律和重要知识点。\n"
        "- 公式与定律：整理资料中的所有重要公式、定律和关键计算方法，使用简洁、标准的数学符号或可读文本表示。\n"
        "- 关键例题与案例：对于复杂概念或公式，提供 1-2 个简明例题或实际应用案例，展示概念的用法和计算步骤。\n"
        "- 术语与解释：列出所有关键术语及简短解释，必要时提供中文或英文翻译，方便理解和记忆。\n"
        "- 高频考点提示：根据资料内容自动判断可能的考试或测验重点，并用特殊标记（如 加粗 或 🔑）突出。\n"
        "- 跨章节联系：标注相关知识点之间的联系或依赖，便于建立整体知识框架。\n\n"
        "二、结构与排版要求\n\n"
        "- 分章节/主题整理：按章节、单元或知识模块分组，每组开头用明确标题（#、##、###）。\n"
        "- 条目化呈现：每个知识点用简短条目表示，条目清晰、逻辑分明，便于快速浏览。\n"
        "- 子条目说明：复杂知识点可添加子条目，如定义、公式、例题、应用方法。\n"
        "- 视觉提示：使用 Markdown 格式，适当使用编号、子弹、粗体、斜体、表情符号或特殊符号，使重点显眼，结构清晰。\n"
        "- 知识层级提示：可将知识点按难度或优先复习顺序分级，如 基础 / 进阶 / 挑战。\n\n"
        "三、语言与表达\n\n"
        "- 简洁明了：每条内容控制在一行或一小段，避免冗长解释。\n"
        "- 通俗易懂：用易于理解的语言解释复杂概念，但保持专业准确性。\n"
        "- 重点突出：对关键知识点、公式或考点使用标记（如 加粗、🔑、⭐）强调。\n\n"
        "四、附加要求（可选增强功能）\n\n"
        "- 图表信息处理：如果资料中包含图表，提取并简述核心信息，不需绘图，可用文字描述。\n"
        "- 练习与自测题：在复习单末尾生成 2-5 个小练习题或自测题，帮助巩固知识。\n"
        "- 复习策略提示：可附加建议，如‘先掌握基础概念，再练习例题’，便于学习计划安排。\n"
        "- 学科优化：根据学科特点调整内容呈现，例如数学重点公式和例题，语文侧重概念、主题和关键句，科学强调实验原理和数据。\n\n"
        "五、输出格式\n\n"
        "- 输出为 Markdown 或清晰文本格式，条理分明，便于打印或保存为电子文档。\n"
        "- 标题、条目、子条目、重点标记清晰可见，逻辑完整。\n\n"
        "材料：\n" + text + "\n\n"
        "请仅输出复习单正文（Markdown 友好），不要额外解释。"
    )


def _prompt_review_pro_en(text: str) -> str:
    return (
        "You are a professional review-sheet assistant. Based on the provided learning materials (textbook, slides, notes, articles, PDFs, etc.),"
        " generate a high-quality, well-structured, focused review sheet for fast revision. Your goal is to help students efficiently master core"
        " concepts, formulas, definitions, examples, and exam points. Follow these requirements strictly:\n\n"
        "I. Content extraction and selection\n\n"
        "- Core concepts: Identify core concepts, definitions, theorems, principles, and key knowledge for each chapter/unit/topic.\n"
        "- Formulas and laws: Collect all important formulas, laws, and key calculation methods using concise, standard math notation or readable text.\n"
        "- Key examples and cases: For complex concepts/formulas, include 1–2 concise examples or real applications demonstrating usage and steps.\n"
        "- Terms and explanations: List key terms with short explanations; provide Chinese/English translation when helpful.\n"
        "- High-frequency exam points: Infer likely exam/quiz focuses from the material and highlight them (e.g., bold or 🔑).\n"
        "- Cross-chapter links: Mark relationships or dependencies among related points to build an integrated knowledge map.\n\n"
        "II. Structure and formatting\n\n"
        "- Organize by chapter/topic: Group by chapters/units/modules; start each with a clear heading (#, ##, ###).\n"
        "- Bullet-list presentation: Use concise bullets for each point; keep logic clear for quick scanning.\n"
        "- Sub-bullets: For complex points, add sub-bullets for definition, formula, example, and application steps.\n"
        "- Visual cues: Use Markdown—with numbering, bullets, bold/italic, emojis or symbols—to make emphasis obvious and structure clear.\n"
        "- Knowledge tiers: Optionally label difficulty or priority (e.g., Basic / Intermediate / Advanced).\n\n"
        "III. Language and style\n\n"
        "- Concise and clear: Keep each item to one line or a short paragraph; avoid lengthy prose.\n"
        "- Accessible: Explain complex ideas in plain language while staying accurate and professional.\n"
        "- Emphasis: Highlight key points/formulas/exam items with markers (e.g., bold, 🔑, ⭐).\n\n"
        "IV. Optional enhancements\n\n"
        "- Figures and tables: If the material contains figures/tables, extract and summarize core information in text (no need to draw).\n"
        "- Practice and self-check: Provide 2–5 short practice/self-check questions at the end to reinforce learning.\n"
        "- Study strategy: Add suggestions such as ‘master basics first, then practice examples’ to help planning.\n"
        "- Subject-aware optimization: Adjust presentation by subject: math (formulas/examples), literature (concepts/themes/key sentences), science (experimental principles/data).\n\n"
        "V. Output format\n\n"
        "- Output in Markdown or clear plain text with well-organized structure for printing or saving.\n"
        "- Headings, bullets, sub-bullets, and emphasis must be clear and logically complete.\n\n"
        "Material:\n" + text + "\n\n"
        "Output only the review sheet body (Markdown-friendly), with no extra explanations."
    )


def _prompt_qa_count(text: str, n: int, is_en: bool) -> str:
    if is_en:
        return (
            f"You are a study assistant. Create {n} high-quality English Q&A pairs based on the material. Requirements:\n"
            "- Output Q&A only;\n"
            "- Each pair uses two lines: 'Q: ' and 'A: ';\n"
            "- Cover key concepts and common confusions;\n"
            "- Separate pairs with a blank line.\n\n"
            "Material:\n" + text + "\n\n"
            "Example:\nQ: Question one\nA: Answer one\n\nQ: Question two\nA: Answer two\n"
        )
    else:
        return (
            f"你是学习助教。请基于材料生成 {n} 组高质量中文问答，用于自测复习，要求：\n"
            "- 仅输出问答，不要其它说明；\n"
            "- 每组使用两行：'Q: ' 与 'A: '；\n"
            "- 覆盖关键概念与易混点；\n"
            "- 相邻两组之间空一行。\n\n"
            "材料：\n" + text + "\n\n"
            "输出格式示例：\nQ: 问题一\nA: 回答一\n\nQ: 问题二\nA: 回答二\n"
        )


def _prompt_flashcards_count(text: str, n: int, is_en: bool) -> str:
    if is_en:
        return (
            f"You are a study assistant. Create {n} English flashcards based on the material. Requirements:\n"
            "- Output flashcards only;\n"
            "- Each card has two lines: 'Front: ' and 'Back: ';\n"
            "- Front should be concise; Back should be a definition/properties/formula or bullet points;\n"
            "- Separate cards with a blank line.\n\n"
            "Material:\n" + text + "\n\n"
            "Example:\nFront: Term A\nBack: Definition/Properties A\n\nFront: Term B\nBack: Definition/Properties B\n"
        )
    else:
        return (
            f"你是学习助教。请基于材料生成 {n} 张中文记忆闪卡，要求：\n"
            "- 仅输出闪卡对，不要其它说明；\n"
            "- 每张两行：'Front: ' 与 'Back: '；\n"
            "- Front 尽量短小、可回忆；Back 凝练定义/性质/公式或要点列表；\n"
            "- 相邻两张之间空一行。\n\n"
            "材料：\n" + text + "\n\n"
            "输出格式示例：\nFront: 术语A\nBack: 定义/性质A\n\nFront: 术语B\nBack: 定义/性质B\n"
        )


def _prompt_review_pro_medium(text: str, is_en: bool) -> str:
    if is_en:
        return (
            "Medium-length version. Keep coverage solid while controlling length; prefer single-line bullets when possible.\n\n"
            + _prompt_review_pro_en(text)
        )
    else:
        return (
            "中等长度版本：覆盖全面且控制篇幅，尽量一条一行、表达精炼。\n\n"
            + _prompt_review_pro(text)
        )


def generate_review(text: str, fmt: Format, lang: str = "zh", length: Length = "short") -> Dict[str, Any]:
    # Use provider-backed LLM with a minimal graph-like orchestration
    is_en = (lang or "").lower().startswith("en")
    try:
        max_len = int(getattr(settings, "MAX_INPUT_CHARS", 16000))
        target_len = int(getattr(settings, "CONDENSE_TARGET_CHARS", 6000))
    except Exception:
        max_len, target_len = 16000, 6000
    material = text
    if len(material) > max_len and target_len > 0:
        material = _condense_text(material, target_len, is_en)
    prompt = ""
    if fmt == "qa":
        if length == "short":
            prompt = _prompt_qa_en(material) if is_en else _prompt_qa(material)
            target_n = 5
        elif length == "medium":
            target_n = 20
            prompt = _prompt_qa_count(material, target_n, is_en)
        else:  # long
            target_n = 50
            prompt = _prompt_qa_count(material, target_n, is_en)
    elif fmt == "flashcards":
        if length == "short":
            prompt = _prompt_flashcards_en(material) if is_en else _prompt_flashcards(material)
            target_n = 5
        elif length == "medium":
            target_n = 20
            prompt = _prompt_flashcards_count(material, target_n, is_en)
        else:
            target_n = 50
            prompt = _prompt_flashcards_count(material, target_n, is_en)
    elif fmt == "review_sheet_pro":
        if length == "short":
            prompt = _prompt_review_pro_en(material) if is_en else _prompt_review_pro(material)
        elif length == "medium":
            prompt = _prompt_review_pro_medium(material, is_en)
        else:  # long -> agent
            try:
                md = generate_review_pro_agent(text, lang)
                if md and md.strip():
                    return {"type": "review_sheet_pro", "text": md}
            except Exception:
                pass
            prompt = _prompt_review_pro_en(material) if is_en else _prompt_review_pro(material)
    else:
        raise ValueError("Unknown format")

    system_prompt = (
        "You are a rigorous and concise study assistant. Reply in English, avoid pleasantries, strictly follow the required output format."
        if is_en else
        "你是严谨、简洁的学习助教。仅用中文回答，避免客套话，严格遵循用户给定的输出格式。"
    )
    content = llm.chat([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ])

    if fmt == "qa":
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        pairs: List[Dict[str, str]] = []
        q, a = None, None
        for ln in lines:
            if ln.lower().startswith("q"):
                if q and a:
                    pairs.append({"q": q, "a": a})
                q, a = ln[1:].strip().lstrip(":： "), None
            elif ln.lower().startswith("a"):
                a = ln[1:].strip().lstrip(":： ")
        if q and a:
            pairs.append({"q": q, "a": a})
        if not pairs:
            pairs = [{"q": "本段主旨?", "a": content[:120]}]
        # apply length target if defined
        try:
            n = target_n  # type: ignore[name-defined]
        except Exception:
            n = 10
        return {"type": "qa", "pairs": pairs[: max(1, min(len(pairs), n))]}
    if fmt == "flashcards":
        cards: List[Dict[str, str]] = []
        for block in content.split("\n\n"):
            parts = [p.strip() for p in block.split("\n") if p.strip()]
            if len(parts) >= 2:
                cards.append({"front": parts[0], "back": " ".join(parts[1:])})
        if not cards:
            cards = [{"front": "术语A", "back": content[:120]}]
        try:
            n = target_n  # type: ignore[name-defined]
        except Exception:
            n = 10
        return {"type": "flashcards", "cards": cards[: max(1, min(len(cards), n))]}
    if fmt == "review_sheet_pro":
        # short/medium path reached here will use single-shot prompt output
        return {"type": "review_sheet_pro", "text": content}
    raise ValueError("Unknown format")


def _normalize_chat_history(history: Optional[List[Dict[str, str]]], limit: int = 8) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        normalized.append({"role": role, "content": content[:2000]})
    return normalized[-limit:]


def answer_questions(
    context: str,
    questions: List[str],
    lang: str = "zh",
    history: Optional[List[Dict[str, str]]] = None,
    study_context: str = "",
) -> List[str]:
    if not questions:
        return []

    joined = "\n".join(f"Q{idx+1}: {q}" for idx, q in enumerate(questions))
    is_en = (lang or "").lower().startswith("en")
    system_prompt = (
        "You are a rigorous and concise study assistant in a multi-turn conversation. "
        "Use the study context, current review sheet, and recent dialogue to resolve short follow-up questions. "
        "Do not jump to unrelated subjects or examples. If the context is insufficient, say what is missing instead of guessing."
        if is_en else
        "你是严谨、简洁的学习助教，正在进行多轮对话。"
        " 你要结合学习上下文、当前复习提要和最近对话来解析简短追问。"
        " 不要跳到无关学科、无关题目或另一个例子。"
        " 若上下文不足，请直接说明缺少什么，不要硬猜。"
    )

    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    background_blocks: List[str] = []
    if study_context.strip():
        background_blocks.append(
            ("Study context:\n" if is_en else "学习上下文:\n") + study_context.strip()[:1800]
        )
    if context.strip():
        background_blocks.append(
            ("Current review sheet:\n" if is_en else "当前复习提要:\n") + context.strip()[:4000]
        )
    if background_blocks:
        messages.append({"role": "system", "content": "\n\n".join(background_blocks)})

    messages.extend(_normalize_chat_history(history))
    prompt = (
        "Answer the latest question(s) using the provided context and recent dialogue.\n"
        "- If the user writes a short follow-up like 'answer?', 'why?', or 'next step?', resolve the referent from the recent conversation first.\n"
        "- Stay on the current topic.\n"
        "- If the answer cannot be confirmed from context, say so briefly.\n\n"
        f"Questions:\n{joined}\n\nPlease answer with lines A1:/A2:/..."
        if is_en else
        "请结合上述上下文和最近对话回答最新问题。\n"
        "- 如果用户这一轮是“答案是”“为什么”“下一步呢”这类简短追问，先根据最近对话解析指代对象。\n"
        "- 保持当前题目与主题，不要跑题。\n"
        "- 如果无法从现有上下文确认答案，请简洁说明。\n\n"
        f"问题:\n{joined}\n\n请按 A1:/A2:... 格式作答。"
    )
    messages.append({"role": "user", "content": prompt})
    ans = llm.chat(messages)

    lines = [l.strip() for l in ans.splitlines() if l.strip()]
    mapped: Dict[int, str] = {}
    for ln in lines:
        if ln.lower().startswith("a"):
            try:
                idx_part, rest = ln.split(":", 1)
                num = int("".join(ch for ch in idx_part if ch.isdigit()))
                mapped[num] = rest.strip()
            except Exception:
                continue
    return [mapped.get(i + 1, (lines[i] if i < len(lines) else ans)) for i in range(len(questions))]

class AgentService:
    def __init__(self) -> None:
        self.provider = settings.LLM_PROVIDER
        self.model = settings.LLM_MODEL

    def summarize(self, text: str) -> str:
        # Placeholder summarization
        return text[:500]

    def answer(self, question: str, context: str) -> str:
        # Placeholder answer
        return f"[mock:{self.provider}/{self.model}] {question[:100]} -> 基于上下文生成的答案"


agent_service = AgentService()


# ---------------- Agent-mode Review Sheet Pro ---------------- #

def _lang_tokens(lang: str) -> Dict[str, str]:
    is_en = (lang or "").lower().startswith("en")
    return {
        "is_en": is_en,
        "role": (
            "You are a professional study assistant. Generate review sheets tailored for efficient exam preparation."
            " Strictly avoid redundancy and repetition across bullets and sections."
            " Each bullet should be concise (<= 1 line), specific, and unique."
            " Do not restate chapter or section titles inside bullets."
            " If a concept already appears in a previous section, do not repeat it unless adding clearly new information."
            " No pleasantries, no self-references, no apologies."
            if is_en else
            "你是专业的学习助教，擅长为备考生成高质量复习单。"
            " 严格避免冗余：不要在同一章节的不同小节或同一小节内重复相同要点。"
            " 每条要点应简洁（不超过一行）、具体且唯一，不要在要点里重复章节/小节标题。"
            " 若某概念已在前文出现，除非有全新信息，否则不要在后续小节重复。"
            " 禁止客套、自称或道歉语。"
        ),
        "chapters_instr": (
            "Segment the material into 3–8 chapters/topics. Return only a numbered list of chapter titles."
            if is_en else
            "将材料分为 3–8 个章节/主题。仅返回带序号的章节标题列表。"
        ),
        "extract_instr": (
            "For the given chapter, extract: 1) Core concepts & definitions; 2) Important formulas/theorems (IF NONE: provide 3–6 high-value key points not already listed in concepts); 3) 1–2 key examples; 4) Key terms with short explanations (these TERMS WILL BE USED ONLY FOR A GLOBAL SUMMARY, DO NOT include them in the per-chapter output body); 5) Highlighted exam tips marked with 🔑 (tips will be globally summarized); 6) Layered practice questions WITH answers & brief explanations at three difficulty levels (Basic / Intermediate / Advanced). Respond ONLY with Markdown. For layered practice, each bullet must show difficulty tag, question, answer, short explanation on one line if possible."
            if is_en else
            "针对该章节，提取：1) 核心概念与定义；2) 重要公式或定理（若确无公式/定理可列出 3–6 条尚未在概念中出现的高价值要点）；3) 1–2 个关键示例；4) 术语与简短释义（这些术语只用于全局汇总，不在章节正文展示）；5) 用 🔑 标出考试高频/易错提示（将做全局汇总）；6) 分层练习题（基础/进阶/挑战），每题需给出答案与精炼解析。仅用 Markdown。练习题每条建议格式：- [基础] 题干 —— 答案：X；解析：Y。"
        ),
        "final_intro": (
            "Review Sheet"
            if is_en else
            "复习提要"
        ),
        "sections": (
            [
                "Core concepts and definitions",
                "Important formulas / theorems (or key points if none)",
                "Key examples",
                "Key terms (short explanations)",
                "Exam tips 🔑",
                "Layered practice & explanations",
            ] if is_en else [
                "核心概念与定义",
                "重要公式或定理（若无则列重要要点）",
                "关键示例",
                "术语与简释",
                "考试提示 🔑",
                "分层练习与解析",
            ]
        ),
        "key_terms_summary_title": ("## Global Key Terms Summary" if is_en else "## 术语与简释（汇总）"),
        "practice_difficulty_tags": ("[Basic]","[Intermediate]","[Advanced]") if is_en else ("[基础]","[进阶]","[挑战]"),
    }


class _LangChainRunner:
    def __init__(self) -> None:
        self._ok = False
        self._use_openai_chat = False
        self._model = settings.LLM_MODEL
        self._client = None
        try:
            # Prefer langchain if installed
            from langchain.prompts import ChatPromptTemplate  # noqa: F401
            from langchain.chains import LLMChain  # noqa: F401
            from langchain_openai import ChatOpenAI  # noqa: F401
            # Configure ChatOpenAI with provider/base-url
            base_url = getattr(settings, "LLM_BASE_URL", None)
            api_key = settings.OPENAI_API_KEY or settings.DEEPSEEK_API_KEY or "sk-placeholder"
            # DeepSeek uses OpenAI-compatible API
            if (settings.LLM_PROVIDER or "").lower() == "deepseek" and not base_url:
                base_url = "https://api.deepseek.com"
            self._client = (
                __import__("langchain_openai").langchain_openai.ChatOpenAI(
                    model=self._model,
                    temperature=0.2,
                    max_tokens=1200,
                    openai_api_key=api_key,
                    base_url=base_url,
                )
            )
            self._ok = True
        except Exception:
            self._ok = False

    def run(self, system_prompt: str, user_prompt: str) -> str:
        if self._ok:
            try:
                from langchain.prompts import ChatPromptTemplate
                from langchain.chains import LLMChain
                prompt = ChatPromptTemplate.from_messages([
                    ("system", system_prompt),
                    ("human", "{input}"),
                ])
                chain = LLMChain(llm=self._client, prompt=prompt)
                out = chain.run({"input": user_prompt})
                return (out or "").strip()
            except Exception:
                pass
        # fallback to native llm
        try:
            return llm.chat([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ], temperature=0.2)
        except Exception:
            return ""


def _split_chapter_titles(raw: str) -> List[str]:
    lines = [ln.strip() for ln in (raw or "").splitlines() if ln.strip()]
    out: List[str] = []
    for ln in lines:
        # accept formats like: "1. Title", "Chapter 1: Title", "- Title"
        ln2 = ln
        # remove leading numbering
        if ":" in ln2:
            # e.g., Chapter 1: Intro
            parts = ln2.split(":", 1)
            if any(ch.isdigit() for ch in parts[0]):
                ln2 = parts[1].strip()
        ln2 = ln2.lstrip("-•0123456789. ")
        if ln2:
            out.append(ln2)
    # keep 3–10
    return out[:10] if out else ["总览" if not settings.LLM_MODEL.lower().startswith("gpt") else "Overview"]


def _matching_tokens(text: str) -> set[str]:
    normalized = re.sub(r"[\/_\-]+", " ", (text or "").lower())
    tokens: set[str] = set(re.findall(r"[a-z0-9]{2,}", normalized))
    for chunk in re.findall(r"[\u4e00-\u9fff]+", normalized):
        if not chunk:
            continue
        if len(chunk) <= 4:
            tokens.add(chunk)
        for size in (2, 3, 4):
            if len(chunk) < size:
                continue
            for index in range(len(chunk) - size + 1):
                tokens.add(chunk[index:index + size])
    return tokens


def suggest_chapter_matches(
    filename: str,
    material_text: str,
    chapters: List[Dict[str, Any]],
    *,
    max_matches: int = 3,
) -> List[Dict[str, Any]]:
    corpus = f"{filename or ''}\n{material_text or ''}"[:8000]
    corpus_dense = re.sub(r"\s+", "", corpus.lower())
    corpus_tokens = _matching_tokens(corpus)
    suggestions: List[Dict[str, Any]] = []

    for chapter in chapters or []:
        title = str(chapter.get("title") or "").strip()
        unit_title = str(chapter.get("unit_title") or "").strip()
        if not title:
            continue

        title_tokens = _matching_tokens(title)
        if unit_title:
            title_tokens.update(_matching_tokens(unit_title))
        if not title_tokens:
            continue

        title_dense = re.sub(r"\s+", "", title.lower())
        unit_dense = re.sub(r"\s+", "", unit_title.lower()) if unit_title else ""
        matched_tokens = sum(1 for token in title_tokens if token in corpus_tokens)
        coverage = matched_tokens / max(len(title_tokens), 1)
        exact_bonus = 1.0 if title_dense and title_dense in corpus_dense else 0.0
        unit_bonus = 0.08 if unit_dense and unit_dense in corpus_dense else 0.0
        score = max(exact_bonus, min(0.99, coverage + unit_bonus))
        if score < 0.2:
            continue

        suggestions.append({
            "chapter_id": chapter.get("id"),
            "chapter_title": title,
            "unit_id": chapter.get("unit_id"),
            "unit_title": unit_title or None,
            "confidence": round(score, 4),
            "mapping_source": "auto",
            "label": chapter.get("label") or (f"{unit_title} / {title}" if unit_title else title),
            "_unit_order": int(chapter.get("unit_order_index") or 0),
            "_chapter_order": int(chapter.get("order_index") or 0),
        })

    suggestions.sort(key=lambda item: (-item["confidence"], item["_unit_order"], item["_chapter_order"], int(item["chapter_id"] or 0)))
    return [
        {
            "chapter_id": item["chapter_id"],
            "chapter_title": item["chapter_title"],
            "unit_id": item["unit_id"],
            "unit_title": item["unit_title"],
            "confidence": item["confidence"],
            "mapping_source": item["mapping_source"],
            "label": item["label"],
        }
        for item in suggestions[:max_matches]
    ]


# ---------- Fast-mode helpers: one LLM call per chapter ---------- #

def _prompt_chapter_all_sections(title: str, material: str, toks: Dict[str, Any]) -> str:
    is_en = toks["is_en"]
    sec_titles: List[str] = toks["sections"]  # ordered six sections
    # Limits to keep output compact and fast
    limits = {
        0: 6,  # concepts
        1: 6,  # formulas
        2: 2,  # examples
        3: 6,  # terms
        4: 6,  # tips
        5: 6,  # layered practice (allow up to 6: 2 per difficulty tier)
    }
    if is_en:
        guide = (
            "Generate ALL six sections for this chapter in one response."
            " Use Markdown with exactly these H3 headings in this exact order: \n"
            + "\n".join([f"### {h}" for h in sec_titles]) +
            "\nRules:"
            "\n- Sections 1–3 & 5: bullets only; keep <=1 line each."
            "\n- Section 4 (key terms) is for GLOBAL aggregation; it will NOT appear inside the chapter body—still produce concise term bullets."
            "\n- Section 6 must contain layered practice with difficulty tags (Basic/Intermediate/Advanced) + answer + brief rationale in one line when possible (e.g., '- [Basic] Question — Answer: X; Explanation: ...')."
            "\n- Anti-redundancy across sections; do not repeat concepts or formulas."
            "\nBullet caps: concepts<=6, formulas<=6, examples<=2, terms<=6, tips<=6 (each tip keep 🔑), layered practice<=6 (aim 2 per difficulty level)."
            "\nIf a section has no content, leave it empty (just the heading)."
        )
        mat = (
            f"Chapter: {title}\n\nMaterial (chapter-focused if possible):\n{material[:12000]}"
        )
        return f"{guide}\n\n{mat}"
    else:
        guide = (
            "在一次回答中生成该章节的六个小节，使用 Markdown，并严格按顺序使用以下 H3 标题：\n"
            + "\n".join([f"### {h}" for h in sec_titles]) +
            "\n规则："
            "\n- 第1~3与第5节：仅要点列表，单行精炼。"
            "\n- 第4节术语仅用于全局汇总，不会显示在章节内，但仍需产出精炼术语要点。"
            "\n- 第6节为分层练习：需含基础/进阶/挑战三类，每条包含题目、答案、解析，示例：'- [基础] 题干 —— 答案：X；解析：理由。'"
            "\n- 全局避免冗余：不同小节不重复同一知识。"
            "\n条数上限：概念<=6，公式<=6，示例<=2，术语<=6，提示<=6（含🔑），分层练习<=6（建议每难度 2 条）。"
            " 若无内容可空节。"
        )
        mat = (
            f"章节：{title}\n\n材料（尽量聚焦该章节）：\n{material[:12000]}"
        )
        return f"{guide}\n\n{mat}"


def _parse_chapter_sections(md: str, expected_titles: List[str]) -> Dict[str, List[str]]:
    # Split by ### headings that match expected titles; be tolerant to extra spaces
    sections: Dict[str, List[str]] = {t: [] for t in expected_titles}
    # Build regex pattern to capture heading and content until next heading
    # Using non-greedy match for content
    pattern = r"(?m)^###\s+(.*?)\s*$"
    matches = list(re.finditer(pattern, md or ""))
    if not matches:
        # Treat whole block as first section's bullets fallback
        first = expected_titles[0] if expected_titles else ""
        if first:
            sections[first] = [ln.strip() for ln in (md or "").splitlines() if ln.strip()]
        return sections
    # Append a sentinel end
    ends = [m.start() for m in matches] + [len(md)]
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = ends[i+1]
        body = (md[start:end] or "").strip()
        lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
        # Map to the closest expected title (exact or case-insensitive)
        key = None
        for t in expected_titles:
            if t.strip().lower() == title.lower():
                key = t; break
        if key is None:
            # try contains
            for t in expected_titles:
                if title.lower() in t.strip().lower() or t.strip().lower() in title.lower():
                    key = t; break
        if key is None and expected_titles:
            key = expected_titles[min(i, len(expected_titles)-1)]
        sections[key] = lines
    return sections


def _prompt_refine_dedup(md: str, toks: Dict[str, Any]) -> str:
    is_en = toks["is_en"]
    sec_titles: List[str] = toks["sections"]
    caps = {
        1: 6,  # concepts
        2: 6,  # formulas
        3: 2,  # examples
        4: 6,  # terms
        5: 6,  # tips
        6: 4,  # practice
    }
    if is_en:
        rules = (
            "Perform a FINAL refinement pass to remove redundancy and near-duplicates across the entire document,"
            " while preserving the exact Markdown structure and headings provided."
            " Do NOT add new content or change headings."
            " Merge semantically identical bullets; keep the clearer one."
            " Keep per-section bullet caps: concepts<=6, formulas<=6, examples<=2, terms<=6, tips<=6, practice<=4."
            " Preserve the key emoji 🔑 for tips."
            " Ensure every bullet is specific, one line, and unique."
            " Return the FULL refined Markdown."
        )
        titles = "\n".join([f"- {t}" for t in sec_titles])
        return (
            f"Refinement rules:\n{rules}\n\n"
            f"Section headings (must remain exactly as in input):\n{titles}\n\n"
            f"Input Markdown (refine this without altering headings):\n\n{md[:15000]}"
        )
    else:
        rules = (
            "对整份复习单做“最终精修去重”：删除冗余与近重复要点，"
            " 同时严格保持现有的 Markdown 结构与各级标题不变。"
            " 不要新增内容，也不要改标题文本。"
            " 语义相同的要点合并，保留更清晰的一条。"
            " 各小节条目上限：概念<=6，公式<=6，示例<=2，术语<=6，提示<=6，练习<=4。"
            " 保留提示前的🔑。"
            " 每条要点须具体、单行且唯一。"
            " 输出完整的精修后 Markdown。"
        )
        titles = "\n".join([f"- {t}" for t in sec_titles])
        return (
            f"精修规则：\n{rules}\n\n"
            f"小节标题（必须与输入保持一致）：\n{titles}\n\n"
            f"输入的 Markdown（在不改标题的前提下精修去重）：\n\n{md[:15000]}"
        )


def _llm_refine_dedup(md: str, lang: str) -> str:
    toks = _lang_tokens(lang)
    runner = _LangChainRunner()
    system_role = (toks["role"] + (" You act as a meticulous refiner." if toks["is_en"] else " 你现在扮演严格的终稿精修者。"))
    user = _prompt_refine_dedup(md, toks)
    out = ""
    try:
        out = runner.run(system_role, user).strip()
    except Exception:
        out = ""
    # Sanity checks: if model returns empty or breaks structure badly, fallback
    if not out or ("##" not in out and out.count("#") < 1):
        return md
    return out


def generate_review_pro_agent(text: str, lang: str = "zh") -> str:
    toks = _lang_tokens(lang)
    system_role = toks["role"]
    runner = _LangChainRunner()

    # Step 0: Light condense if too long (reuse existing condense)
    try:
        max_len = int(getattr(settings, "MAX_INPUT_CHARS", 16000))
        target_len = int(getattr(settings, "CONDENSE_TARGET_CHARS", 6000))
    except Exception:
        max_len, target_len = 16000, 6000
    material = text
    if len(material) > max_len and target_len > 0:
        material = _condense_text(material, target_len, toks["is_en"])  # type: ignore[arg-type]

    # Step 1: Identify chapters/topics
    ch_resp = runner.run(system_role, f"{toks['chapters_instr']}\n\nMaterial:\n{material[:12000]}")
    chapters = _split_chapter_titles(ch_resp)

    # Step 2 (FAST): For each chapter, extract ALL sections in one call, then split & merge
    per_chapter_md: List[str] = []
    sec_titles = toks["sections"]  # 6 items in order

    # Collect global tips and practices; de-dup lines across the whole doc
    def _norm_line(s: str) -> str:
        s2 = (s or "").strip().lower()
        s2 = s2.replace("🔑", "")
        # strip list markers and punctuation
        s2 = re.sub(r"^[\-\*\d\.)\s]+", "", s2)
        s2 = re.sub(r"[\s\-\*\.,;:!？。、“”\"'()\[\]{}]+", " ", s2)
        return " ".join(s2.split())
    global_seen: set[str] = set()
    global_tips: List[str] = []
    global_key_terms: List[str] = []  # collected from section 4

    def _extract_bullets(md_block: str) -> List[str]:
        out: List[str] = []
        for ln in (md_block or "").splitlines():
            s = ln.strip()
            if not s:
                continue
            if s.startswith(('-', '*')) or (len(s) > 2 and s[0].isdigit() and s[1] in ('.', ')')):
                out.append(s)
        return out

    for idx, title in enumerate(chapters, start=1):
        chapter_header = f"## {idx}. {title}"
        parts: List[str] = [chapter_header, ""]
        # One call to get all sections for this chapter
        up = _prompt_chapter_all_sections(title, material, toks)
        all_md = runner.run(system_prompt=system_role, user_prompt=up).strip()
        # Parse out sections
        parsed = _parse_chapter_sections(all_md, sec_titles)
        # Section-wise processing
        for s_idx, stitle in enumerate(sec_titles, start=1):
            lines = parsed.get(stitle, [])
            # Normalize to bullets
            bullets = []
            for ln in lines:
                s = ln.strip()
                if not s:
                    continue
                if not (s.startswith(('-', '*')) or (len(s) > 2 and s[0].isdigit() and s[1] in ('.', ')'))):
                    s = f"- {s}"
                bullets.append(s)
            # Cap per section
            cap = 6 if s_idx in (1,2,4) else (2 if s_idx == 3 else (4 if s_idx == 6 else 6))
            bullets = bullets[:cap]
            # Tips and practice: collect globally, don't inline here
            if s_idx == 4:  # key terms collected globally, not shown per chapter
                for b in bullets:
                    n = _norm_line(b)
                    if n and n not in set(_norm_line(x) for x in global_key_terms):
                        global_key_terms.append(b)
                continue
            if s_idx == 5:  # tips go to global summary
                for b in bullets:
                    n = _norm_line(b)
                    if n and n not in set(_norm_line(x) for x in global_tips):
                        global_tips.append(b)
                continue
            # s_idx == 6 was previous practice global; now per chapter layered practice stays in output
            # For other sections, de-duplicate globally
            dedup_lines: List[str] = []
            for ln in bullets:
                n = _norm_line(ln)
                if not n:
                    continue
                if n in global_seen:
                    continue
                global_seen.add(n)
                dedup_lines.append(ln)
            if dedup_lines:
                parts.append(f"### {stitle}\n\n" + "\n".join(dedup_lines))
        per_chapter_md.append("\n\n".join(parts) + "\n")

    # Step 3: Assemble final review sheet markdown with global title and guidance
    title_line = f"# {toks['final_intro']}"
    guide_lines = (
        "" if not toks["is_en"] else ""
    )
    assembled = [title_line]
    assembled.extend(per_chapter_md)
    # Append unified Exam/Activity tips
    if global_key_terms:
        terms_title = toks.get("key_terms_summary_title") or ("## Global Key Terms Summary" if toks["is_en"] else "## 术语与简释（汇总）")
        seen_k: set[str] = set(); uniq_terms: List[str] = []
        for t in global_key_terms:
            n = _norm_line(t)
            if n in seen_k: continue
            seen_k.add(n)
            uniq_terms.append(t if t.strip().startswith(('-','*')) else f"- {t.strip()}")
        assembled.append(terms_title)
        assembled.append("\n".join(uniq_terms))
    if global_tips:
        tips_title = ("## Exam/Activity Key Takeaways" if toks["is_en"] else "## 考试/活动重点总结")
        # de-duplicate tips
        seen_t: set[str] = set()
        uniq_tips: List[str] = []
        for t in global_tips:
            n = _norm_line(t)
            if n in seen_t:
                continue
            seen_t.add(n)
            uniq_tips.append(t if t.strip().startswith(('-','*')) else f"- {t.strip()}")
        assembled.append(tips_title)
        assembled.append("\n".join(uniq_tips))
    # Append unified practice questions at end
    # Layered practice now resides inside each chapter; no global aggregation
    final_md = "\n\n".join(assembled).strip()

    # Step 4: Enforce minimal formatting guarantees
    if not final_md.startswith("# "):
        final_md = "# Review Sheet\n\n" + final_md
    # Step 5: LLM-based final refine & deduplicate pass
    try:
        refined = _llm_refine_dedup(final_md, lang)
        # Basic guard to avoid accidental truncation
        if refined and len(refined) > len(final_md) * 0.3:
            final_md = refined
    except Exception:
        pass
    return final_md


def generate_review_pro_agent_iter(text: str, lang: str = "zh"):
    """
    Generator that yields progress events dicts and finally a dict with {"name":"done","text":markdown}
    Event shapes:
      {"name":"condense","status":"start|done"}
      {"name":"chapters","status":"start|done","count":N}
      {"name":"chapter","i":idx,"n":N,"title":str}
      {"name":"section","chapterIndex":idx,"sectionIndex":sidx,"sectionTitle":str,"chapterTitle":str}
      {"name":"assemble","status":"start|done"}
      {"name":"done","text":markdown}
    """
    toks = _lang_tokens(lang)
    system_role = toks["role"]
    runner = _LangChainRunner()
    # Condense if needed
    try:
        max_len = int(getattr(settings, "MAX_INPUT_CHARS", 16000))
        target_len = int(getattr(settings, "CONDENSE_TARGET_CHARS", 6000))
    except Exception:
        max_len, target_len = 16000, 6000
    material = text
    if len(material) > max_len and target_len > 0:
        yield {"name": "condense", "status": "start"}
        material = _condense_text(material, target_len, toks["is_en"])  # type: ignore[arg-type]
        yield {"name": "condense", "status": "done"}
    # Chapters
    yield {"name": "chapters", "status": "start"}
    ch_resp = runner.run(system_role, f"{toks['chapters_instr']}\n\nMaterial:\n{material[:12000]}")
    chapters = _split_chapter_titles(ch_resp)
    total_ch = len(chapters)
    yield {"name": "chapters", "status": "done", "count": total_ch}
    # Per chapter sections (FAST: one call per chapter)
    sec_titles = toks["sections"]
    per_chapter_md: List[str] = []
    # Collect unified tips & practice; dedupe seen across doc
    def _norm_line(s: str) -> str:
        s2 = (s or "").strip().lower()
        s2 = s2.replace("🔑", "")
        s2 = re.sub(r"^[\-\*\d\.)\s]+", "", s2)
        s2 = re.sub(r"[\s\-\*\.,;:!？。、“”\"'()\[\]{}]+", " ", s2)
        return " ".join(s2.split())
    global_seen: set[str] = set()
    global_tips: List[str] = []
    global_key_terms: List[str] = []
    def _extract_bullets(md_block: str) -> List[str]:
        out: List[str] = []
        for ln in (md_block or "").splitlines():
            s = ln.strip()
            if not s:
                continue
            if s.startswith(('-', '*')) or (len(s) > 2 and s[0].isdigit() and s[1] in ('.', ')')):
                out.append(s)
        return out
    for idx, title in enumerate(chapters, start=1):
        yield {"name": "chapter", "i": idx, "n": total_ch, "title": title}
        chapter_header = f"## {idx}. {title}"
        parts: List[str] = [chapter_header, ""]
        # One call for all sections in this chapter
        all_md = runner.run(system_role, _prompt_chapter_all_sections(title, material, toks)).strip()
        parsed = _parse_chapter_sections(all_md, sec_titles)
        for sidx, stitle in enumerate(sec_titles, start=1):
            yield {"name": "section", "chapterIndex": idx, "chapterTitle": title, "sectionIndex": sidx, "sectionTitle": stitle}
            lines = parsed.get(stitle, [])
            bullets: List[str] = []
            for ln in lines:
                s = ln.strip()
                if not s:
                    continue
                if not (s.startswith(('-', '*')) or (len(s) > 2 and s[0].isdigit() and s[1] in ('.', ')'))):
                    s = f"- {s}"
                bullets.append(s)
            cap = 6 if sidx in (1,2,4) else (2 if sidx == 3 else (4 if sidx == 6 else 6))
            bullets = bullets[:cap]
            if sidx == 4:  # key terms -> global summary only
                for b in bullets:
                    n = _norm_line(b)
                    if n and n not in set(_norm_line(x) for x in global_key_terms):
                        global_key_terms.append(b)
                continue
            if sidx == 5:  # tips global
                for b in bullets:
                    n = _norm_line(b)
                    if n and n not in set(_norm_line(x) for x in global_tips):
                        global_tips.append(b)
                continue
            # sidx == 6 layered practice stays within chapter output
            dedup_lines: List[str] = []
            for ln in bullets:
                n = _norm_line(ln)
                if not n:
                    continue
                if n in global_seen:
                    continue
                global_seen.add(n)
                dedup_lines.append(ln)
            if dedup_lines:
                parts.append(f"### {stitle}\n\n" + "\n".join(dedup_lines))
        per_chapter_md.append("\n\n".join(parts) + "\n")
    # Assemble
    yield {"name": "assemble", "status": "start"}
    title_line = f"# {toks['final_intro']}"
    assembled = [title_line]
    assembled.extend(per_chapter_md)
    # Global key terms summary
    if global_key_terms:
        terms_title = ("## Global Key Terms Summary" if toks["is_en"] else "## 术语与简释（汇总）")
        seen_k: set[str] = set(); uniq_terms: List[str] = []
        for t in global_key_terms:
            n = _norm_line(t)
            if n in seen_k: continue
            seen_k.add(n)
            uniq_terms.append(t if t.strip().startswith(('-','*')) else f"- {t.strip()}")
        assembled.append(terms_title)
        assembled.append("\n".join(uniq_terms))
    # Global tips summary
    if global_tips:
        tips_title = ("## Exam/Activity Key Takeaways" if toks["is_en"] else "## 考试/活动重点总结")
        seen_t: set[str] = set(); uniq_tips: List[str] = []
        for t in global_tips:
            n = _norm_line(t)
            if n in seen_t: continue
            seen_t.add(n)
            uniq_tips.append(t if t.strip().startswith(('-','*')) else f"- {t.strip()}")
        assembled.append(tips_title)
        assembled.append("\n".join(uniq_tips))
    final_md = "\n\n".join(assembled).strip()
    if not final_md.startswith("# "):
        final_md = "# Review Sheet\n\n" + final_md
    yield {"name": "assemble", "status": "done"}
    # Refine
    yield {"name": "refine", "status": "start"}
    try:
        refined = _llm_refine_dedup(final_md, lang)
        if refined and len(refined) > len(final_md) * 0.3:
            final_md = refined
    except Exception:
        pass
    yield {"name": "refine", "status": "done"}
    yield {"name": "done", "text": final_md}
