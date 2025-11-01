from typing import Dict, Any
from uuid import uuid4


class ReviewSheetService:
    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}

    def create(self, user_id: str | None, data: Dict[str, Any]) -> str:
        rid = str(uuid4())
        self._store[rid] = {"user_id": user_id, "data": data}
        return rid

    def get(self, rid: str) -> Dict[str, Any] | None:
        return self._store.get(rid)


review_sheet_service = ReviewSheetService()
