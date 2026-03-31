from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime


class Doc(BaseModel):
    id: str
    filename: str
    content_type: str
    size: int
    text_length: int
    uploaded_at: datetime


class DocResponse(BaseModel):
    id: str
    filename: str
    content_type: str
    size: int
    text_length: int
    uploaded_at: datetime


class SummaryRequest(BaseModel):
    style: Literal["concise", "detailed", "bullet_points"] = "Detailed"


class SummaryResponse(BaseModel):
    doc_id: str
    style: str
    summary: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    response: str
    history: list[ChatMessage]


class ExtractResponse(BaseModel):
    doc_id: str
    entities: list[str] = []
    dates: list[str] = []
    figures: list[str] = []
