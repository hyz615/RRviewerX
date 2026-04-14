from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Optional, Literal, Dict, Any
from ..core.deps import require_auth_or_trial
from ..core.db import get_session
from sqlmodel import Session, select
from ..models.models import ReviewSheet
from ..services.agent_service import llm

router = APIRouter()


Difficulty = Literal["easy", "medium", "hard", "competition"]
QType = Literal["single", "tf", "fill", "short"]

ALL_DIFFICULTIES = ("easy", "medium", "hard", "competition")
ALL_QTYPES = ("single", "tf", "fill", "short")


class TypeCounts(BaseModel):
    single: int = 0
    tf: int = 0
    fill: int = 0
    short: int = 0


class DiffCounts(BaseModel):
    easy: int = 0
    medium: int = 0
    hard: int = 0
    competition: int = 0


class TestGenerateRequest(BaseModel):
    review_sheet_id: Optional[int] = None
    text: Optional[str] = None
    lang: Optional[str] = None  # 'zh' | 'en'
    length: Literal["short", "medium", "long"] = "short"  # maps to total count (fallback)
    type_counts: Optional[TypeCounts] = None  # custom per-type counts
    difficulty: Optional[str] = None  # legacy: single difficulty or "mixed" (ignored if diff_counts set)
    diff_counts: Optional[DiffCounts] = None  # custom per-difficulty counts


class TestQuestion(BaseModel):
    id: int
    type: QType
    difficulty: Difficulty
    stem: str
    choices: Optional[List[str]] = None  # for single
    answer: Any  # index for single; bool for tf; str for short/fill
    explanation: Optional[str] = None


