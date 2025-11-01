from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List
from ..core.deps import require_auth_or_trial
from ..services.embedding_service import embed_texts

router = APIRouter()

class EmbedRequest(BaseModel):
    texts: List[str]

@router.post("")
async def create_embeddings(payload: EmbedRequest, ctx=Depends(require_auth_or_trial)):
    vecs = embed_texts(payload.texts)
    return {"ok": True, "vectors": vecs}
