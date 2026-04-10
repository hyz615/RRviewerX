import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services import agent_service


def test_infer_textbook_structure_prefers_llm_boundaries(monkeypatch):
    calls = {"count": 0}

    def fake_chat(messages, temperature=0.2, purpose="llm", max_tokens=None):
        calls["count"] += 1
        assert purpose == "llm"
        assert "1: Topic A: Limits" in messages[-1]["content"]
        return (
            '{"units":[{"title":"Calculus","chapters":['
            '{"title":"Limits","start_line":1,"heading_text":"Topic A: Limits"},'
            '{"title":"Derivatives","start_line":4,"heading_text":"Topic B: Derivatives"}'
            ']}]}'
        )

    monkeypatch.setattr(agent_service.llm, "has_client", lambda purpose="llm": True)
    monkeypatch.setattr(agent_service.llm, "chat", fake_chat)

    text = (
        "Topic A: Limits\n"
        "epsilon delta continuity\n"
        "\n"
        "Topic B: Derivatives\n"
        "slope tangent rate of change\n"
    )

    result = agent_service.infer_textbook_structure(text, "calc_textbook.txt")

    assert calls["count"] == 1
    assert result["strategy"] == "llm"
    assert [
        chapter["title"]
        for unit in result["units"]
        for chapter in unit["chapters"]
    ] == ["Limits", "Derivatives"]
    assert result["units"][0]["title"] == "Calculus"
    assert "epsilon delta continuity" in result["units"][0]["chapters"][0]["content"]
    assert "slope tangent rate of change" in result["units"][0]["chapters"][1]["content"]


def test_infer_textbook_structure_prefers_toc_and_skips_toc_content(monkeypatch):
    calls = {"count": 0}

    def fake_chat(messages, temperature=0.2, purpose="llm", max_tokens=None):
        calls["count"] += 1
        assert "目录条目" in messages[-1]["content"] or "TOC entries" in messages[-1]["content"]
        assert "Chapter 1 Limits ........ 1" in messages[-1]["content"]
        assert "epsilon delta continuity" not in messages[-1]["content"]
        return (
            '{"units":[{"title":"Calculus","chapters":['
            '{"title":"Limits","source_text":"Chapter 1 Limits ........ 1"},'
            '{"title":"Derivatives","source_text":"Chapter 2 Derivatives ........ 25"}'
            ']}]}'
        )

    monkeypatch.setattr(agent_service.llm, "has_client", lambda purpose="llm": True)
    monkeypatch.setattr(agent_service.llm, "chat", fake_chat)

    text = (
        "Contents\n"
        "Chapter 1 Limits ........ 1\n"
        "Chapter 2 Derivatives ........ 25\n"
        "\n"
        "Chapter 1 Limits\n"
        "epsilon delta continuity\n"
        "\n"
        "Chapter 2 Derivatives\n"
        "slope tangent rate of change\n"
    )

    result = agent_service.infer_textbook_structure(text, "calc_textbook.txt")

    assert calls["count"] == 1
    assert result["strategy"] == "toc_llm"
    assert [
        chapter["title"]
        for unit in result["units"]
        for chapter in unit["chapters"]
    ] == ["Limits", "Derivatives"]
    first_content = result["units"][0]["chapters"][0]["content"]
    assert first_content.startswith("Chapter 1 Limits")
    assert "Contents" not in first_content
    assert "........ 1" not in first_content


def test_infer_textbook_structure_falls_back_to_heading_rules_when_llm_invalid(monkeypatch):
    calls = {"count": 0}

    def fake_chat(messages, temperature=0.2, purpose="llm", max_tokens=None):
        calls["count"] += 1
        return "not-json"

    monkeypatch.setattr(agent_service.llm, "has_client", lambda purpose="llm": True)
    monkeypatch.setattr(agent_service.llm, "chat", fake_chat)

    text = (
        "Chapter 1 Limits\n"
        "epsilon delta continuity\n"
        "\n"
        "Chapter 2 Derivatives\n"
        "slope tangent rate of change\n"
    )

    result = agent_service.infer_textbook_structure(text, "calc_textbook.txt")

    assert calls["count"] == 1
    assert result["strategy"] == "headings"
    assert [
        chapter["title"]
        for unit in result["units"]
        for chapter in unit["chapters"]
    ] == ["Limits", "Derivatives"]
