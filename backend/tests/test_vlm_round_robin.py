import json
import sys
import types
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services import agent_service, file_service


class _FakeChatCompletions:
    def __init__(self, label: str, should_fail: bool = False):
        self.label = label
        self.should_fail = should_fail
        self.calls = 0

    def create(self, model, messages, temperature, max_tokens=None):
        self.calls += 1
        if self.should_fail:
            raise RuntimeError(f"{self.label} failed")
        return types.SimpleNamespace(
            choices=[
                types.SimpleNamespace(
                    message=types.SimpleNamespace(content=f"{self.label}:{model}")
                )
            ]
        )


class _FakeClient:
    def __init__(self, label: str, should_fail: bool = False):
        self.chat = types.SimpleNamespace(completions=_FakeChatCompletions(label, should_fail))


def test_llm_provider_round_robins_across_configured_endpoints(monkeypatch):
    monkeypatch.setattr(
        agent_service.settings,
        "LLM_API_CONFIGS",
        json.dumps([
            {"name": "endpoint-a", "provider": "openai", "model": "gpt-4o-mini", "api_key": "key-a"},
            {"name": "endpoint-b", "provider": "openai", "model": "gpt-4.1-mini", "api_key": "key-b"},
        ]),
        raising=False,
    )
    monkeypatch.setattr(agent_service.settings, "VLM_API_CONFIGS", None, raising=False)

    created = {}

    def fake_build_client(self, config):
        client = _FakeClient(config.name)
        created[config.name] = client
        return client

    monkeypatch.setattr(agent_service.LLMProvider, "_build_client", fake_build_client)

    provider = agent_service.LLMProvider()
    first = provider.chat([{"role": "user", "content": "hello"}])
    second = provider.chat([{"role": "user", "content": "hello again"}])
    third = provider.chat([{"role": "user", "content": "once more"}])

    assert first == "endpoint-a:gpt-4o-mini"
    assert second == "endpoint-b:gpt-4.1-mini"
    assert third == "endpoint-a:gpt-4o-mini"
    assert created["endpoint-a"].chat.completions.calls == 2
    assert created["endpoint-b"].chat.completions.calls == 1


def test_llm_provider_fails_over_to_next_endpoint(monkeypatch):
    monkeypatch.setattr(
        agent_service.settings,
        "LLM_API_CONFIGS",
        json.dumps([
            {"name": "endpoint-a", "provider": "openai", "model": "gpt-4o-mini", "api_key": "key-a"},
            {"name": "endpoint-b", "provider": "openai", "model": "gpt-4o-mini", "api_key": "key-b"},
        ]),
        raising=False,
    )
    monkeypatch.setattr(agent_service.settings, "VLM_API_CONFIGS", None, raising=False)

    def fake_build_client(self, config):
        return _FakeClient(config.name, should_fail=(config.name == "endpoint-a"))

    monkeypatch.setattr(agent_service.LLMProvider, "_build_client", fake_build_client)

    provider = agent_service.LLMProvider()
    result = provider.chat([{"role": "user", "content": "need fallback"}])

    assert result == "endpoint-b:gpt-4o-mini"


def test_sniff_and_read_uses_vlm_for_images(monkeypatch):
    captured = {}

    def fake_summary(filename, image_payloads, extracted_text="", lang="zh"):
        captured["filename"] = filename
        captured["payloads"] = image_payloads
        return "visual summary from image"

    monkeypatch.setattr(file_service, "summarize_visual_material", fake_summary)
    monkeypatch.setattr(file_service, "ocr_image_bytes", lambda data: "")

    content = file_service.sniff_and_read("diagram.png", b"\x89PNG\r\n\x1a\nmock")

    assert content == "visual summary from image"
    assert captured["filename"] == "diagram.png"
    assert captured["payloads"][0]["url"].startswith("data:image/png;base64,")


def test_sniff_and_read_uses_vlm_for_scanned_pdf(monkeypatch):
    monkeypatch.setattr(file_service, "read_pdf_bytes", lambda data: "")
    monkeypatch.setattr(
        file_service,
        "_extract_pdf_visual_payloads",
        lambda data: [{"label": "page 1", "url": "data:image/png;base64,AAAA", "detail": "auto"}],
    )
    monkeypatch.setattr(
        file_service,
        "summarize_visual_material",
        lambda filename, image_payloads, extracted_text="", lang="zh": "visual summary from scanned pdf",
    )

    content = file_service.sniff_and_read("scan.pdf", b"%PDF-1.7")

    assert content == "visual summary from scanned pdf"