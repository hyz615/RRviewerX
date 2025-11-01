from __future__ import annotations
from typing import List
from .agent_service import llm
from ..core.config import settings

# We reuse openai-compatible client if available; else mock deterministic hash embedding.
try:
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore

_client = getattr(llm, "_client", None)
_model = settings.EMBEDDING_MODEL


def _mock_embed(texts: List[str]) -> List[List[float]]:
    import hashlib, math
    dim = settings.EMBEDDING_DIM
    out: List[List[float]] = []
    for t in texts:
        h = hashlib.sha256(t.encode("utf-8")).digest()
        # repeat hash to fill dim
        raw = (h * ((dim // len(h)) + 1))[:dim]
        vec = [ (b / 255.0) for b in raw ]
        # l2 normalize
        norm = math.sqrt(sum(v*v for v in vec)) or 1.0
        out.append([v / norm for v in vec])
    return out


def embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    if not _client:
        return _mock_embed(texts)
    try:
        resp = _client.embeddings.create(model=_model, input=texts)
        return [d.embedding for d in resp.data]
    except Exception:
        return _mock_embed(texts)
