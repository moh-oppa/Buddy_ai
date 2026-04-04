import ollama
import httpx
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List
import uuid
from fastapi import FastAPI, HTTPException, Request, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os


from schemas import (
    DocResponse,
    SummaryRequest,
    SummaryResponse,
    ChatRequest,
    ChatResponse,
    ExtractResponse,
    Doc,
    ChatMessage,
)
from utilities import parse_docx, parse_pdf, parse_text

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    api_key = os.getenv("AI_API_KEY")
    ollama_host = os.getenv("AI_HOST", "https://api.ollama.com")
    ollama_model = os.getenv("AI_MODEL", "llama3")
    if not api_key:
        raise RuntimeError("AI_API_KEY environment variable is not set.")

    app.state.client = ollama.AsyncClient(host=ollama_host, headers={"Authorization": f"Bearer {api_key}"})
    app.state.model = ollama_model
    app.state.documents = {}

    try:
        models = await app.state.ollama_client.list()
        available = [m.model for m in models.models]

        if ollama_model not in available:
            raise RuntimeError(f"Model '{ollama_model}' not found. Available: {available}")

        print(f"Ollama client initialised — model: {ollama_model}")
    except Exception as e:
        raise RuntimeError(f"Ollama not reachable at {ollama_host}: {e}")

    print("Ai client initialised")
    print("Document store initialised")

    yield

    print("Shutting down!")


app = FastAPI(title="BuddyAI API", description="AI powered document reader ", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=['"http://localhost:5173"'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_CONTENT_TYPES = [
    "application/pdf",
    "text/plain",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]

STYLE_TEMPLATE = {
    "concise": "Provide a brief summary of the key points.",
    "detailed": "Provide a comprehensive summary of the document.",
    "bullet_points": "Present the information in a list of clear bullet points.",
}

MAX_TEXT_LENGTH = 80000


@app.get("/buddyai")
async def root():
    return {"message": "Welcome to the BuddyAI!"}


# @app.get("/test-client")
# async def test_client(request: Request):
#     client = request.app.state.client
#     return {"client_ready": client is not None}


@app.get("/buddyai/health")
async def health_check():
    return {"status": "OK", "version": "1.0.0", "time": datetime.now(timezone.utc).isoformat()}


@app.get("/buddyai/docs", response_model=List[DocResponse])
async def all_docs(request: Request):
    docs = request.app.state.documents
    if not docs:
        raise HTTPException(status_code=404, detail="No documents available!")
    return list(docs.values())


@app.post("/buddyai/upload_doc")
async def upload_doc(request: Request, doc: UploadFile = File(...)):
    if doc.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type!")

    if doc.content_type == "application/pdf":
        content = await parse_pdf(doc)

    elif doc.content_type == "text/plain":
        content = await parse_text(doc)

    elif doc.content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        content = await parse_docx(doc)

    doc_id = str(uuid.uuid4())

    new_doc = Doc(
        id=doc_id,
        name=doc.filename,
        type=doc.content_type,
        size=doc.size,
        text=content,
        truncated=len(content) == MAX_TEXT_LENGTH,
        uploaded_at=datetime.now(timezone.utc),
    )
    request.app.state.documents[new_doc.id] = new_doc

    return DocResponse(
        id=doc_id,
        name=doc.filename,
        size=doc.size,
        truncated=len(content) == MAX_TEXT_LENGTH,
        uploaded_at=datetime.now(timezone.utc),
    )


@app.delete("/buddyai/docs/{doc_id}")
async def delete_doc(request: Request, doc_id: str):
    docs = request.app.state.documents
    if doc_id not in docs:
        raise HTTPException(status_code=404, detail="Document not found!")

    del docs[doc_id]
    return {"message": f"Document {doc_id} deleted successfully!"}


@app.post("/buddyai/summarize/{doc_id}", response_model=SummaryResponse)
async def summary(request: Request, body: SummaryRequest, doc_id: str):
    docs = request.app.state.documents
    if doc_id not in docs:
        raise HTTPException(status_code=404, detail="Document not found")

    doc = docs[doc_id]
    template = STYLE_TEMPLATE[body.style]
    short = request.app.state.client.messages.create(...)

    return SummaryResponse(doc_id=doc_id, style=body.style, summary=short)
