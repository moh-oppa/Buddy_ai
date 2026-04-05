import ollama
import json
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
        models = await app.state.client.list()
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


@app.post("/buddyai/summary/{doc_id}", response_model=SummaryResponse)
async def summary(request: Request, body: SummaryRequest, doc_id: str):
    docs = request.app.state.documents
    if doc_id not in docs:
        raise HTTPException(status_code=404, detail="Document not found")

    doc = docs[doc_id]
    template = f"""You are a document analyst. {STYLE_TEMPLATE[body.style]} This is the document content: {doc.text} """
    short = request.app.state.client.chat(
        model="llama3",
        messages=[
            {"role": "system", "content": template},
            {"role": "user", "content": "summarize the provided document."},
        ],
    )

    summary_text = short["message"]["content"]

    return SummaryResponse(doc_id=doc_id, style=body.style, summary=summary_text)


@app.post("/buddyai/chat/{doc_id}", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest, doc_id: str):
    docs = request.app.state.documents
    if doc_id not in docs:
        raise HTTPException(status_code=404, detail="Document not found!")

    doc = docs[doc_id]

    system_prompt = f"""You are a document analyst that answers questions about the provided document. Only use the information from the document to answer all questions. If the document does not contain the information needed to answer a question, respond with 'I don't know.' The document content is: {doc.text}"""
    messages = [{"role": "system", "content": system_prompt}]

    for msg in body.history:
        messages.append({"role": msg.role, "content": msg.content})

    messages.append({"role": "user", "content": body.message})

    response = request.app.state.client.chat(model="llama3", messages=messages)

    reply = response["message"]["content"]

    update_history = list(body.history) + [
        ChatMessage(role="user", content=body.message),
        ChatMessage(role="assistant", content=reply),
    ]

    return ChatResponse(response=reply, history=update_history)


@app.post("/buddyai/extract/{doc_id}", response_model=ExtractResponse)
async def extract(request: Request, doc_id: str):
    docs = request.app.state.documents
    if doc_id not in docs:
        raise HTTPException(status_code=404, detail="Document not found!")

    doc = docs[doc_id]

    system_prompt = f"""You are a document data analyst that extracts key information from the provided document. Extract information from the document provided and return a JSON object.Raw JSON only and it must be in the following structure: 
    {{"entities": ["list of named people, organizations, places"], "dates": ["list of all dates and time references"], "figures": ["list of all numbers, statistics, monetary values"]}} 
    The document content is: {doc.text}
    """

    response = request.app.state.client.chat(
        model="llama3",
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": "Extract the information as a JSON object with three fields: 'entities', 'dates', and 'figures'.",
            },
        ],
    )

    content = response["message"]["content"]

    try:
        extraction = json.loads(content)
        data = httpx.get(content).json()
        entities = data.get("entities", [])
        dates = data.get("dates", [])
        figures = data.get("figures", [])
    except json.JSONDecodeError:
        extraction = {"entities": [], "dates": [], "figures": []}

    return ExtractResponse(
        doc_id=doc_id,
        entities=extraction.get("entities", []),
        dates=extraction.get("dates", []),
        figures=extraction.get("figures", []),
    )
