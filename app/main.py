from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
import uuid

from app.config import Settings, get_openai_api_key, get_settings
from app.schemas import ChatRequest, DocumentSummary, ScrapeRequest, UploadResponse, SMSWebhookRequest, SMSResponse
from app.services.document_store import DocumentStore
from app.services.ingestion import ingest_document, ingest_web_page
from app.services.retrieval import stream_answer, answer_question
from app.services.sms_service import send_sms_response, parse_incoming_sms
from app.whatsapp_chat import app as whatsapp_app
from app.schemas import VideoUploadRequest,VideoResource


app = FastAPI(title="PDF Chat Assistant")
app.mount("/webhook", whatsapp_app)


settings = get_settings()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def get_document_store() -> DocumentStore:
    return DocumentStore(settings.chroma_path)


def _resolve_document_path(document_id: str, store: DocumentStore) -> tuple[DocumentSummary, Path]:
    summary = store.get(document_id)
    if summary is None or summary.source_type != "pdf":
        raise HTTPException(status_code=404, detail="Document not found.")

    matches = sorted(settings.uploads_path.glob(f"{document_id}_*"))
    if not matches:
        raise HTTPException(status_code=404, detail="Stored PDF could not be located.")

    return summary, matches[0]


@app.get("/", response_class=HTMLResponse)
@app.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("chat.html", {"request": request})


@app.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("upload.html", {"request": request})


@app.get("/sms-admin", response_class=HTMLResponse)
def sms_admin_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("sms_admin.html", {"request": request})


@app.get("/api/documents", response_model=list[DocumentSummary])
def list_documents(store: DocumentStore = Depends(get_document_store)) -> list[DocumentSummary]:
    return store.list()


@app.post("/api/documents", response_model=UploadResponse)
def upload_document(
    file: UploadFile = File(...),
) -> UploadResponse:
    contents = file.file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    response = ingest_document(
        upload_bytes=contents,
        filename=file.filename,
        content_type=file.content_type,
    )
    return response


@app.post("/api/scrape", response_model=UploadResponse)
def scrape_document(payload: ScrapeRequest) -> UploadResponse:
    try:
        return ingest_web_page(str(payload.url))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/chat")
def chat(payload: ChatRequest) -> StreamingResponse:
    if not get_openai_api_key():
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is required for chat responses. Configure a key or set OPENAI_BASE_URL for your provider.",
        )
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question is required.")
    return StreamingResponse(stream_answer(payload), media_type="application/x-ndjson")


@app.get("/documents/{document_id}/download")
def download_document(document_id: str, store: DocumentStore = Depends(get_document_store)) -> FileResponse:
    summary, file_path = _resolve_document_path(document_id, store)
    return FileResponse(file_path, media_type="application/pdf", filename=summary.filename)


@app.get("/documents/{document_id}/inline")
def inline_document(document_id: str, store: DocumentStore = Depends(get_document_store)) -> FileResponse:
    summary, file_path = _resolve_document_path(document_id, store)
    headers = {"Content-Disposition": f'inline; filename="{summary.filename}"'}
    return FileResponse(file_path, media_type="application/pdf", headers=headers)


@app.post("/api/sms/webhook", response_model=SMSResponse)
async def sms_webhook(request: Request) -> SMSResponse:
    """
    Webhook endpoint for incoming SMS from Africa's Talking
    Receives SMS questions and responds with AI answers
    """
    try:
        # Get form data from Africa's Talking webhook
        form_data = await request.form()
        webhook_data = dict(form_data)
        
        # Map 'from' to 'from_' for Pydantic model
        if 'from' in webhook_data:
            webhook_data['from_'] = webhook_data.pop('from')
        
        # Parse incoming SMS
        sms = parse_incoming_sms(webhook_data)
        
        # Validate that we have required data
        if not sms.text.strip() or not sms.from_:
            return SMSResponse(
                success=False, 
                message="Invalid SMS data received"
            )
        
        # Process the question using existing chat logic
        chat_request = ChatRequest(question=sms.text.strip())
        
        # Get answer from AI (non-streaming version)
        try:
            chat_response = answer_question(chat_request)
            ai_answer = chat_response.answer
        except Exception as e:
            ai_answer = "Sorry, I'm having trouble processing your question right now. Please try again later."
        
        # Send SMS response
        sms_sent = await send_sms_response(
            phone_number=sms.from_,
            question=sms.text.strip(),
            answer=ai_answer
        )
        
        if sms_sent:
            return SMSResponse(
                success=True,
                message="SMS response sent successfully",
                message_id=sms.id
            )
        else:
            return SMSResponse(
                success=False,
                message="Failed to send SMS response"
            )
            
    except Exception as e:
        return SMSResponse(
            success=False,
            message=f"Error processing SMS: {str(e)}"
        )


