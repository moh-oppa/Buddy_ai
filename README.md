# BuddyAI: chat with your documents

An AI document assistant. Upload a **PDF, DOCX or TXT** file, then:

- **Summarise** it in one of three styles: concise, detailed or bullet points.
- **Chat** with it. Answers are grounded in the document only, and the model says "I don't know" when th
e document doesn't cover the question.
- **Extract** named entities, dates and figures as structured JSON.

## Architecture

```
React frontend (Vite) ──► FastAPI backend ──► PostgreSQL (uploaded documents + extracted text)
                                │
                                └──► LLM via the Ollama API (default model: gpt-oss:120b)
```

- Text is parsed on upload (PyPDF2 / python-docx), capped at 80k characters, and stored in Postgres.
- Per-IP rate limiting with SlowAPI: 5 uploads per minute and 30 AI requests per minute.
- Chat is stateless on the server. The client sends the conversation history with each request.

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | List uploaded documents |
| `POST` | `/upload_doc` | Upload a document (multipart) |
| `DELETE` | `/buddyai/docs/{doc_id}` | Delete a document |
| `POST` | `/buddyai/summary/{doc_id}` | `{"style": "concise" \| "detailed" \| "bullet_points"}` |
| `POST` | `/buddyai/chat/{doc_id}` | `{"message": "...", "history": [...]}` |
| `POST` | `/buddyai/extract/{doc_id}` | Entities, dates and figures as JSON |

## Running locally

```bash
cd Buddyai-backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # set AI_API_KEY, AI_HOST, AI_MODEL, DATABASE_URL
uvicorn main:app --reload
```

API docs are at http://localhost:8000/docs.

## Tech stack

Python · FastAPI · SQLAlchemy · PostgreSQL · Ollama API · SlowAPI · PyPDF2 · python-docx · React

## Roadmap

- [ ] Streaming chat responses (Server-Sent Events)
- [ ] Chunking and embeddings (RAG) for documents larger than the context window
- [ ] Tests and CI
- [ ] Docker Compose setup
