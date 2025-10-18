from typing import List, Optional

from pydantic import BaseModel


class DocumentSummary(BaseModel):
    document_id: str
    filename: str
    page_count: int


class UploadResponse(BaseModel):
    document: DocumentSummary
    chunks_indexed: int


class ChatRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None


class Citation(BaseModel):
    document_id: str
    filename: str
    page_start: int
    page_end: int
    score: float


class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation]