def _alloc_counts(total: int, ratios: List[int]) -> List[int]:
    s = sum(ratios) or 1
    base = [total * r // s for r in ratios]
    rem = total - sum(base)
    # distribute remainder by largest fractional part heuristic -> here simple round-robin
    i = 0
    while rem > 0:
        base[i % len(base)] += 1
        rem -= 1
        i += 1
    return base


@router.post("/generate")
def generate_test(payload: TestGenerateRequest, _ctx=Depends(require_auth_or_trial), session: Session = Depends(get_session)):
    # Resolve material
    text = (payload.text or "").strip()
    if (not text) and payload.review_sheet_id:
        rs = session.get(ReviewSheet, payload.review_sheet_id)
        if rs and rs.content:
            text = rs.content
    if not text:
        return {"ok": False, "error": "Empty text"}

    is_en = (payload.lang or "zh").lower().startswith("en")

    # Resolve per-type counts
    if payload.type_counts:
        tc = payload.type_counts
        t_single = max(0, tc.single)
        t_tf = max(0, tc.tf)
        t_fill = max(0, tc.fill)
        t_short = max(0, tc.short)
    else:
        fallback_total = 10 if payload.length == "short" else (20 if payload.length == "medium" else 50)
        alloc = _alloc_counts(fallback_total, [5, 3, 0, 2])  # single, tf, fill, short
        t_single, t_tf, t_fill, t_short = alloc

    total = t_single + t_tf + t_fill + t_short
    if total <= 0:
        return {"ok": False, "error": "Total question count must be > 0"}
    if total > 80:
        return {"ok": False, "error": "Maximum 80 questions"}

    # Difficulty distribution
    if payload.diff_counts:
        dc = payload.diff_counts
        d_easy = max(0, dc.easy)
        d_medium = max(0, dc.medium)
        d_hard = max(0, dc.hard)
        d_competition = max(0, dc.competition)
        diff_total = d_easy + d_medium + d_hard + d_competition
        if diff_total != total:
            # Scale to match total
            if diff_total > 0:
                d_easy, d_medium, d_hard, d_competition = _alloc_counts(total, [d_easy, d_medium, d_hard, d_competition])
            else:
                d_easy, d_medium, d_hard, d_competition = _alloc_counts(total, [4, 3, 2, 1])
        diff_spec = {"easy": d_easy, "medium": d_medium, "hard": d_hard, "competition": d_competition}
    else:
        raw_diff = (payload.difficulty or "mixed").strip().lower()
        if raw_diff in ALL_DIFFICULTIES:
            diff_spec = {d: (total if d == raw_diff else 0) for d in ALL_DIFFICULTIES}
        else:
            d_easy, d_medium, d_hard, d_competition = _alloc_counts(total, [4, 3, 2, 1])
            diff_spec = {"easy": d_easy, "medium": d_medium, "hard": d_hard, "competition": d_competition}

    # Build strict JSON prompt
    schema = {
        "questions": [
            {
                "id": 1,
                "type": "single|tf|fill|short",
                "difficulty": "easy|medium|hard|competition",
                "stem": "question text",
                "choices": ["A", "B", "C", "D"],
                "answer": "index(for single) | true/false(for tf) | text(for fill/short)",
                "explanation": "why this is correct (concise)"
            }
        ]
    }

    sys = (
        "You are an exam item writer. Generate a strictly valid JSON matching the requested schema only. No extra text."
        if is_en else
        "你是一名命题老师。只输出严格有效的 JSON，必须符合请求的结构，严禁添加任何额外文本。"
    )

    def make_block(label: str, count: int) -> str:
        if count <= 0:
            return ""
        if is_en:
            return f"Type: {label} | Count: {count}."
        else:
            return f"题型：{label} ｜ 数量：{count}。"

    instr = []
    type_names_en = {"single": "single-choice", "tf": "true/false", "fill": "fill-in-the-blank", "short": "short-answer"}
    type_names_zh = {"single": "单选题", "tf": "判断题", "fill": "填空题", "short": "解答题"}

    if is_en:
        instr.append(
            "Create a test based on the review sheet. Respect the exact type counts specified below."
        )
        instr.append("Question types: single-choice (4 options, exactly 1 correct), true/false, fill-in-the-blank, short answer.")
        instr.append("Return JSON with key 'questions' only. Each question requires: id, type, difficulty, stem, choices (for single), answer, explanation.")
        instr.append("For single-choice: provide 4 plausible options in 'choices'; 'answer' is the 0-based index of the correct option.")
        instr.append("For true/false: 'answer' is true or false.")
        instr.append("For fill-in-the-blank: stem should contain one or more blanks marked as '____'; 'answer' is the correct text to fill in (if multiple blanks, separate with ' | ').")
        instr.append("For short answer: 'answer' is a concise reference answer. Keep explanation short.")
        instr.append("Calibrate difficulty to the review sheet's level: avoid trivial copy-and-paste recall and avoid out-of-scope advanced puzzles.")
        instr.append(
            "Anchor definitions: easy = direct recall/definition from the sheet; medium = example-driven application of ONE concept; "
            "hard = multi-concept integration or minor extension; competition = challenging problems requiring creative thinking, "
            "multi-step reasoning, or combining concepts in non-obvious ways — these should push beyond the sheet while remaining grounded in its topics."
        )
        instr.append(
            "All questions must be answerable using ONLY the given review sheet; explanations should briefly reference the relevant term/formula or section title from the sheet."
        )
    else:
        instr.append(
            "基于复习单生成模拟测试。请严格按照下方指定的各题型数量出题。"
        )
        instr.append("题型定义：单选题（4个选项，且仅1个正确）、判断题（是/否）、填空题、解答题。")
        instr.append("仅返回包含 'questions' 键的 JSON。每题包含：id、type、difficulty、stem、choices（仅单选）、answer、explanation。")
        instr.append("单选题：提供4个具有迷惑性的选项；answer 为正确选项的 0 基索引。")
        instr.append("判断题：answer 为 true 或 false。")
        instr.append("填空题：题干中用 '____' 标记空白处；answer 为应填入的正确文本（若多个空，用 ' | ' 分隔）。")
        instr.append("解答题：answer 为精炼参考答案；explanation 简短说明。")
        instr.append("难度需与复习单的技术深度相匹配：避免过于浅显的照抄回忆题，也避免超纲过难的题目。")
        instr.append(
            "难度锚点：简单 = 基本概念/定义直接回忆；中等 = 以示例/情境驱动的单一概念应用；"
            "困难 = 多概念组合或小幅延伸；竞赛 = 需要创造性思维、多步推导或以非显而易见的方式整合概念的挑战性问题——应超越复习单表层，但仍以其主题为根基。"
        )
        instr.append("所有题目必须仅依赖给定复习单即可作答；解析中请简要引用相关的术语/公式或小节标题以作依据。")

    blocks = []
    for qtype, count in [("single", t_single), ("tf", t_tf), ("fill", t_fill), ("short", t_short)]:
        if count > 0:
            label = type_names_en[qtype] if is_en else type_names_zh[qtype]
            blocks.append(make_block(label, count))

    user = (
        ("Review sheet (excerpt):\n" + text[:12000] + "\n\n") if is_en else ("复习提要（摘录）：\n" + text[:12000] + "\n\n")
    )
    user += ("Total questions: " + str(total) + "\n") if is_en else ("总题数：" + str(total) + "\n")
    user += "\n".join(instr) + "\n\n"
    user += ("Type blocks:\n" if is_en else "题型分配：\n") + "\n".join([f"- {b}" for b in blocks if b]) + "\n\n"
    # Difficulty distribution instruction
    diff_zh_map = {"easy": "简单", "medium": "中等", "hard": "困难", "competition": "竞赛"}
    if is_en:
        diff_line = "Difficulty distribution across the entire test: " + ", ".join(
            f"{d}: {diff_spec[d]}" for d in ALL_DIFFICULTIES if diff_spec[d] > 0
        ) + ". Ensure each question is tagged with the correct difficulty."
    else:
        diff_line = "整套试卷的难度分配：" + "、".join(
            f"{diff_zh_map[d]}：{diff_spec[d]}题" for d in ALL_DIFFICULTIES if diff_spec[d] > 0
        ) + "。请确保每题标注正确的难度。"
    user += diff_line + "\n\n"
    user += ("Output schema example (JSON only, keys in English):\n" if is_en else "输出结构示例（仅 JSON，键名使用英文）：\n")
    import json as _json
    user += _json.dumps(schema, ensure_ascii=False)

    content = llm.chat([
        {"role": "system", "content": sys},
        {"role": "user", "content": user},
    ], temperature=0.4)

    # Parse JSON
    import json
    data: Dict[str, Any] = {}
    try:
        data = json.loads(content)
    except Exception:
        import re
        m = re.search(r"\{[\s\S]*\}$", content.strip())
        if m:
            try:
                data = json.loads(m.group(0))
            except Exception:
                data = {}
    if not isinstance(data, dict) or "questions" not in data or not isinstance(data["questions"], list):
        return {"ok": False, "error": "LLM did not return valid JSON."}
    # Normalize & clamp structure
    questions: List[Dict[str, Any]] = []
    next_id = 1
    for q in data["questions"]:
        try:
            qtype = str(q.get("type", "")).lower()
            if qtype not in ALL_QTYPES:
                continue
            diff = str(q.get("difficulty", "")).lower()
            if diff not in ALL_DIFFICULTIES:
                diff = "medium"
            stem = str(q.get("stem", "")).strip()
            if not stem:
                continue
            item: Dict[str, Any] = {
                "id": next_id,
                "type": qtype,
                "difficulty": diff,
                "stem": stem,
                "explanation": (q.get("explanation") or "")[:500],
            }
            if qtype == "single":
                ch = q.get("choices") or []
                choices = [str(x) for x in ch][:4]
                if len(choices) < 4:
                    continue
                ans = q.get("answer")
                try:
                    ai = int(ans)
                except Exception:
                    ai = 0
                ai = max(0, min(3, ai))
                item["choices"] = choices
                item["answer"] = ai
            elif qtype == "tf":
                ans = q.get("answer")
                item["answer"] = bool(ans)
            elif qtype == "fill":
                item["answer"] = str(q.get("answer") or "").strip()[:800]
            else:  # short
                item["answer"] = str(q.get("answer") or "").strip()[:800]
            questions.append(item)
            next_id += 1
        except Exception:
            continue

    # Trim to total
    if len(questions) > total:
        questions = questions[:total]
    from collections import defaultdict
    cnt_by_type = defaultdict(int)
    for q in questions:
        cnt_by_type[q["type"]] += 1
    need = {"single": t_single, "tf": t_tf, "fill": t_fill, "short": t_short}
    meta = {
        "target_total": total,
        "target_types": need,
        "actual_types": dict(cnt_by_type),
        "diff_spec": diff_spec,
    }
    return {"ok": True, "items": questions, "meta": meta}


class ScoreRequest(BaseModel):
    items: List[TestQuestion]
    answers: Dict[int, Any] | Dict[str, Any]
    lang: Optional[str] = None
    review_text: Optional[str] = None


@router.post("/score")
def score_test(payload: ScoreRequest):
    lang = (payload.lang or "zh").lower()
    is_en = lang.startswith("en")
    # Normalize answers key to int
    norm_answers: Dict[int, Any] = {}
    for k, v in (payload.answers or {}).items():
        try:
            ik = int(k)
        except Exception:
            continue
        norm_answers[ik] = v
    results: List[Dict[str, Any]] = []
    shorts: List[TestQuestion] = []
    short_user: Dict[int, str] = {}
    correct = 0
    # Auto-grade single & tf; collect short/fill for LLM
    for it in payload.items:
        ans = norm_answers.get(it.id, None)
        if it.type == "single":
            try:
                ai = int(ans) if ans is not None else -1
            except Exception:
                ai = -1
            ok = (ai == it.answer)
            if ok:
                correct += 1
            results.append({"id": it.id, "type": it.type, "correct": ok, "score": 1 if ok else 0})
        elif it.type == "tf":
            sval = str(ans).lower()
            aval = bool(it.answer)
            if sval in ("true", "1", "yes", "y", "t"):
                u = True
            elif sval in ("false", "0", "no", "n", "f"):
                u = False
            else:
                try:
                    u = bool(ans)
                except Exception:
                    u = False
            ok = (u == aval)
            if ok:
                correct += 1
            results.append({"id": it.id, "type": it.type, "correct": ok, "score": 1 if ok else 0})
        else:
            # fill / short answer -> LLM grading
            user_text = str(ans or "").strip()
            shorts.append(it)
            short_user[it.id] = user_text
    # LLM grade short answers in batch
    if shorts:
        context = (payload.review_text or "")[:12000]
        # Build a compact JSON-in JSON prompt
        if is_en:
            sys = (
                "You are a strict but fair grader. Grade SHORT answers using ONLY the given review sheet content as ground truth."
                " Return STRICT JSON with an array 'scores', elements {id, score, reason}. Score is 0 or 1."
            )
            guide = (
                "Grading rules: award 1 if the student's answer semantically matches the reference answer based on the sheet (allow synonyms/paraphrases);"
                " award 0 if key points are missing, incorrect, or out of scope. Keep reasons concise (<=120 chars)."
            )
        else:
            sys = (
                "你是一名严格但公正的阅卷老师。仅依据给定复习单内容判分简答题。"
                " 仅输出严格 JSON，包含数组 'scores'，每个元素 {id, score, reason}；score 为 0 或 1。"
            )
            guide = (
                "判分规则：若学生答案与参考答案在语义上等价/关键要点一致（允许同义/转述），给 1 分；"
                " 若缺失关键要点/表述错误/超出复习单范围，给 0 分。理由简洁（<=120字）。"
            )
        import json as _json
        ref_items = [
            {
                "id": it.id,
                "ref": (str(it.answer or "")[:800]),
                "student": short_user.get(it.id, "")[:800],
            }
            for it in shorts
        ]
        user = (
            ("Review sheet:\n" + context + "\n\n") if is_en else ("复习提要：\n" + context + "\n\n")
        )
        user += guide + "\n\n"
        user += ("Items (JSON):\n" if is_en else "待判题目（JSON）：\n") + _json.dumps(ref_items, ensure_ascii=False)
        reply = llm.chat([
            {"role": "system", "content": sys},
            {"role": "user", "content": user},
        ], temperature=0.0)
        # Parse JSON
        import json, re
        data = {}
        try:
            data = json.loads(reply)
        except Exception:
            m = re.search(r"\{[\s\S]*\}$", reply.strip())
            if m:
                try:
                    data = json.loads(m.group(0))
                except Exception:
                    data = {}
        scores_map: Dict[int, Dict[str, Any]] = {}
        if isinstance(data, dict) and isinstance(data.get("scores"), list):
            for it in data["scores"]:
                try:
                    iid = int(it.get("id"))
                    sc = 1 if int(it.get("score", 0)) >= 1 else 0
                    rsn = str(it.get("reason", ""))[:200]
                    scores_map[iid] = {"score": sc, "reason": rsn}
                except Exception:
                    continue
        # Merge back
        for it in shorts:
            sc = scores_map.get(it.id, {"score": 0, "reason": ""})
            if sc["score"] >= 1:
                correct += 1
            results.append({
                "id": it.id,
                "type": it.type,
                "correct": sc["score"] >= 1,
                "score": sc["score"],
                "reason": sc["reason"],
            })
    total = len(payload.items)
    return {"ok": True, "results": results, "totals": {"correct": correct, "total": total}}
