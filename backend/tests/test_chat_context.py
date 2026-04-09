import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.db import engine
from app.core.jwt import sign_jwt
from app.main import app
from app.models.models import ReviewSheet
from app.routes import chat as chat_route
from app.services import agent_service


def _auth_headers(user_id: int) -> dict[str, str]:
    token = sign_jwt(f"local:{user_id}", "local")
    return {"Authorization": f"Bearer {token}"}


def test_answer_questions_uses_recent_dialogue(monkeypatch):
    captured: dict[str, object] = {}

    def fake_chat(messages, temperature=0.2):
        captured["messages"] = messages
        return "A1: 最稳定的一个典型画法是两个 S=O 和一个 S-O^-。"

    monkeypatch.setattr(agent_service.llm, "chat", fake_chat)

    answers = agent_service.answer_questions(
        "SO3 可通过比较形式电荷判断更稳定结构。",
        ["答案是？"],
        history=[
            {"role": "user", "content": "给我一个类似于 ClO2- 的题目。"},
            {"role": "assistant", "content": "请绘制 SO3 的路易斯结构，并比较形式电荷。"},
        ],
        study_context="科目: chemistry\n课程: inorganic chemistry",
    )

    assert answers == ["最稳定的一个典型画法是两个 S=O 和一个 S-O^-。"]
    messages = captured["messages"]
    assert any(message["role"] == "assistant" and "SO3" in message["content"] for message in messages)
    assert any("学习上下文" in message["content"] and "chemistry" in message["content"] for message in messages)


def test_chat_route_passes_history_and_study_context(monkeypatch):
    user_id = 9411
    headers = _auth_headers(user_id)
    captured: dict[str, object] = {}

    def fake_answer_questions(context, questions, lang="zh", history=None, study_context=""):
        captured["context"] = context
        captured["questions"] = questions
        captured["history"] = history
        captured["study_context"] = study_context
        return ["参考上一轮题目，SO3 的较稳定画法通常是两个双键和一个单键。"]

    monkeypatch.setattr(chat_route, "answer_questions", fake_answer_questions)

    with Session(engine) as session:
        review_sheet = ReviewSheet(
            user_id=user_id,
            kind="review_sheet_pro",
            content="Lewis 结构判断时先看总价电子数，再比较形式电荷。",
            subject_code="chemistry",
            course_name="Inorganic Chemistry",
            exam_type="quiz",
            exam_name="FC Practice",
            selected_chapter_labels=json.dumps(["Lewis 结构", "形式电荷"], ensure_ascii=False),
        )
        session.add(review_sheet)
        session.commit()
        session.refresh(review_sheet)
        review_sheet_id = review_sheet.id

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            headers=headers,
            json={
                "review_sheet_id": str(review_sheet_id),
                "question": "答案是？",
                "history": [
                    {"role": "user", "content": "给我一个类似于 ClO2- 的题目，就是需要用 FC 来做下一步的。"},
                    {"role": "assistant", "content": "绘制 SO3 的路易斯结构，并计算形式电荷以确定最稳定结构。"},
                ],
            },
        )

    assert response.status_code == 200
    assert response.json()["text"].startswith("参考上一轮题目")
    assert captured["questions"] == ["答案是？"]
    assert captured["history"] == [
        {"role": "user", "content": "给我一个类似于 ClO2- 的题目，就是需要用 FC 来做下一步的。"},
        {"role": "assistant", "content": "绘制 SO3 的路易斯结构，并计算形式电荷以确定最稳定结构。"},
    ]
    assert "Lewis 结构判断时先看总价电子数" in str(captured["context"])
    assert "科目: chemistry" in str(captured["study_context"])
    assert "课程: Inorganic Chemistry" in str(captured["study_context"])
    assert "章节范围: Lewis 结构，形式电荷" in str(captured["study_context"])