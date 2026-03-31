from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
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

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise RuntimeError("API_KEY environment variable is not set.")

    app.state.client = ai.AI(api_key=api_key)
    app.state.documents = {}
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


@app.get("/")
async def root():
    return {"message": "Welcome to the BuddyAI!"}


# @app.get("/test-client")
# async def test_client(request: Request):
#     client = request.app.state.client
#     return {"client_ready": client is not None}
