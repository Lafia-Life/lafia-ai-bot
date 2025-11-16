from pathlib import Path
import fastapi
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile,Form
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
import uuid
import glob
import os
from datetime import datetime
from typing import Optional
from app.config import Settings, get_openai_api_key, get_settings
from app.schemas import VideoSummary,ChatRequest, DocumentSummary, ScrapeRequest, UploadResponse, SMSWebhookRequest, SMSResponse
from app.services.document_store import DocumentStore
from app.services.video_store import VideoStore
from app.services.ingestion import ingest_document, ingest_web_page
from app.services.retrieval import stream_answer, answer_question
from app.services.sms_service import send_sms_response, parse_incoming_sms
from app.whatsapp_chat import app as whatsapp_app
from app.schemas import VideoUploadRequest,VideoResource, VideoUploadResponse, VideoType, VideoSummary
from starlette.requests import Request
from starlette.responses import Response


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
    

# @app.post("/api/videos", response_model=VideoUploadResponse)
# async def upload_video(
#     file: UploadFile = File(None),
#     title: str = Form(...),
#     url: Optional[str] = Form(None),
#     type: str = Form(...),
#     description: Optional[str] = Form("")
# ):
#     """Upload a video - just store it, no ingestion"""
#     try:
#         print(f"🎬 Video storage request: {title}")
        
#         # Use VideoStore instead of DocumentStore
#         settings = get_settings()
#         video_store = VideoStore(settings.chroma_path)
        
#         # Create video ID
#         video_id = str(uuid.uuid4())
        
#         # Handle file if provided
#         video_bytes = None
#         filename = title + ".mp4"  # Default filename
        
#         if file and file.filename:
#             # Just read the bytes - NO PROCESSING
#             video_bytes = await file.read()
#             filename = file.filename
#             print(f"💾 Storing video file: {filename} ({len(video_bytes)} bytes)")
#         else:
#             print(f"🔗 Storing video URL: {url}")
        
#         # Convert string type to VideoType enum
#         try:
#             video_type_enum = VideoType(type)
#         except ValueError:
#             raise HTTPException(status_code=400, detail="Invalid video type")
        
#         # Save video file (just stores bytes, no processing)
#         saved_path = video_store.save_video_file(
#             video_bytes if video_bytes else b"",  # Empty bytes for URL-only videos
#             filename, 
#             video_id
#         )
        
#         # Create VideoSummary (NOT DocumentSummary)
#         video_summary = VideoSummary(
#             video_id=video_id,
#             title=title,
#             url=url,
#             type=video_type_enum,
#             description=description,
#             filename=filename,
#             file_path=str(saved_path),
#             created_at=datetime.now().isoformat(), 
#             duration=None
#         )
        
#         # Store in VideoStore (NOT DocumentStore)
#         video_store.upsert(video_summary)
        
#         # Return VideoUploadResponse (NOT UploadResponse)
#         return VideoUploadResponse(
#             video=video_summary,
#             message=f"Video '{title}' stored successfully"
#         )
        
#     except Exception as e:
#         print(f"Video storage error: {str(e)}")
#         raise HTTPException(status_code=500, detail=str(e))
def debug_storage_layout():
    """Debug the actual storage layout"""
    print("📁 STORAGE LAYOUT DEBUG:")
    
    locations = [
        Path("storage"),
        Path("storage/chroma"),
        Path("storage/uploads"),
        Path("storage/chroma/uploads"),
        Path("storage/chroma/videos"),
        Path("storage/chroma/documents"),
    ]
    
    for location in locations:
        if location.exists():
            print(f"✅ {location}: EXISTS")
            try:
                files = list(location.glob("*"))
                print(f"   Files: {[f.name for f in files[:5]]}")  # Show first 5 files
            except Exception as e:
                print(f"   Error listing: {e}")
        else:
            print(f"❌ {location}: DOES NOT EXIST")
    
    # Check where documents are actually stored
    print("\n🔍 DOCUMENT STORAGE LOCATION:")
    settings = get_settings()
    print(f"Chroma path: {settings.chroma_path}")
    print(f"Chroma path exists: {settings.chroma_path.exists()}")
    
