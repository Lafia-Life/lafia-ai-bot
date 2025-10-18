from typing import List, Optional

from pydantic import BaseModel, HttpUrl


class DocumentSummary(BaseModel):
    document_id: str
    filename: str
    page_count: int = 0
    source_type: str = "pdf"
    url: Optional[str] = None


class UploadResponse(BaseModel):
    document: DocumentSummary
    chunks_indexed: int


class ChatRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None


class ScrapeRequest(BaseModel):
    url: HttpUrl


class Citation(BaseModel):
    document_id: str
    filename: str
    page_start: int
    page_end: int
    score: float
    excerpt: str
    source_type: str = "pdf"
    url: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation]
