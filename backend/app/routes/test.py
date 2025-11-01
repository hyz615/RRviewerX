from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Optional, Literal, Dict, Any
from ..core.deps import require_auth_or_trial
from ..core.db import get_session
from sqlmodel import Session, select
from ..models.models import ReviewSheet
from ..services.agent_service import llm

router = APIRouter()


Difficulty = Literal["easy", "medium", "hard"]
QType = Literal["single", "tf", "short"]


class TestGenerateRequest(BaseModel):
    review_sheet_id: Optional[int] = None
    text: Optional[str] = None
    lang: Optional[str] = None  # 'zh' | 'en'
    length: Literal["short", "medium", "long"] = "short"  # maps to total count


class TestQuestion(BaseModel):
    id: int
    type: QType
    difficulty: Difficulty
    stem: str
    choices: Optional[List[str]] = None  # for single
    answer: Any  # index for single; bool for tf; str for short
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
    # totals
    total = 10 if payload.length == "short" else (20 if payload.length == "medium" else 50)
    # type ratio 5:3:2 => single, tf, short
    type_counts = _alloc_counts(total, [5, 3, 2])
    # difficulty ratio 5:3:2 inside each type to ensure global mix
    def diff_counts(n: int) -> List[int]:
        return _alloc_counts(n, [5, 3, 2])  # easy, medium, hard

    # Build strict JSON prompt
    schema = {
        "questions": [
            {
                "id": 1,
                "type": "single|tf|short",
                "difficulty": "easy|medium|hard",
                "stem": "question text",
                "choices": ["A", "B", "C", "D"],
                "answer": "index(for single) | true/false(for tf) | text(for short)",
                "explanation": "why this is correct (concise)"
            }
        ]
    }

    sys = (
        "You are an exam item writer. Generate a strictly valid JSON matching the requested schema only. No extra text."
        if is_en else
        "你是一名命题老师。只输出严格有效的 JSON，必须符合请求的结构，严禁添加任何额外文本。"
    )

    def make_block(label: str, count: int, t: QType) -> str:
        e, m, h = diff_counts(count)
        if is_en:
            return (
                f"Type: {label} | Count: {count} | Difficulty split (easy/medium/hard): {e}/{m}/{h}. "
                "Mix the difficulties naturally."
            )
        else:
            return (
                f"题型：{label} ｜ 数量：{count} ｜ 难度分配（易/中/难）：{e}/{m}/{h}。在该题型中自然混合难度。"
            )

    instr = []
    if is_en:
        instr.append(
            "Create a mixed test based on the review sheet. Respect BOTH constraints: (1) question type ratio single:tf:short = 5:3:2; (2) difficulty ratio easy:medium:hard = 5:3:2 across the entire test."
        )
        instr.append("Question types: single-choice (4 options, exactly 1 correct), true/false, short answer.")
        instr.append("Return JSON with key 'questions' only. Each question requires: id, type, difficulty, stem, choices (for single), answer, explanation.")
        instr.append("For single-choice: provide 4 plausible options in 'choices'; 'answer' is the 0-based index of the correct option.")
        instr.append("For true/false: 'answer' is true or false.")
        instr.append("For short answer: 'answer' is a concise reference answer. Keep explanation short.")
        # Difficulty calibration to sheet level
        instr.append("Calibrate difficulty to the review sheet's level: avoid trivial copy-and-paste recall and avoid out-of-scope advanced puzzles.")
        instr.append(
            "Anchor definitions: easy = direct recall/definition from the sheet; medium = example-driven application of ONE concept (you may propose a new scenario/example not verbatim in the sheet, but solvable entirely by the sheet); hard = slightly beyond the sheet: multi-concept integration or minor extension that pushes thinking just past the sheet while still strongly tied to it (avoid requiring outside specialized knowledge)."
        )
        instr.append(
            "All questions must be answerable using ONLY the given review sheet; explanations should briefly reference the relevant term/formula or section title from the sheet."
        )
    else:
        instr.append(
            "基于复习单生成混合模拟测试。需同时满足：(1) 题型比例 单选:判断:文字 = 5:3:2；(2) 难度比例 易:中:难 = 5:3:2（在整套题中混合）。"
        )
        instr.append("题型定义：单选题（4个选项，且仅1个正确）、判断题（是/否）、文字题（简答题）。")
        instr.append("仅返回包含 'questions' 键的 JSON。每题包含：id、type、difficulty、stem、choices（仅单选）、answer、explanation。")
        instr.append("单选题：提供4个具有迷惑性的选项；answer 为正确选项的 0 基索引。")
        instr.append("判断题：answer 为 true 或 false。")
        instr.append("文字题：answer 为精炼参考答案；explanation 简短说明。")
        # 难度与复习单匹配
        instr.append("难度需与复习单的技术深度相匹配：避免过于浅显的照抄回忆题，也避免超纲过难的题目。")
        instr.append(
            "难度锚点：易 = 基本概念/定义直接回忆；中 = 以示例/情境驱动的单一概念应用（可使用复习单未逐字出现的新例子，但完全可依复习单知识求解）；难 = 略微超出复习单表层：多概念组合或小幅延伸，促使思考略跨一步，但仍与复习单强关联（不可依赖额外的专业外部知识）。"
        )
        instr.append("所有题目必须仅依赖给定复习单即可作答；解析中请简要引用相关的术语/公式或小节标题以作依据。")

    t_single, t_tf, t_short = type_counts
    blocks = [
        make_block("单选题" if not is_en else "single-choice", t_single, "single"),
        make_block("判断题" if not is_en else "true/false", t_tf, "tf"),
        make_block("文字题" if not is_en else "short-answer", t_short, "short"),
    ]

    user = (
        ("Review sheet (excerpt):\n" + text[:12000] + "\n\n") if is_en else ("复习提要（摘录）：\n" + text[:12000] + "\n\n")
    )
    user += ("Total questions: " + str(total) + "\n") if is_en else ("总题数：" + str(total) + "\n")
    user += "\n".join(instr) + "\n\n"
    user += ("Type blocks:\n" if is_en else "题型分配：\n") + "\n".join([f"- {b}" for b in blocks]) + "\n\n"
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
        # Try direct
        data = json.loads(content)
    except Exception:
        # Fallback: extract JSON substring
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
            if qtype not in ("single", "tf", "short"):
                continue
            diff = str(q.get("difficulty", "")).lower()
            if diff not in ("easy", "medium", "hard"):
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
            else:  # short
                item["answer"] = str(q.get("answer") or "").strip()[:800]
            questions.append(item)
            next_id += 1
        except Exception:
            continue

    # If counts deviate too much, trim/pad heuristically
    # Trim to total
    if len(questions) > total:
        questions = questions[:total]
    # Basic guarantee: ensure at least 1 per type when expected >0
    from collections import defaultdict
    cnt_by_type = defaultdict(int)
    for q in questions:
        cnt_by_type[q["type"]] += 1
    need = {
        "single": type_counts[0],
        "tf": type_counts[1],
        "short": type_counts[2],
    }
    # No complex rebalancing; just report meta
    meta = {
        "target_total": total,
        "target_types": {"single": need["single"], "tf": need["tf"], "short": need["short"]},
        "actual_types": cnt_by_type,
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
    # Auto-grade single & tf; collect short
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
                # best effort cast
                try:
                    u = bool(ans)
                except Exception:
                    u = False
            ok = (u == aval)
            if ok:
                correct += 1
            results.append({"id": it.id, "type": it.type, "correct": ok, "score": 1 if ok else 0})
        else:
            # short answer -> LLM grading later
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
