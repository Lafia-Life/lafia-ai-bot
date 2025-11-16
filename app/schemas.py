from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, HttpUrl
from enum import Enum


class ResourceType(str, Enum):
    PDF = "pdf"
    VIDEO = "video"
    WEB = "web"
    IMAGE = "image"

class VideoResource(BaseModel):
    title: str
    url: str
    type: str  # "youtube", "direct"
    description: Optional[str] = None

class DocumentSummary(BaseModel):
    document_id: str
    filename: str
    page_count: int = 0
    source_type: str = "pdf"
    url: Optional[str] = None


class UploadResponse(BaseModel):
    document: DocumentSummary
    chunks_indexed: int
class VideoType(str, Enum):
    YOUTUBE = "youtube"
    DIRECT = "direct"
    UPLOAD = "upload"


class VideoSummary(BaseModel):
    video_id: str
    title: str
    url: Optional[str] = None
    type: VideoType
    description: Optional[str] = None
    filename: Optional[str] = None
    file_path: Optional[str] = None
    created_at: str 
    duration: Optional[str] = None


class UploadResponse(BaseModel):
    document: DocumentSummary
    chunks_indexed: int


class VideoUploadResponse(BaseModel):
    video: VideoSummary
    message: str


class VideoListResponse(BaseModel):
    videos: List[VideoSummary]


class VideoUploadRequest(BaseModel):
    title: str
    url: Optional[str] = None
    type: VideoType
    description: Optional[str] = None


# -----------------------------
# 💬 Chat Models
# -----------------------------
class ChatRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None


class Citation(BaseModel):
    """Represents a document snippet used as a citation in a response."""
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


# -----------------------------
# 🌐 Web Scraping
# -----------------------------
class ScrapeRequest(BaseModel):
    url: HttpUrl


# -----------------------------
# 📱 SMS Webhook & Response
# -----------------------------
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


# -----------------------------
# 🎥 Video Upload & Resource
# -----------------------------
class VideoUploadRequest(BaseModel):
    """Schema for uploading a video file."""
    title: str
    description: Optional[str] = None
    file_url: Optional[HttpUrl] = None


class VideoResource(BaseModel):
    """Schema representing a stored video resource."""
    id: Optional[int] = None
    title: str
    description: Optional[str] = None
    file_url: Optional[HttpUrl] = None
    upload_date: Optional[str] = None  # ISO formatted date string