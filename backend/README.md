# RRviewer Backend

FastAPI backend for RRviewer (Review Sheet Maker) by Yizhou Han.

## Features
- OAuth-ready endpoints (Google/Microsoft placeholders)
- One free trial before login required
- Upload, Generate, Chat APIs
- LangChain + LangGraph orchestration (OpenAI/DeepSeek)
- SQLite via SQLModel
- Unit tests with pytest
- Dockerfile + minimal CI stub

## Quickstart
1. Create and activate venv
2. Install dependencies
3. Copy `.env.example` to `.env` and set API keys
4. Run server

### Docker Compose (backend + frontend)
1. Optional: set env in a `.env` at repo root (OPENAI_API_KEY / DEEPSEEK_API_KEY)
2. Run `docker compose up --build`
3. Frontend at http://localhost:8080 , Backend at http://localhost:8000

## Endpoints
- `POST /auth/login` (provider: google|microsoft|anonymous)
- `GET /auth/trial-status`
- `POST /upload`
- `POST /generate` (outline|qa|flashcards)
- `POST /chat` (single/batch)

