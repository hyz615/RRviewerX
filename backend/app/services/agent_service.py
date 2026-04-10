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
from dataclasses import dataclass
from typing import Literal, Dict, Any, List, Optional
import json
import re
import threading
from ..core.config import settings


Format = Literal["qa", "flashcards", "review_sheet_pro"]
Length = Literal["short", "medium", "long"]


@dataclass
class _APIConfig:
    name: str
    provider: str
    model: str
    api_key: str | None
    base_url: str | None


@dataclass
class _APIEntry:
    config: _APIConfig
    client: Any


def _clean_setting_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _looks_like_vision_model(model: str | None) -> bool:
    name = (model or "").strip().lower()
    if not name:
        return False
    vision_tokens = (
        "gpt-4o",
        "gpt-4.1",
        "vision",
        "claude-3",
        "claude-3.5",
        "claude-3.7",
        "gemini",
        "glm-4v",
        "qwen-vl",
        "minicpm-v",
        "llava",
    )
    return any(token in name for token in vision_tokens)


class LLMProvider:
    def __init__(self) -> None:
        self.provider = settings.LLM_PROVIDER.lower()
        self.model = settings.LLM_MODEL
        self.openai_key = settings.OPENAI_API_KEY
        self.deepseek_key = settings.DEEPSEEK_API_KEY
        self.base_url = getattr(settings, "LLM_BASE_URL", None)
        self._rr_lock = threading.Lock()
        self._rr_index = {"llm": 0, "vlm": 0}
        self._entries = {
            "llm": self._build_entries("llm"),
            "vlm": self._build_entries("vlm"),
        }
        if not self._entries["vlm"]:
            self._entries["vlm"] = [
                entry for entry in self._entries["llm"]
                if _looks_like_vision_model(entry.config.model)
            ]
        if self._entries["llm"]:
            first = self._entries["llm"][0]
            self.model = first.config.model
            self.provider = first.config.provider
            self._client = first.client
        else:
            self._client = None

    def _normalize_config(
        self,
        *,
        name: str,
        provider: str,
        model: str | None,
        api_key: str | None,
        base_url: str | None,
    ) -> _APIConfig | None:
        provider_name = (provider or "openai").strip().lower()
        model_name = _clean_setting_text(model)
        resolved_key = _clean_setting_text(api_key)
        resolved_base = _clean_setting_text(base_url)
        if provider_name == "deepseek":
            resolved_base = resolved_base or "https://api.deepseek.com"
            if not model_name or model_name == "gpt-4o-mini":
                model_name = "deepseek-chat"
        elif not model_name:
            model_name = "gpt-4o-mini"
        if provider_name == "mock" or (not resolved_key and not resolved_base):
            return None
        return _APIConfig(
            name=name,
            provider=provider_name,
            model=model_name,
            api_key=resolved_key,
            base_url=resolved_base,
        )

    def _legacy_config(self, purpose: str) -> _APIConfig | None:
        if purpose == "vlm":
            provider = _clean_setting_text(getattr(settings, "VLM_PROVIDER", None)) or "openai"
            return self._normalize_config(
                name="vlm-legacy",
                provider=provider,
                model=getattr(settings, "VLM_MODEL", None),
                api_key=getattr(settings, "VLM_API_KEY", None),
                base_url=getattr(settings, "VLM_BASE_URL", None),
            )
        api_key = self.openai_key if self.provider == "openai" else self.deepseek_key
        return self._normalize_config(
            name="llm-legacy",
            provider=self.provider,
            model=self.model,
            api_key=api_key,
            base_url=self.base_url,
        )

    def _configs_from_json(self, raw: str | None, purpose: str) -> List[_APIConfig]:
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except Exception:
            return []
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return []
        configs: List[_APIConfig] = []
        for index, item in enumerate(data, start=1):
            if not isinstance(item, dict):
                continue
            enabled = item.get("enabled", True)
            if isinstance(enabled, str):
                enabled = enabled.strip().lower() not in {"0", "false", "no", "off"}
            if not enabled:
                continue
            provider = _clean_setting_text(item.get("provider")) or ("openai" if purpose == "vlm" else self.provider)
            config = self._normalize_config(
                name=_clean_setting_text(item.get("name")) or f"{purpose}-{index}",
                provider=provider,
                model=item.get("model"),
                api_key=item.get("api_key"),
                base_url=item.get("base_url"),
            )
            if config is not None:
                configs.append(config)
        return configs

    def _build_client(self, config: _APIConfig) -> Any | None:
        try:
            from openai import OpenAI
        except Exception:
            return None
        try:
            kwargs: Dict[str, Any] = {"api_key": config.api_key or "sk-placeholder"}
            if config.base_url:
                kwargs["base_url"] = config.base_url
            return OpenAI(**kwargs)
        except Exception:
            return None

    def _build_entries(self, purpose: str) -> List[_APIEntry]:
        raw = getattr(settings, "LLM_API_CONFIGS", None) if purpose == "llm" else getattr(settings, "VLM_API_CONFIGS", None)
        configs = self._configs_from_json(raw, purpose)
        if not configs:
            legacy = self._legacy_config(purpose)
            if legacy is not None:
                configs = [legacy]
        entries: List[_APIEntry] = []
        for config in configs:
            client = self._build_client(config)
            if client is not None:
                entries.append(_APIEntry(config=config, client=client))
        return entries

    def has_client(self, purpose: str = "llm") -> bool:
        return bool(self._entries.get(purpose))

    def _flatten_content(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    text = _clean_setting_text(item.get("text"))
                    if text:
                        parts.append(text)
                elif item.get("type") == "image_url":
                    parts.append("[image]")
            return "\n".join(parts)
        return str(content or "")

    def _mock_reply(self, messages: List[Dict[str, Any]]) -> str:
        for message in reversed(messages or []):
            text = self._flatten_content(message.get("content"))
            if text:
                return text[:512]
        return ""

    def _next_entries(self, purpose: str) -> List[_APIEntry]:
        entries = list(self._entries.get(purpose) or [])
        if not entries:
            return []
        with self._rr_lock:
            start = self._rr_index[purpose] % len(entries)
            self._rr_index[purpose] = (self._rr_index[purpose] + 1) % len(entries)
        return entries[start:] + entries[:start]

    def _extract_content(self, response: Any) -> str:
        try:
            content = response.choices[0].message.content
        except Exception:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                text = _clean_setting_text(item.get("text"))
                if text:
                    parts.append(text)
            return "\n".join(parts)
        return str(content or "")

    def chat(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.2,
        *,
        purpose: str = "llm",
        max_tokens: int | None = None,
    ) -> str:
        entries = self._next_entries(purpose)
        if not entries:
            return self._mock_reply(messages)
        for entry in entries:
            try:
                payload: Dict[str, Any] = {
                    "model": entry.config.model,
                    "messages": messages,
                    "temperature": temperature,
                }
                if max_tokens is not None:
                    payload["max_tokens"] = max_tokens
                resp = entry.client.chat.completions.create(**payload)
                content = self._extract_content(resp).strip()
                if content:
                    return content
            except Exception:
                continue
        return self._mock_reply(messages)


llm = LLMProvider()


def summarize_visual_material(
    filename: str,
    image_payloads: List[Dict[str, str]],
    *,
    extracted_text: str = "",
    lang: str = "zh",
) -> str:
    if not image_payloads or not llm.has_client("vlm"):
        return ""
    is_en = (lang or "").lower().startswith("en")
    limited = image_payloads[: max(1, getattr(settings, "VLM_MAX_IMAGES", 6))]
    labels = [str(item.get("label") or "").strip() for item in limited if str(item.get("label") or "").strip()]
    text_hint = (extracted_text or "").strip()
    if len(text_hint) > 1600:
        text_hint = text_hint[:1600]
    if is_en:
        system = (
            "You are a vision pre-processor for downstream study-assistant workflows. "
            "Describe only what is visible in the uploaded pages or images. "
            "Extract headings, formulas, diagrams, tables, question stems, answer options, and key annotations. "
            "When uncertain, mark the detail as [unclear] instead of inventing it. "
            "Return plain text that can be passed to another LLM."
        )
        user_prompt = (
            f"Filename: {filename}\n"
            f"Image order: {', '.join(labels) if labels else 'in order of appearance'}\n"
            "Summarize the educational content in these images/pages for a downstream text model.\n"
            "Prefer concrete facts over general descriptions, and keep the summary structured but concise."
        )
        if text_hint:
            user_prompt += "\n\nExisting extracted text (may be incomplete):\n" + text_hint
    else:
        user_prompt = (
            f"文件名：{filename}\n"
            f"图片顺序：{', '.join(labels) if labels else '按出现顺序'}\n"
            "请把这些图片或扫描页里的学习内容总结成可直接交给下游文本大模型的纯文本摘要。\n"
            "优先提取标题、知识点、公式、图表结论、题干、选项、表格字段、步骤与批注；不要编造看不清的内容，看不清请标注 [不清晰]。"
        )
        if text_hint:
            user_prompt += "\n\n已有文字抽取（可能不完整）：\n" + text_hint
        system = (
            "你是学习资料的视觉预处理器。只描述图中真实可见的信息，"
            "把图片内容整理成结构化纯文本，供下游文本大模型继续生成。"
        )

    content: List[Dict[str, Any]] = [{"type": "text", "text": user_prompt}]
    for item in limited:
        url = _clean_setting_text(item.get("url"))
        if not url:
            continue
        image_part: Dict[str, Any] = {"type": "image_url", "image_url": {"url": url}}
        detail = _clean_setting_text(item.get("detail"))
        if detail:
            image_part["image_url"]["detail"] = detail
        content.append(image_part)
    if len(content) <= 1:
        return ""
    try:
        out = llm.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
            temperature=0.1,
            purpose="vlm",
            max_tokens=1200,
        )
        limit = max(400, int(getattr(settings, "VLM_SUMMARY_MAX_CHARS", 3000)))
        return (out or "").strip()[:limit]
    except Exception:
        return ""


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
    if not llm.has_client("llm"):
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
        if getattr(settings, "LLM_API_CONFIGS", None):
            return
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