@app.post("/api/sms/send", response_model=SMSResponse)
async def send_sms_manual(payload: dict) -> SMSResponse:
    """
    Manual SMS sending endpoint for testing
    Expected payload: {"phone_number": "+256...", "message": "..."}
    """
    settings = get_settings()
    if not settings.africas_talking_api_key:
        raise HTTPException(
            status_code=503,
            detail="SMS service not configured. Set AFRICAS_TALKING_API_KEY in environment."
        )
    
    phone_number = payload.get("phone_number")
    message = payload.get("message")
    
    if not phone_number or not message:
        raise HTTPException(
            status_code=400,
            detail="phone_number and message are required"
        )
    
    try:
        success = await send_sms_response(phone_number, "Manual Test", message)
        
        return SMSResponse(
            success=success,
            message="SMS sent successfully" if success else "Failed to send SMS - check server logs for details"
        )
    except Exception as e:
        return SMSResponse(
            success=False,
            message=f"SMS error: {str(e)}"
        )


@app.get("/api/sms/config-status")
def sms_config_status():
    """Check SMS service configuration status"""
    settings = get_settings()
    
    configured = bool(settings.africas_talking_api_key and settings.africas_talking_username)
    
    return {
        "configured": configured,
        "username": settings.africas_talking_username if configured else None,
        "api_key_masked": f"atsk_...{settings.africas_talking_api_key[-8:]}" if settings.africas_talking_api_key else None
    }


@app.post("/api/sms/debug")
async def debug_sms_api(payload: dict):
    """Debug endpoint to test Africa's Talking API directly"""
    import httpx
    
    settings = get_settings()
    phone_number = payload.get("phone_number", "+000000000")
    message = payload.get("message", "Debug test from MoH AI")
    
    # Format phone number
    if phone_number.startswith('0'):
        phone_number = '+256' + phone_number[1:]
    elif not phone_number.startswith('+'):
        phone_number = '+256' + phone_number
    
    headers = {
        'apiKey': settings.africas_talking_api_key,
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json'
    }
    
    data = {
        'username': settings.africas_talking_username,
        'to': phone_number,
        'message': message
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.sandbox.africastalking.com/version1/messaging",
                headers=headers,
                data=data,
                timeout=30.0
            )
            
            return {
                "status_code": response.status_code,
                "response_text": response.text,
                "headers_sent": dict(headers),
                "data_sent": data,
                "phone_formatted": phone_number
            }
    except Exception as e:
        return {
            "error": str(e),
            "headers_sent": dict(headers),
            "data_sent": data
        }


@app.post("/api/sms/test-webhook")
async def test_webhook_flow(request: Request):
    """
    Test webhook flow without actually sending SMS
    Shows what the AI response would be
    """
    try:
        # Get form data from Africa's Talking webhook
        form_data = await request.form()
        webhook_data = dict(form_data)
        
        # Map 'from' to 'from_' for Pydantic model
        if 'from' in webhook_data:
            webhook_data['from_'] = webhook_data.pop('from')
        
        # Parse incoming SMS
        sms = parse_incoming_sms(webhook_data)
        
        # Process the question using existing chat logic
        chat_request = ChatRequest(question=sms.text.strip())
        
        # Get answer from AI
        try:
            chat_response = answer_question(chat_request)
            ai_answer = chat_response.answer
            citations = chat_response.citations
        except Exception as e:
            ai_answer = f"Error processing question: {str(e)}"
            citations = []
        
        # Format SMS response (without sending)
        sms_message = f"Q: {sms.text[:50]}{'...' if len(sms.text) > 50 else ''}\n\nA: {ai_answer}\n\n--\nMoH E-Learning Assistant"
        
        return {
            "success": True,
            "incoming_sms": {
                "from": sms.from_,
                "to": sms.to,
                "text": sms.text,
                "id": sms.id
            },
            "ai_response": {
                "answer": ai_answer,
                "citations_count": len(citations)
            },
            "sms_response": {
                "message": sms_message,
                "length": len(sms_message),
                "estimated_parts": (len(sms_message) // 155) + 1
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "webhook_data": webhook_data
        }
    
@app.post("/api/videos")
def upload_video(payload: VideoUploadRequest):
    """Upload a video link (no file processing, just store the metadata)"""
    settings = get_settings()
    document_store = DocumentStore(settings.chroma_path)
    
    # Create a document entry for the video
    document_id = str(uuid.uuid4())
    
    video_data = {
        "title": payload["title"],
        "url": payload["url"],
        "type": payload["type"],
        "description": payload.get("description", "")
    }
    
    summary = DocumentSummary(
        document_id=document_id,
        filename=payload["title"],
        page_count=1,
        source_type="video",
        url=payload["url"],
        is_video=True,
        video_data=video_data
    )
    
    document_store.upsert(summary)
    
    return UploadResponse(document=summary, chunks_indexed=0)
