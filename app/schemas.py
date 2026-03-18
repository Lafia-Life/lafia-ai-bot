from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from enum import Enum


class CourseCreate(BaseModel):
    title: str
    description: Optional[str] = None
    code: Optional[str] = None
    is_active: bool = True
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class CourseUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    code: Optional[str] = None
    is_active: Optional[bool] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class Course(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    code: Optional[str] = None
    is_active: bool = True
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    material_count: Optional[dict] = None
    class Config:
        from_attributes = True

class ResourceType(str, Enum):
    PDF = "pdf"
    VIDEO = "video"
    WEB = "web"
    IMAGE = "image"
    SCORM = "scorm"

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
    course_id: Optional[str] = None
    external_ref: Optional[str] = None
    moodle_cmid: Optional[str] = None


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
    course_id: Optional[str]=None

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
    context_prompt: Optional[str] = None
    allowed_course_ids: Optional[List[str]] = None
    allowed_source_types: Optional[List[str]] = None
    include_global_docs: bool = False
    document_scope: Optional[str] = None
    moodle_cmid: Optional[str] = None

    @field_validator("moodle_cmid", mode="before")
    @classmethod
    def normalize_moodle_cmid(cls, value):
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


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
    course_id: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation]


# -----------------------------
# 🌐 Web Scraping
# -----------------------------
class ScrapeRequest(BaseModel):
    url: HttpUrl
    course_id: Optional[str] = None
    moodle_cmid: Optional[str] = None


# -----------------------------
# 📱 SMS Webhook & Response
# -----------------------------
class SMSWebhookRequest(BaseModel):
    """Incoming SMS webhook from Africa's Talking"""
    to: str  # Your shortcode/number
    from_: str = Field(alias="from")  # Sender's phone number
    text: str  # SMS message content
    date: str  # Timestamp
    id: str  # Message ID
    linkId: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


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

class UserRegistration(BaseModel):
    phone_number: str
    name: str
    email: Optional[str] = None
    district: Optional[str] = None
    job_title: Optional[str] = None
    organization: Optional[str] = None
    password: str
    student_no: Optional[str]= None
    registered_at: datetime = datetime.now()

class Enrollment(BaseModel):
    id: str
    student_number: str
    course_id: str
    course_name: str
    enrolled_at: datetime
    completed_at: Optional[datetime] = None
    progress: float = 0.0  # 0.0 to 1.0
    is_active: bool = True