@app.post("/api/videos", response_model=VideoUploadResponse)
async def upload_video(
    file: UploadFile = File(None),
    title: str = Form(...),
    url: Optional[str] = Form(None),
    type: str = Form(...),
    description: Optional[str] = Form("")
):
    """Upload a video - store it in the same uploads folder as documents"""
    try:
        print(f"🎬 Video storage request: {title}")
        
        # Debug storage layout first
        debug_storage_layout()
        
        # Use VideoStore - it will now use the correct uploads location
        settings = get_settings()
        video_store = VideoStore(settings.chroma_path)
        
        # Create video ID
        video_id = str(uuid.uuid4())
        
        # Handle file if provided
        video_bytes = None
        filename = title + ".mp4"  # Default filename
        
        if file and file.filename:
            # Read the file bytes
            video_bytes = await file.read()
            filename = file.filename
            mime_type = file.content_type or 'video/mp4'
            print(f"💾 Storing video file: {filename} ({len(video_bytes)} bytes)")
        else:
            mime_type = 'video/mp4'
            print(f"🔗 Storing video URL: {url}")
        
        # Convert string type to VideoType enum
        try:
            video_type_enum = VideoType(type)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid video type")
        
        # Save video file to documents uploads folder
        saved_path = video_store.save_video_file(
            video_bytes if video_bytes else b"",
            filename, 
            video_id
        )
        
        # Create VideoSummary with file path
        video_summary = VideoSummary(
            video_id=video_id,
            title=title,
            url=url,
            type=video_type_enum,
            description=description,
            filename=filename,
            file_path=str(saved_path),
            mime_type=mime_type,
            created_at=datetime.now().isoformat(), 
            duration=None
        )
        
        # Store in VideoStore
        video_store.upsert(video_summary)
        
        print(f"✅ Video stored in documents uploads folder: {saved_path}")
        
        return VideoUploadResponse(
            video=video_summary,
            message=f"Video '{title}' stored successfully"
        )
        
    except Exception as e:
        print(f"Video storage error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    

@app.get("/debug/routes")
async def debug_routes():
    """Show all registered routes"""
    routes = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            routes.append({
                "path": route.path,
                "methods": list(route.methods),
                "name": getattr(route, "name", "N/A")
            })
    return {"routes": routes}

@app.get("/test-simple")
async def test_simple():
    """Simple test endpoint to check if server is working"""
    return {"status": "success", "message": "Server is running"}


@app.get("/debug/video-files")
async def debug_video_files():
    """Check if video files actually exist on disk"""
    
    video_files = []
    
    # Check storage/uploads directory
    upload_dirs = [
        "storage/uploads",
        "uploads", 
        "./storage/uploads",
        "../storage/uploads"
    ]
    
    for upload_dir in upload_dirs:
        if os.path.exists(upload_dir):
            print(f"🔍 Checking directory: {upload_dir}")
            for ext in ['*.mp4', '*.mov', '*.avi', '*.mkv']:
                files = glob.glob(os.path.join(upload_dir, ext))
                for file_path in files:
                    file_size = os.path.getsize(file_path)
                    video_files.append({
                        'filename': os.path.basename(file_path),
                        'path': file_path,
                        'size_bytes': file_size,
                        'size_mb': round(file_size / (1024 * 1024), 2)
                    })
    
    return {
        "video_files_found": len(video_files),
        "upload_dirs_checked": upload_dirs,
        "files": video_files
    }


@app.get("/debug/video-path")
async def debug_video_path():
    """Debug the exact file path"""
    filename = "0fd72f21-175a-46e3-8980-c86d86b8f07d_testvideo.mp4"
    safe_filename = os.path.basename(filename)
    
    locations = [
        "storage/uploads",
        "uploads", 
        "storage",
        "./storage/uploads",
        "../storage/uploads"
    ]
    
    results = []
    
    for location in locations:
        file_path = os.path.join(location, safe_filename)
        normalized_path = os.path.normpath(file_path)
        exists = os.path.exists(normalized_path)
        
        results.append({
            'location': location,
            'file_path': file_path,
            'normalized_path': normalized_path,
            'exists': exists,
            'size': os.path.getsize(normalized_path) if exists else 0
        })
    
    return {"filename": safe_filename, "checks": results}

@app.get("/serve-video/{filename}")
@app.head("/serve-video/{filename}")
async def serve_video(filename: str, request: Request):
    """Serve video files - with HEAD method support"""
    print(f"🎬 SERVE VIDEO REQUEST: {request.method} {filename}")
    
    safe_filename = os.path.basename(filename)
    file_path = os.path.join("storage", "uploads", safe_filename)
    absolute_path = os.path.abspath(file_path)
    
    if not os.path.exists(absolute_path):
        raise HTTPException(status_code=404, detail=f"Video file not found: {safe_filename}")
    
    file_size = os.path.getsize(absolute_path)
    print(f"✅ FOUND VIDEO: {absolute_path} ({file_size} bytes)")
    
    headers = {
        'Content-Type': 'video/mp4',
        'Content-Length': str(file_size),
        'Content-Disposition': f'inline; filename="{safe_filename}"',
        'Cache-Control': 'no-cache',
        'Accept-Ranges': 'bytes'
    }
    
    # If HEAD request, return headers only
    if request.method == "HEAD":
        return Response(headers=headers)
    
    # If GET request, return the file
    return FileResponse(
        path=absolute_path,
        media_type='video/mp4',
        filename=safe_filename,
        headers=headers
    )

@app.get("/debug/actual-files")
async def debug_actual_files():
    """Show exactly what files exist in storage directories"""
    locations = ["storage/uploads", "uploads", "storage"]
    
    results = {}
    
    for location in locations:
        if os.path.exists(location):
            files = []
            for item in os.listdir(location):
                item_path = os.path.join(location, item)
                if os.path.isfile(item_path):
                    files.append({
                        'name': item,
                        'size': os.path.getsize(item_path),
                        'path': os.path.abspath(item_path)
                    })
            results[location] = {
                'exists': True,
                'files': files,
                'absolute_path': os.path.abspath(location)
            }
        else:
            results[location] = {
                'exists': False,
                'absolute_path': os.path.abspath(location) if location else location
            }
    
    return results

@app.get("/debug/video-info/{filename}")
async def debug_video_info(filename: str):
    """Check if video meets WhatsApp requirements"""
    safe_filename = os.path.basename(filename)
    file_path = os.path.join("storage/uploads", safe_filename)
    
    if not os.path.exists(file_path):
        return {"error": "File not found", "path": file_path}
    
    file_size = os.path.getsize(file_path)
    file_size_mb = round(file_size / (1024 * 1024), 2)
    
    # Check WhatsApp limits
    whatsapp_compatible = file_size_mb <= 16
    is_mp4 = safe_filename.lower().endswith('.mp4')
    
    return {
        "filename": safe_filename,
        "file_path": file_path,
        "file_size_bytes": file_size,
        "file_size_mb": file_size_mb,
        "is_mp4": is_mp4,
        "whatsapp_compatible_size": whatsapp_compatible,
        "meets_requirements": whatsapp_compatible and is_mp4,
        "notes": "WhatsApp requires: MP4 format, max 16MB, H.264 video, AAC audio"
    }

@app.get("/debug/whatsapp-video-urls")
async def debug_whatsapp_video_urls():
    """Debug what video URLs WhatsApp is receiving"""
    from app.whatsapp_chat import get_available_courses
    
    courses = get_available_courses()
    results = {}
    
    for course_id, course_data in courses.items():
        videos = course_data.get('videos', [])
        course_results = []
        
        for video in videos:
            video_info = {
                'title': video.get('title'),
                'type': video.get('type'),
                'original_url': video.get('url'),
                'whatsapp_url': None
            }
            
            # Simulate what create_smart_video_response does
            if video.get('type') == 'uploaded':
                url = video.get('url', '')
                if url.startswith('/'):
                    filename = os.path.basename(url)
                    video_info['whatsapp_url'] = f"https://8cdbf1c1aba5.ngrok-free.app/serve-video/{filename}"
                else:
                    video_info['whatsapp_url'] = url
            
            course_results.append(video_info)
        
        if course_results:
            results[course_id] = course_results
    
    return results