def _detect_material_language(text: str) -> str:
    sample = (text or "")[:4000]
    zh_count = len(re.findall(r"[\u4e00-\u9fff]", sample))
    en_count = len(re.findall(r"[A-Za-z]{3,}", sample))
    return "zh" if zh_count >= en_count else "en"


def _clean_heading_title(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "").strip())
    cleaned = cleaned.strip("-:：.、· ")
    return cleaned[:120]


def _unique_titles(values: List[str]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for value in values:
        title = _clean_heading_title(value)
        key = re.sub(r"\s+", "", title.lower())
        if not title or key in seen:
            continue
        seen.add(key)
        result.append(title)
    return result


def _split_paragraph_chunks(text: str, count: int) -> List[str]:
    pieces = [piece.strip() for piece in re.split(r"\n\s*\n+", text or "") if piece.strip()]
    if not pieces:
        pieces = [piece.strip() for piece in str(text or "").splitlines() if piece.strip()]
    if not pieces:
        return [str(text or "").strip()]

    total = len(pieces)
    target = max(1, min(count, total))
    chunks: List[str] = []
    for index in range(target):
        start = round(index * total / target)
        end = round((index + 1) * total / target)
        chunk = "\n\n".join(pieces[start:end]).strip()
        if chunk:
            chunks.append(chunk)
    return chunks or [str(text or "").strip()]


def _looks_explicit_textbook_heading(line: str) -> bool:
    if not line or len(line) > 120:
        return False
    patterns = [
        r"^(?:unit|part|module|lesson|chapter|section|topic)\s+[A-Za-z0-9IVXLCM]+(?:\s*[:.\-]\s*|\s+).+$",
        r"^第[一二三四五六七八九十百千0-9]+(?:单元|部分|编|篇|课|章|节)\s*[:：.\-]?\s*.+$",
        r"^(?:\d{1,2}(?:\.\d{1,3}){0,3}|[IVXLCM]{1,8}|[A-Z])(?:[.)]|\s*[:：.\-])\s*\S.+$",
    ]
    return any(re.match(pattern, line, re.I) for pattern in patterns)


def _looks_loose_textbook_heading(line: str, prev_blank: bool, next_blank: bool) -> bool:
    if not line or len(line) > 70 or not (prev_blank or next_blank):
        return False
    if re.search(r"https?://|www\.", line, re.I):
        return False
    if re.fullmatch(r"(?:page|p\.)\s*\d+", line, re.I):
        return False
    if re.search(r"[。！？!?；;]$", line):
        return False
    if len(re.findall(r"[，,、；;]", line)) > 1:
        return False

    english_words = re.findall(r"[A-Za-z]+(?:['-][A-Za-z]+)?", line)
    zh_chars = len(re.findall(r"[\u4e00-\u9fff]", line))
    digits = len(re.findall(r"\d", line))

    if english_words:
        return len(english_words) <= 12 and digits <= 4 and bool(re.search(r"[A-Z]", line))
    if zh_chars:
        return zh_chars <= 30 and digits <= 6
    return len(line) <= 40 and digits <= 6


def _collect_textbook_heading_candidates(
    raw_lines: List[str],
    *,
    start_line: int = 1,
    end_line: int | None = None,
) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []
    safe_start = max(1, int(start_line or 1))
    safe_end = len(raw_lines) if end_line is None else min(len(raw_lines), max(0, int(end_line)))
    if safe_end < safe_start:
        return []

    for line_number in range(safe_start, safe_end + 1):
        raw_line = raw_lines[line_number - 1]
        text = _clean_heading_title(raw_line)
        if not text:
            continue
        prev_blank = line_number == 1 or not str(raw_lines[line_number - 2] or "").strip()
        next_blank = line_number == len(raw_lines) or not str(raw_lines[line_number] or "").strip()
        if _looks_explicit_textbook_heading(text):
            ranked.append({"line_number": line_number, "text": text, "priority": 2})
        elif _looks_loose_textbook_heading(text, prev_blank, next_blank):
            ranked.append({"line_number": line_number, "text": text, "priority": 1})

    selected: List[Dict[str, Any]] = []
    total_chars = 0
    for priority in (2, 1):
        for item in ranked:
            if item["priority"] != priority:
                continue
            rendered = f"{item['line_number']}: {item['text']}"
            if len(selected) >= 400 or total_chars + len(rendered) + 1 > 18000:
                continue
            selected.append({"line_number": item["line_number"], "text": item["text"]})
            total_chars += len(rendered) + 1
    selected.sort(key=lambda item: int(item["line_number"]))
    return selected


def _looks_textbook_toc_anchor(line: str) -> bool:
    cleaned = _clean_heading_title(line)
    if not cleaned:
        return False
    normalized = re.sub(r"\s+", " ", cleaned.lower()).strip()
    if normalized in {"contents", "table of contents", "toc", "目录", "目次"}:
        return True
    if "目录" in cleaned and len(cleaned) <= 12:
        return True
    return normalized.startswith("table of contents") or normalized.startswith("contents ")


def _looks_textbook_toc_entry(line: str) -> bool:
    cleaned = _clean_heading_title(line)
    if not cleaned or len(cleaned) > 140 or _looks_textbook_toc_anchor(cleaned):
        return False
    if re.fullmatch(r"(?:page|p\.)\s*\d+", cleaned, re.I):
        return False
    if re.search(r"(?:\.{2,}|·{2,}|…{2,}|-{2,}|_{2,})\s*(?:\d{1,4}|[ivxlcdm]{1,8})\s*$", cleaned, re.I):
        return True
    if re.search(r"\s+(?:\d{1,4}|[ivxlcdm]{1,8})\s*$", cleaned, re.I):
        prefix = re.sub(r"\s+(?:\d{1,4}|[ivxlcdm]{1,8})\s*$", "", cleaned, flags=re.I).strip()
        if _looks_explicit_textbook_heading(prefix):
            return True
        if re.match(r"^(?:\d{1,2}(?:\.\d{1,3}){0,3}|[IVXLCM]{1,8}|[A-Z])[.)]?\s+\S.+$", prefix, re.I):
            return True
        english_words = re.findall(r"[A-Za-z]+(?:['-][A-Za-z]+)?", prefix)
        zh_chars = len(re.findall(r"[\u4e00-\u9fff]", prefix))
        if english_words and len(english_words) <= 14:
            return True
        if zh_chars and zh_chars <= 36:
            return True
    return False


def _extract_textbook_toc_candidates(raw_lines: List[str]) -> Dict[str, Any] | None:
    if not raw_lines:
        return None

    anchor_search_limit = min(len(raw_lines), max(80, min(240, len(raw_lines) // 3 + 20)))
    anchor_line = None
    for line_number in range(1, anchor_search_limit + 1):
        if _looks_textbook_toc_anchor(raw_lines[line_number - 1]):
            anchor_line = line_number
            break
    if anchor_line is None:
        return None

    entries: List[Dict[str, Any]] = []
    noise_streak = 0
    blank_streak = 0
    strong_entry_count = 0
    toc_end_line = anchor_line
    scan_limit = min(len(raw_lines), anchor_line + 160)
    for line_number in range(anchor_line + 1, scan_limit + 1):
        text = _clean_heading_title(raw_lines[line_number - 1])
        if not text:
            blank_streak += 1
            if entries and blank_streak >= 3 and noise_streak >= 2:
                break
            continue

        had_blank_gap = blank_streak > 0
        blank_streak = 0
        if _looks_textbook_toc_anchor(text):
            if entries:
                break
            continue

        is_strong_entry = _looks_textbook_toc_entry(text)
        is_weak_entry = (not is_strong_entry) and _looks_explicit_textbook_heading(text) and len(text) <= 100
        if is_strong_entry:
            entries.append({"line_number": line_number, "text": text})
            toc_end_line = line_number
            strong_entry_count += 1
            noise_streak = 0
            continue

        if is_weak_entry:
            if entries and strong_entry_count >= 2 and had_blank_gap:
                break
            entries.append({"line_number": line_number, "text": text})
            toc_end_line = line_number
            noise_streak = 0
            continue

        noise_streak += 1
        if entries and noise_streak >= 8:
            break

    if len(entries) < 2:
        return None
    return {
        "anchor_line": anchor_line,
        "end_line": toc_end_line,
        "entries": entries,
    }


def _extract_json_object(raw: str) -> Dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None

    candidates: List[str] = []
    fenced = re.findall(r"```(?:json)?\s*(.*?)\s*```", text, re.I | re.S)
    candidates.extend(fenced)
    candidates.append(text)

    for candidate in candidates:
        snippet = candidate.strip()
        if not snippet:
            continue
        start = snippet.find("{")
        end = snippet.rfind("}")
        if start < 0 or end <= start:
            continue
        try:
            payload = json.loads(snippet[start:end + 1])
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _heading_key(value: Any) -> str:
    return re.sub(r"\s+", " ", _clean_heading_title(str(value or "")).lower()).strip()


def _resolve_textbook_start_line(
    chapter: Dict[str, Any],
    raw_lines: List[str],
    candidate_lookup: Dict[str, List[int]],
    used_lines: set[int],
    *,
    min_line_number: int = 1,
) -> int | None:
    for key in ("start_line", "startLine", "line", "line_number"):
        value = chapter.get(key)
        if value is None:
            continue
        try:
            line_number = int(str(value).strip())
        except Exception:
            continue
        if min_line_number <= line_number <= len(raw_lines) and line_number not in used_lines:
            return line_number

    for key in ("heading_text", "heading", "raw_heading", "source_text"):
        normalized = _heading_key(chapter.get(key))
        if not normalized:
            continue
        for line_number in candidate_lookup.get(normalized, []):
            if line_number not in used_lines:
                return line_number

    title_key = _heading_key(chapter.get("title"))
    if not title_key:
        return None
    for line_number in range(max(1, min_line_number), len(raw_lines) + 1):
        raw_line = raw_lines[line_number - 1]
        if line_number in used_lines:
            continue
        normalized = _heading_key(raw_line)
        if normalized == title_key or title_key in normalized:
            return line_number
    return None


def _structure_from_llm_payload(
    payload: Dict[str, Any],
    raw_lines: List[str],
    candidates: List[Dict[str, Any]],
    default_unit_title: str,
    *,
    min_line_number: int = 1,
    strategy: str = "llm",
) -> Dict[str, Any] | None:
    units_payload = payload.get("units")
    if not isinstance(units_payload, list):
        chapters_payload = payload.get("chapters")
        if isinstance(chapters_payload, list):
            units_payload = [{"title": default_unit_title, "chapters": chapters_payload}]
        else:
            units_payload = []

    candidate_lookup: Dict[str, List[int]] = {}
    for item in candidates:
        line_number = int(item.get("line_number") or 0)
        if line_number < min_line_number:
            continue
        key = _heading_key(item.get("text"))
        if not key:
            continue
        candidate_lookup.setdefault(key, []).append(line_number)

    resolved: List[Dict[str, Any]] = []
    used_lines: set[int] = set()
    for unit_order, unit in enumerate(units_payload):
        if not isinstance(unit, dict):
            continue
        unit_title = _clean_heading_title(unit.get("title") or default_unit_title) or default_unit_title
        for chapter_order, chapter in enumerate(unit.get("chapters") or []):
            if not isinstance(chapter, dict):
                continue
            title = _clean_heading_title(chapter.get("title") or "")
            if not title:
                continue
            start_line = _resolve_textbook_start_line(
                chapter,
                raw_lines,
                candidate_lookup,
                used_lines,
                min_line_number=min_line_number,
            )
            if start_line is None:
                continue
            used_lines.add(start_line)
            resolved.append({
                "unit_title": unit_title,
                "title": title,
                "start_line": start_line,
                "unit_order": unit_order,
                "chapter_order": chapter_order,
            })

    resolved.sort(key=lambda item: (int(item["start_line"]), int(item["unit_order"]), int(item["chapter_order"])))
    if len(resolved) < 2:
        return None

    units: List[Dict[str, Any]] = []
    unit_lookup: Dict[str, Dict[str, Any]] = {}
    for index, chapter in enumerate(resolved):
        start = int(chapter["start_line"]) - 1
        end = int(resolved[index + 1]["start_line"]) - 1 if index + 1 < len(resolved) else len(raw_lines)
        content = "\n".join(raw_lines[start:end]).strip()
        if not content:
            continue
        unit_title = chapter["unit_title"] or default_unit_title
        if unit_title not in unit_lookup:
            unit_lookup[unit_title] = {"title": unit_title, "chapters": []}
            units.append(unit_lookup[unit_title])
        unit_lookup[unit_title]["chapters"].append({
            "title": chapter["title"],
            "content": content,
        })

    total_chapters = sum(len(unit.get("chapters") or []) for unit in units)
    if total_chapters < 2:
        return None
    return {"units": units, "strategy": strategy}


def _extract_textbook_toc_structure(text: str, filename: str | None, lang: str) -> Dict[str, Any] | None:
    raw_lines = str(text or "").splitlines()
    if len(raw_lines) < 2 or not llm.has_client("llm"):
        return None

    toc_info = _extract_textbook_toc_candidates(raw_lines)
    if toc_info is None:
        return None

    default_unit_title = _clean_heading_title(filename or "") or ("教材章节" if lang == "zh" else "Textbook")
    toc_entries = toc_info.get("entries") or []
    candidate_block = "\n".join(f"{item['line_number']}: {item['text']}" for item in toc_entries)
    if lang == "zh":
        system_prompt = (
            "你是教材目录结构抽取器。"
            "你只能根据提供的目录条目识别单元和章节，不得编造标题。"
            "只返回严格 JSON，不要解释。"
        )
        user_prompt = (
            "请从下面教材目录中识别课程结构，并返回 JSON。\n"
            "返回格式：\n"
            "{\"units\": [{\"title\": \"教材章节\", \"chapters\": [{\"title\": \"极限\", \"source_text\": \"Chapter 1 Limits ........ 1\"}]}]}\n"
            "规则：\n"
            "1. title 只保留单元名或章节名，不要带页码。\n"
            "2. source_text 必须原样引用目录中的一行。\n"
            "3. 忽略前言、致谢、附录、索引、参考文献等非正式课程章节。\n"
            "4. 若目录只有章节没有单元，使用默认单元标题。\n"
            f"5. 默认单元标题为 {json.dumps(default_unit_title, ensure_ascii=False)}。\n"
            "6. 按目录原顺序输出，合并重复项。\n"
            "7. 如果无法可靠识别至少 2 个章节，返回 {\"units\": []}。\n\n"
            f"文件名：{filename or 'unknown'}\n"
            f"目录起始行：{toc_info['anchor_line']}\n"
            f"目录结束行：{toc_info['end_line']}\n"
            "目录条目：\n"
            f"{candidate_block}"
        )
    else:
        system_prompt = (
            "You extract textbook structure from a table of contents. "
            "Use only the provided TOC lines and never invent titles. "
            "Return strict JSON only."
        )
        user_prompt = (
            "Identify the course structure from the textbook TOC below and return JSON.\n"
            "Schema:\n"
            "{\"units\": [{\"title\": \"Textbook\", \"chapters\": [{\"title\": \"Limits\", \"source_text\": \"Chapter 1 Limits ........ 1\"}]}]}\n"
            "Rules:\n"
            "1. title must keep only the unit or chapter name, without page numbers.\n"
            "2. source_text must quote one TOC line exactly.\n"
            "3. Ignore preface, acknowledgements, appendix, index, bibliography, and other non-course sections.\n"
            "4. If the TOC has chapters but no units, use the default unit title.\n"
            f"5. The default unit title is {json.dumps(default_unit_title)}.\n"
            "6. Preserve TOC order and merge duplicates.\n"
            "7. If you cannot reliably identify at least 2 chapters, return {\"units\": []}.\n\n"
            f"Filename: {filename or 'unknown'}\n"
            f"TOC anchor line: {toc_info['anchor_line']}\n"
            f"TOC end line: {toc_info['end_line']}\n"
            "TOC entries:\n"
            f"{candidate_block}"
        )

    payload = _extract_json_object(
        llm.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=1600,
        )
    )
    if payload is None:
        return None

    return _structure_from_llm_payload(
        payload,
        raw_lines,
        _collect_textbook_heading_candidates(raw_lines, start_line=int(toc_info["end_line"]) + 1),
        default_unit_title,
        min_line_number=int(toc_info["end_line"]) + 1,
        strategy="toc_llm",
    )


def _extract_textbook_llm_structure(text: str, filename: str | None, lang: str) -> Dict[str, Any] | None:
    raw_lines = str(text or "").splitlines()
    if len(raw_lines) < 2 or not llm.has_client("llm"):
        return None

    toc_info = _extract_textbook_toc_candidates(raw_lines)
    min_line_number = int(toc_info["end_line"]) + 1 if toc_info is not None else 1
    candidates = _collect_textbook_heading_candidates(raw_lines, start_line=min_line_number)
    if len(candidates) < 2:
        return None

    default_unit_title = _clean_heading_title(filename or "") or ("教材章节" if lang == "zh" else "Textbook")
    candidate_block = "\n".join(f"{item['line_number']}: {item['text']}" for item in candidates)
    if lang == "zh":
        system_prompt = (
            "你是教材章节结构抽取器。"
            "你只能根据提供的候选行识别教材的单元/章节结构，禁止编造不存在的标题。"
            "只返回严格 JSON，不要解释。"
        )
        user_prompt = (
            "请从下面教材候选行中识别课程结构，并返回 JSON。\n"
            "返回格式：\n"
            "{\"units\": [{\"title\": \"教材章节\", \"chapters\": [{\"title\": \"极限\", \"start_line\": 12, \"heading_text\": \"Chapter 1 Limits\"}]}]}\n"
            "规则：\n"
            "1. start_line 必须使用候选行中的 1-based 行号。\n"
            "2. heading_text 必须与候选行文本一致。\n"
            "3. 忽略正文句子、页码、习题、页眉页脚、图表说明。\n"
            "4. 合并重复标题，保持原顺序。\n"
            f"5. 如果没有明确单元，使用默认单元标题 {json.dumps(default_unit_title, ensure_ascii=False)}。\n"
            "6. 只保留适合作为课程章节的顶层主题；不要把普通小点或正文句子当成章节。\n"
            "7. 如果无法可靠识别至少 2 个章节，返回 {\"units\": []}。\n\n"
            f"文件名：{filename or 'unknown'}\n"
            f"原文总行数：{len(raw_lines)}\n"
            f"候选行数：{len(candidates)}\n"
            "候选行：\n"
            f"{candidate_block}"
        )
    else:
        system_prompt = (
            "You extract textbook chapter structure. "
            "Use only the provided candidate lines and never invent headings. "
            "Return strict JSON only, with no commentary."
        )
        user_prompt = (
            "Identify the textbook structure from the candidate lines below and return JSON.\n"
            "Schema:\n"
            "{\"units\": [{\"title\": \"Textbook\", \"chapters\": [{\"title\": \"Limits\", \"start_line\": 12, \"heading_text\": \"Chapter 1 Limits\"}]}]}\n"
            "Rules:\n"
            "1. start_line must be a 1-based line number taken from the candidate list.\n"
            "2. heading_text must match the candidate line text exactly.\n"
            "3. Ignore body sentences, page numbers, exercises, headers/footers, and figure captions.\n"
            "4. Merge duplicates and keep the original order.\n"
            f"5. If there are no clear units, use the default unit title {json.dumps(default_unit_title)}.\n"
            "6. Keep only chapter-level study topics; do not treat ordinary bullet points or prose as chapters.\n"
            "7. If you cannot reliably identify at least 2 chapters, return {\"units\": []}.\n\n"
            f"Filename: {filename or 'unknown'}\n"
            f"Total source lines: {len(raw_lines)}\n"
            f"Candidate count: {len(candidates)}\n"
            "Candidate lines:\n"
            f"{candidate_block}"
        )

    raw = llm.chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        max_tokens=1600,
    )
    payload = _extract_json_object(raw)
    if payload is None:
        return None
    return _structure_from_llm_payload(
        payload,
        raw_lines,
        candidates,
        default_unit_title,
        min_line_number=min_line_number,
        strategy="llm",
    )


def _extract_textbook_heading_structure(text: str, lang: str) -> Dict[str, Any] | None:
    raw_lines = str(text or "").splitlines()
    if not raw_lines:
        return None

    unit_patterns = [
        re.compile(r"^(?:unit|part|module|lesson)\s+[A-Za-z0-9IVXLCM]+(?:\s*[:.\-]\s*|\s+)(?P<title>.+)$", re.I),
        re.compile(r"^第[一二三四五六七八九十百千0-9]+(?:单元|部分|编|篇|课)\s*[:：.\-]?\s*(?P<title>.+)$"),
    ]
    chapter_patterns = [
        re.compile(r"^(?:chapter|section)\s+[A-Za-z0-9IVXLCM]+(?:\s*[:.\-]\s*|\s+)(?P<title>.+)$", re.I),
        re.compile(r"^第[一二三四五六七八九十百千0-9]+(?:章|节)\s*[:：.\-]?\s*(?P<title>.+)$"),
        re.compile(r"^(?P<num>\d{1,2}(?:\.\d{1,2}){0,2})\s+(?P<title>[A-Za-z][^.;]{2,80}|[\u4e00-\u9fff][^\n]{1,40})$"),
    ]

    default_unit_title = "教材章节" if lang == "zh" else "Textbook"
    current_unit_title = default_unit_title
    chapter_entries: List[Dict[str, Any]] = []
    unit_titles_seen: set[str] = set()

    for line_index, raw_line in enumerate(raw_lines):
        line = str(raw_line or "").strip()
        if not line or len(line) > 120:
            continue

        matched_unit = None
        for pattern in unit_patterns:
            matched_unit = pattern.match(line)
            if matched_unit:
                break
        if matched_unit:
            current_unit_title = _clean_heading_title(matched_unit.group("title") or line)
            if not current_unit_title:
                current_unit_title = default_unit_title
            unit_titles_seen.add(current_unit_title)
            continue

        matched_chapter = None
        for pattern in chapter_patterns:
            matched_chapter = pattern.match(line)
            if matched_chapter:
                break
        if not matched_chapter:
            continue

        chapter_title = _clean_heading_title(matched_chapter.groupdict().get("title") or line)
        if not chapter_title:
            continue
        chapter_entries.append({
            "title": chapter_title,
            "unit_title": current_unit_title,
            "line_index": line_index,
        })

    if len(chapter_entries) < 2 and unit_titles_seen:
        chapter_entries = []
        for line_index, raw_line in enumerate(raw_lines):
            line = str(raw_line or "").strip()
            if not line or len(line) > 120:
                continue
            for pattern in unit_patterns:
                matched_unit = pattern.match(line)
                if not matched_unit:
                    continue
                chapter_title = _clean_heading_title(matched_unit.group("title") or line)
                if chapter_title:
                    chapter_entries.append({
                        "title": chapter_title,
                        "unit_title": default_unit_title,
                        "line_index": line_index,
                    })
                break

    if len(chapter_entries) < 2:
        return None

    units: List[Dict[str, Any]] = []
    unit_lookup: Dict[str, Dict[str, Any]] = {}
    for index, chapter in enumerate(chapter_entries):
        start = int(chapter["line_index"])
        end = int(chapter_entries[index + 1]["line_index"]) if index + 1 < len(chapter_entries) else len(raw_lines)
        content = "\n".join(raw_lines[start:end]).strip()
        if not content:
            continue
        unit_title = _clean_heading_title(chapter.get("unit_title") or default_unit_title) or default_unit_title
        if unit_title not in unit_lookup:
            unit_lookup[unit_title] = {"title": unit_title, "chapters": []}
            units.append(unit_lookup[unit_title])
        unit_lookup[unit_title]["chapters"].append({
            "title": chapter["title"],
            "content": content,
        })

    total_chapters = sum(len(unit.get("chapters") or []) for unit in units)
    if total_chapters < 2:
        return None
    return {"units": units, "strategy": "headings"}


def infer_textbook_structure(text: str, filename: str | None = None) -> Dict[str, Any]:
    lang = _detect_material_language(text)
    parsed = _extract_textbook_toc_structure(text, filename, lang)
    if parsed is not None:
        return parsed

    parsed = _extract_textbook_llm_structure(text, filename, lang)
    if parsed is not None:
        return parsed

    parsed = _extract_textbook_heading_structure(text, lang)
    if parsed is not None:
        return parsed

    runner = _LangChainRunner()
    toks = _lang_tokens(lang)
    system_role = toks["role"]
    response = runner.run(system_role, f"{toks['chapters_instr']}\n\nMaterial:\n{str(text or '')[:12000]}")
    chapter_titles = _unique_titles(_split_chapter_titles(response))
    if not chapter_titles:
        default_prefix = "章节" if lang == "zh" else "Chapter"
        chapter_titles = [f"{default_prefix} {index}" for index in range(1, 5)]

    chunks = _split_paragraph_chunks(text, len(chapter_titles))
    default_unit_title = _clean_heading_title(filename or "") or ("教材章节" if lang == "zh" else "Textbook")
    chapters: List[Dict[str, Any]] = []
    for index, title in enumerate(chapter_titles):
        content = chunks[index] if index < len(chunks) else ""
        if not content:
            continue
        chapters.append({"title": title, "content": content})

    if not chapters:
        chapters = [{
            "title": ("总览" if lang == "zh" else "Overview"),
            "content": str(text or "").strip(),
        }]

    return {
        "units": [{"title": default_unit_title, "chapters": chapters}],
        "strategy": "llm",
    }


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
