from pydantic import BaseModel, Field, ConfigDict
from typing import Literal
from datetime import datetime


class Doc(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    type: str
    size: int
    text: str
    uploaded_at: datetime


class DocResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    size: int
    uploaded_at: datetime


class SummaryRequest(BaseModel):
    style: Literal["concise", "detailed", "bullet_points"] = "detailed"


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
