import json
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session
from database import DocumentModel,get_db, create_table
from ollama import AsyncClient
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List
import uuid
from fastapi import FastAPI, HTTPException, Request, File, UploadFile, Depends
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
    ollama_host = os.getenv("AI_HOST", "https://ollama.com")
    ollama_model = os.getenv("AI_MODEL", "gpt-oss:120b")
    if not api_key:
        raise RuntimeError("BuddyAI_API_KEY environment variable is not set.")

    create_table()

    app.state.client = AsyncClient(host=ollama_host, headers={"Authorization": f"Bearer {api_key}"})
    app.state.model = ollama_model

    try:
        models = await app.state.client.list()
        available = [m.model for m in models.models]

        if ollama_model not in available:
            raise RuntimeError(f"Model '{ollama_model}' not found. Available: {available}")

        print(f"Ollama client initialised — model: {ollama_model}")
    except Exception as e:
        raise RuntimeError(f"Ollama not reachable at {ollama_host}: {e}")

    print("Ai client initialised")

    yield

    print("Shutting down!")


app = FastAPI(title="BuddyAI API", description="AI powered document reader ", version="1.0.0", lifespan=lifespan)

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

# Initialize the rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.get("/buddyai/docs", response_model=List[DocResponse])
async def all_docs(request: Request, db: Session = Depends(get_db)):
    docs = db.query(DocumentModel).all()
    if not docs:
        raise HTTPException(status_code=404, detail="No documents available!")

    return docs


@app.post("/buddyai/upload_doc")
@limiter.limit("5/minute")
async def upload_doc(request: Request, doc: UploadFile = File(...), db: Session = Depends(get_db)):

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
        truncated=len(content) > MAX_TEXT_LENGTH,
        uploaded_at=datetime.now(timezone.utc),
    )
    
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)

    return DocResponse(
        id=doc_id,
        name=doc.filename,
        size=doc.size,
        truncated=len(content) > MAX_TEXT_LENGTH,
        uploaded_at=new_doc.uploaded_at,
    )


@app.delete("/buddyai/docs/{doc_id}")
async def delete_doc(request: Request, doc_id: str, db: Session = Depends(get_db)):
    docs = db.query(DocumentModel).filter(DocumentModel.id == doc_id).first()
    if not docs:
        raise HTTPException(status_code=404, detail="Document not found!")

    db.delete(docs)
    db.commit()
    return {"message": f"Document {doc_id} deleted successfully!"}


@app.post("/buddyai/summary/{doc_id}", response_model=SummaryResponse)
@limiter.limit("30/minute")
async def summary(request: Request, body: SummaryRequest, doc_id: str, db: Session = Depends(get_db)):
    docs = db.query(DocumentModel).filter(DocumentModel.id == doc_id).first()
    if not docs:
        raise HTTPException(status_code=404, detail="Document not found")
    
    template = f"""You are a document analyst. {STYLE_TEMPLATE[body.style]} This is the document content: {doc.text} """
    try:
        short = await request.app.state.client.chat(
            model="gpt-oss:120b",
            messages=[
                {"role": "system", "content": template},
                {"role": "user", "content": "summarize the provided document."},
            ],
        )
    except Exception as e:
        raise RuntimeError(f"Unable to complete action: {e}")

    summary_text = short["message"]["content"]

    return SummaryResponse(doc_id=doc_id, style=body.style, summary=summary_text)


@app.post("/buddyai/chat/{doc_id}", response_model=ChatResponse)
@limiter.limit("30/minute")
async def chat(request: Request, body: ChatRequest, doc_id: str, db: Session = Depends(get_db)):
    docs = db.query(DocumentModel).filter(DocumentModel.id == doc_id).first()
    if not docs:
        raise HTTPException(status_code=404, detail="Document not found!")

    system_prompt = f"""You are a document analyst that answers questions about the provided document. Only use the information from the document to answer all questions. If the document does not contain the information needed to answer a question, respond with 'I don't know.' The document content is: {doc.text}"""
    messages = [{"role": "system", "content": system_prompt}]

    #adding chat history to the messages list
    for msg in body.history:
        messages.append({"role": msg.role, "content": msg.content})

    messages.append({"role": "user", "content": body.message})
    try:

        response = await request.app.state.client.chat(model="gpt-oss:120b", messages=messages)
    except Exception as e:
        raise RuntimeError(f"Unable to complete action: {e}")

    reply = response["message"]["content"]

    update_history = list(body.history) + [
        ChatMessage(role="user", content=body.message),
        ChatMessage(role="assistant", content=reply),
    ]

    return ChatResponse(response=reply, history=update_history)


@app.post("/buddyai/extract/{doc_id}", response_model=ExtractResponse)
@limiter.limit("30/minute")
async def extract(request: Request, doc_id: str, db: Session = Depends(get_db)):
    docs = db.query(DocumentModel).filter(DocumentModel.id == doc_id).first()
    if not docs:
        raise HTTPException(status_code=404, detail="Document not found!")

    system_prompt = f"""You are a document data analyst that extracts key information from the provided document. Extract information from the document provided and return a JSON object.Raw JSON only and it must be in the following structure: 
    {{"entities": ["list of named people, organizations, places"], "dates": ["list of all dates and time references"], "figures": ["list of all numbers, statistics, monetary values"]}} 
    The document content is: {docs.text}
    """
    try:
        response = await request.app.state.client.chat(
            model="gpt-oss:120b",
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": "Extract the information as a JSON object with three fields: 'entities', 'dates', and 'figures'.",
                },
            ],
        )
    except HTTPException:
        raise HTTPException(status_code=500, detail="Unable to complete action")

    content = response["message"]["content"]

    try:
        extraction = json.loads(content)
    except json.JSONDecodeError:
        extraction = {"entities": [], "dates": [], "figures": []}

    return ExtractResponse(
        doc_id=doc_id,
        entities=extraction.get("entities", []),
        dates=extraction.get("dates", []),
        figures=extraction.get("figures", []),
    )

@app.post("buddyai/chat/stream/{doc_id}")
async def chat_stream(request: Request, body: ChatRequest, doc_id: str, db: Session = Depends(get_db)):
    docs = db.query(DocumentModel).filter(DocumentModel.id == doc_id).first()
    if not docs:
        raise HTTPException(status_code=404, detail="Document not found!")

    system_prompt = f"""You are a document analyst that answers questions about the provided document. Only use the information from the document to answer all questions. If the document does not contain the information needed to answer a question, respond with 'I don't know.' The document content is: {docs.text}"""
    messages = [{"role": "system", "content": system_prompt}]

    for msg in body.history:
        messages.append({"role": msg.role, "content": msg.content})

    messages.append({"role": "user", "content": body.message})
    try:
        response = await request.app.state.client.chat(model="gpt-oss:120b", messages=messages, stream=True)
    except Exception as e:
        raise RuntimeError(f"Unable to complete action: {e}")

    async for chunk in response:
        yield chunk["message"]["content"]