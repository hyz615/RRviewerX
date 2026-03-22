from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..core.db import get_session
from ..core.deps import get_current_user
from ..models.entities import Ticket, LocalUser, TicketReply
router = APIRouter()

class TicketCreate(BaseModel):
	subject: str
	content: str

@router.post("/tickets")
def create_ticket(body: TicketCreate, current=Depends(get_current_user), session: Session = Depends(get_session)):
	if current is None:
		raise HTTPException(status_code=401, detail="Unauthorized")
	subject = (body.subject or "").strip()
	content = (body.content or "").strip()
	if not subject or not content:
		raise HTTPException(status_code=400, detail="subject and content are required")
	t = Ticket(user_id=current, subject=subject, content=content, status="open")
	session.add(t)
	session.commit()
	session.refresh(t)
	return {"ok": True, "id": t.id}

@router.get("/my")
def list_my(current=Depends(get_current_user), session: Session = Depends(get_session)):
	if current is None:
		raise HTTPException(status_code=401, detail="Unauthorized")
	rows = session.exec(select(Ticket).where(Ticket.user_id == current).order_by(Ticket.id.desc())).all()
	return {"ok": True, "items": [
		{"id": x.id, "subject": x.subject, "content": x.content, "status": x.status, "created_at": x.created_at.isoformat(), "updated_at": x.updated_at.isoformat()} for x in rows
	]}

def _require_admin(current: int | None, session: Session) -> LocalUser:
	if current is None:
		raise HTTPException(status_code=401, detail="Unauthorized")
	u = session.get(LocalUser, current)
	if not u or not u.is_admin:
		raise HTTPException(status_code=403, detail="Forbidden")
	return u

@router.get("/tickets")
def admin_list_all(current=Depends(get_current_user), session: Session = Depends(get_session)):
	_require_admin(current, session)
	rows = session.exec(select(Ticket).order_by(Ticket.id.desc())).all()
	items = []
	for x in rows:
		replies = session.exec(select(TicketReply).where(TicketReply.ticket_id == x.id).order_by(TicketReply.id.asc())).all()
		items.append({
			"id": x.id,
			"user_id": x.user_id,
			"subject": x.subject,
			"content": x.content,
			"status": x.status,
			"created_at": x.created_at.isoformat(),
			"updated_at": x.updated_at.isoformat(),
			"replies": [
				{"id": r.id, "author_id": r.author_id, "author_role": r.author_role, "content": r.content, "created_at": r.created_at.isoformat()}
				for r in replies
			]
		})
	return {"ok": True, "items": items}

class TicketStatusBody(BaseModel):
	status: str  # open|in_progress|resolved|closed

@router.post("/tickets/{ticket_id}/status")
def admin_set_status(ticket_id: int, body: TicketStatusBody, current=Depends(get_current_user), session: Session = Depends(get_session)):
	_require_admin(current, session)
	t = session.get(Ticket, ticket_id)
	if not t:
		raise HTTPException(status_code=404, detail="Ticket not found")
	new_status = (body.status or "").strip().lower()
	if new_status not in {"open", "in_progress", "resolved", "closed"}:
		raise HTTPException(status_code=400, detail="Invalid status")
	from datetime import datetime, timezone
	t.status = new_status
	t.updated_at = datetime.now(timezone.utc)
	session.add(t)
	session.commit()
	return {"ok": True}


class ReplyCreateBody(BaseModel):
	content: str


@router.get("/tickets/{ticket_id}/replies")
def admin_list_replies(ticket_id: int, current=Depends(get_current_user), session: Session = Depends(get_session)):
	_require_admin(current, session)
	t = session.get(Ticket, ticket_id)
	if not t:
		raise HTTPException(status_code=404, detail="Ticket not found")
	replies = session.exec(select(TicketReply).where(TicketReply.ticket_id == ticket_id).order_by(TicketReply.id.asc())).all()
	return {"ok": True, "items": [
		{"id": r.id, "author_id": r.author_id, "author_role": r.author_role, "content": r.content, "created_at": r.created_at.isoformat()} for r in replies
	]}


@router.post("/tickets/{ticket_id}/replies")
def admin_add_reply(ticket_id: int, body: ReplyCreateBody, current=Depends(get_current_user), session: Session = Depends(get_session)):
	u = _require_admin(current, session)
	t = session.get(Ticket, ticket_id)
	if not t:
		raise HTTPException(status_code=404, detail="Ticket not found")
	content = (body.content or "").strip()
	if not content:
		raise HTTPException(status_code=400, detail="content required")
	r = TicketReply(ticket_id=ticket_id, author_id=u.id, author_role="admin", content=content)
	session.add(r)
	# also bump ticket updated_at
	from datetime import datetime, timezone
	t.updated_at = datetime.now(timezone.utc)
	session.add(t)
	session.commit()
	session.refresh(r)
	return {"ok": True, "id": r.id}
