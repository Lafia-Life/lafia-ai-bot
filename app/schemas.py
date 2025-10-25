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


class SMSWebhookRequest(BaseModel):
    """Incoming SMS webhook from Africa's Talking"""
    to: str  # Your shortcode/number
    from_: str  # Sender's phone number
    text: str  # SMS message content
    date: str  # Timestamp
    id: str  # Message ID
    linkId: Optional[str] = None
    
    class Config:
        fields = {"from_": "from"}


class SMSResponse(BaseModel):
    """Response for SMS operations"""
    success: bool
    message: str
    message_id: Optional[str] = None


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
