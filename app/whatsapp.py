from dotenv import load_dotenv
import token
from urllib.parse import quote, urlparse, parse_qs, urlencode
import hashlib
import os
import mimetypes
import json
import functools
import subprocess
import tempfile
import shutil
import subprocess
from openai import base_url
import requests
from concurrent.futures import ThreadPoolExecutor
from twilio.rest import Client as TwilioClient
from fastapi import APIRouter, Form, Response, HTTPException, Query, Request,FastAPI  
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from app.config import get_settings
from app.schemas import ChatRequest
from app.services.retrieval import answer_question, answer_question_async
from datetime import datetime 
from app.services.document_store import DocumentStore
from app.services.video_store import VideoStore
from app.services.course_store import CourseStore
from pathlib import Path
import time
import asyncio
import threading
from app.services.moodle_service import (
    get_available_courses, 
    get_available_courses_async,
    clear_courses_cache,
    start_preload_worker,
    close_async_client,
    normalize_moodle_file_url,
    authenticate_moodle_user,
    authenticate_moodle_user_async,
    get_user_enrolled_courses_moodle,
    get_user_enrolled_courses_moodle_async,
    get_user_not_enrolled_courses,
    get_course_contents_moodle,
    get_course_contents_moodle_async,
    extract_moodle_resources,
    enroll_user_in_course,
    enroll_user_in_course_async,
    get_moodle_user_id,
    is_user_enrolled_in_course,
    is_user_enrolled_in_course_async,
    create_generic_content_response, 
    create_course_overview,          
    format_file_size,               
    categorize_file,
    get_last_course_sync_error,
    
)
from urllib.parse import quote, unquote, urlparse
import urllib3
import html
from twilio.rest import Client
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


load_dotenv()

# Create router instead of app
router = APIRouter()
app = FastAPI()
cache_lock = threading.Lock()
user_state = {}
settings = get_settings()
conversation_history = {}
document_store = DocumentStore(settings.chroma_path)
video_store = VideoStore(settings.chroma_path)
courses_store = CourseStore(Path("storage/data"))
document_path_cache = {}
courses_cache = {}
user_moodle_data = {} 
user_language = {}
courses_cache_timestamp = 0
CACHE_DURATION = 300  # 5 minutes

# ====== NEW: MOODLE USER AUTHENTICATION STORAGE ======
user_moodle_data = {} 

# Disable SSL warnings for Moodle
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
BASE_URL = os.getenv("BASE_URL")
twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
BLOCKING_MAX_WORKERS = int(os.getenv("WHATSAPP_BLOCKING_MAX_WORKERS", "100"))
BLOCKING_EXECUTOR = ThreadPoolExecutor(max_workers=BLOCKING_MAX_WORKERS)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")
WHATSAPP_ASYNC_QA = os.getenv("WHATSAPP_ASYNC_QA", "0").strip().lower() in {"1", "true", "yes", "on"}
WHATSAPP_ASYNC_VIDEO = os.getenv("WHATSAPP_ASYNC_VIDEO", "0").strip().lower() in {"1", "true", "yes", "on"}
WHATSAPP_OUTBOUND_WORKERS = int(os.getenv("WHATSAPP_OUTBOUND_WORKERS", "2"))

OUTBOUND_QUEUE = asyncio.Queue()

async def run_blocking(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    bound = functools.partial(func, *args, **kwargs)
    return await loop.run_in_executor(BLOCKING_EXECUTOR, bound)


def _twilio_ready() -> bool:
    return bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_NUMBER)


def _format_whatsapp_number(value: str) -> str:
    number = (value or "").strip()
    if not number:
        return number
    if number.startswith("whatsapp:"):
        return number
    return f"whatsapp:{number}"


async def _send_whatsapp_message(phone: str, body: str) -> bool:
    if not _twilio_ready():
        print("⚠️ Twilio not configured; skipping async send.")
        return False
    client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    to_number = _format_whatsapp_number(phone)
    from_number = _format_whatsapp_number(TWILIO_WHATSAPP_NUMBER)
    try:
        await run_blocking(
            client.messages.create,
            body=body,
            from_=from_number,
            to=to_number,
        )
        return True
    except Exception as e:
        print(f"❌ Twilio send failed: {e}")
        return False


async def _send_whatsapp_media(phone: str, body: str, media_url: str) -> bool:
    if not _twilio_ready():
        print("⚠️ Twilio not configured; skipping async media send.")
        return False
    client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    to_number = _format_whatsapp_number(phone)
    from_number = _format_whatsapp_number(TWILIO_WHATSAPP_NUMBER)
    try:
        await run_blocking(
            client.messages.create,
            body=body,
            from_=from_number,
            to=to_number,
            media_url=[media_url],
        )
        return True
    except Exception as e:
        print(f"❌ Twilio media send failed: {e}")
        return False


async def _outbound_worker():
    while True:
        task = await OUTBOUND_QUEUE.get()
        try:
            if task.get("type") == "qa":
                payload = task["payload"]
                phone = task["phone"]
                chat_response = await answer_question_async(payload)
                response_text = localize(
                    phone,
                    f"🤖 {chat_response.answer}\n\nAsk another question, or reply 0 for main menu.",
                    f"🤖 {chat_response.answer}\n\nBuuza ekibuuzo ekirala, oba ddamu ne 0 okudda ku main menu."
                )
                await _send_whatsapp_message(phone, response_text)
            elif task.get("type") == "video_download":
                phone = task["phone"]
                course_name = task.get("course_name", "Course")
                course_id = task.get("course_id")
                token = task.get("token")
                video_urls = task.get("video_urls", [])
                base_url = task.get("base_url") or BASE_URL

                await _send_whatsapp_message(
                    phone,
                    localize(
                        phone,
                        f"⏳ Starting download of {len(video_urls)} video(s) for {course_name}.",
                        f"⏳ Nkka vidiyo {len(video_urls)} ez'essomo {course_name}."
                    ),
                )

                for video in video_urls:
                    video_title = video.get('title', 'Video')
                    video_url = video.get('url', '')
                    if not video_url:
                        continue
                    try:
                        local_path = await run_blocking(
                            download_and_store_video,
                            video_url,
                            course_id,
                            video_title,
                            token,
                        )
                        if local_path and base_url:
                            filename = os.path.basename(local_path)
                            server_url = f"{base_url}/webhook/serve-video/{quote(filename)}"
                            await _send_whatsapp_media(phone, f"🎥 {video_title}", server_url)
                        else:
                            await _send_whatsapp_message(
                                phone,
                                localize(
                                    phone,
                                    f"⚠️ Could not attach {video_title}. Link: {video_url}",
                                    f"⚠️ Sisobode okusibira {video_title}. Link: {video_url}",
                                ),
                            )
                    except Exception as e:
                        print(f"❌ Video download task error: {e}")
                        await _send_whatsapp_message(
                            phone,
                            localize(
                                phone,
                                f"⚠️ Error downloading {video_title}. Link: {video_url}",
                                f"⚠️ Wabaddewo obuzibu mu kka {video_title}. Link: {video_url}",
                            ),
                        )
        except Exception as e:
            print(f"❌ Outbound worker error: {e}")
        finally:
            OUTBOUND_QUEUE.task_done()

def escape_xml(text: str) -> str:
    return (text.replace('&', '&amp;')
               .replace('<', '&lt;')
               .replace('>', '&gt;')
               .replace('"', '&quot;')
               .replace("'", '&apos;'))


def twiml_message(text: str = "") -> Response:
    escaped_text = escape_xml(text or "")
    if escaped_text:
        raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
    else:
        raw_xml = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
    return Response(content=raw_xml, media_type="application/xml")


def get_session_language(phone: str) -> str:
    return user_language.get(phone, "en")


def set_session_language(phone: str, language: str) -> None:
    user_language[phone] = language if language in {"en", "lg"} else "en"


def clear_session_language(phone: str) -> None:
    user_language.pop(phone, None)


def localize(phone: str, english: str, luganda: str) -> str:
    return luganda if get_session_language(phone) == "lg" else english


def language_selection_text(invalid: bool = False, change_mode: bool = False) -> str:
    if invalid:
        intro = (
            "Please reply with 1 for English or 2 for Luganda.\n\n"
            "Ddamu ne 1 ku Lungereza oba 2 ku Luganda.\n\n"
        )
    else:
        intro = ""
    if change_mode:
        intro += (
            "Change language for this session:\n"
            "Kyusa olulimi lwa session eno:\n\n"
        )
    return (
        f"{intro}"
        "Welcome to MoH E-Learning Assistant!\n"
        "Tukwaniriza ku MoH E-Learning Assistant!\n\n"
        "Choose your language for this session:\n"
        "Londa olulimi lw'oyagala okukozesa mu session eno:\n\n"
        "1️⃣ English\n"
        "2️⃣ Luganda"
        + ("\n0️⃣ Main Menu" if change_mode else "")
    )


def goodbye_text(phone: str) -> str:
    return localize(
        phone,
        "👋 Thank you for using MoH E-Learning Assistant!",
        "👋 Webale okukozesa MoH E-Learning Assistant!",
    )


def browse_courses_empty_text(phone: str) -> str:
    error = get_last_course_sync_error()
    if not error:
        return localize(
            phone,
            "📚 *Browse Courses*\n\n"
            "Currently no courses are available.\n\n"
            "0️⃣ Main Menu • #️⃣ Exit",
            "📚 *Laba Amasomo*\n\n"
            "Mu kiseera kino tewali masomo galiwo.\n\n"
            "0️⃣ Main Menu • #️⃣ Mala"
        )

    code = error.get("code")
    if code == "missing_config":
        detail = localize(
            phone,
            "Moodle integration is not configured on the WhatsApp server.",
            "Okukwataganya Moodle tekutebeddwa ku seva ya WhatsApp."
        )
    elif code == "invalid_token":
        detail = localize(
            phone,
            "The configured Moodle token is invalid.",
            "Moodle token etebeddwa si ntuufu."
        )
    elif code == "access_exception":
        detail = localize(
            phone,
            "Moodle denied access to the configured course catalog token.",
            "Moodle egaanye token ekozesebwa okulaba olukalala lw'amasomo."
        )
    else:
        detail = localize(
            phone,
            "The Moodle course catalog could not be loaded right now.",
            "Olukalala lw'amasomo ku Moodle telusobodde kulabika kati."
        )

    return localize(
        phone,
        "📚 *Browse Courses*\n\n"
        f"{detail}\n\n"
        "This is a Moodle integration issue, not that your courses are missing.\n\n"
        "Try option 2 to log in and view your enrolled courses, or contact the administrator.\n\n"
        "0️⃣ Main Menu • #️⃣ Exit",
        "📚 *Laba Amasomo*\n\n"
        f"{detail}\n\n"
        "Kino kizibu kya kukwataganya na Moodle, si kubanga amasomo go tebaliwo.\n\n"
        "Gezaako option 2 okweyingiza olabe amasomo go, oba otuukirire omuddukanya.\n\n"
        "0️⃣ Main Menu • #️⃣ Mala"
    )


def question_mode_empty_text(phone: str) -> str:
    if get_last_course_sync_error():
        return localize(
            phone,
            "🤖 *Document Q&A*\n\n"
            "Course materials could not be loaded from Moodle right now.\n\n"
            "Try again later or contact the administrator.\n\n"
            "0️⃣ Main Menu • #️⃣ Exit",
            "🤖 *Q&A ku Biyigirizibwa*\n\n"
            "Ebikozesebwa by'amasomo tebifunye okuva ku Moodle kati.\n\n"
            "Ddamu oluvannyuma oba otuukirire omuddukanya.\n\n"
            "0️⃣ Main Menu • #️⃣ Mala"
        )

    return localize(
        phone,
        "🤖 *Document Q&A*\n\n"
        "No course materials available yet.\n\n"
        "Please upload documents first, then ask questions about them.\n\n"
        "0️⃣ Main Menu • #️⃣ Exit",
        "🤖 *Q&A ku Biyigirizibwa*\n\n"
        "Tewali bikozesebwa by'amasomo biriwo kati.\n\n"
        "Sooka oteeke ebiwandiiko, oluvannyuma obuuze ebibuuzo ku byo.\n\n"
        "0️⃣ Main Menu • #️⃣ Mala"
    )


def normalize_phone_key(from_value: str) -> str:
    """Normalize sender IDs so session state is stable across provider formats."""
    value = (from_value or "").strip().lower()
    if value.startswith("whatsapp:"):
        value = value.split(":", 1)[1]
    return value


def get_document_file_path(document_id: str):
    """Get the actual file path from document_id - THOROUGH VERSION"""
    # Check cache first
    if document_id in document_path_cache:
        cached_result = document_path_cache[document_id]
        if cached_result[0] and os.path.exists(cached_result[0]):
            return cached_result
    
    try:
        all_docs = document_store.list()
        found_doc = None
        
        # Fast database lookup
        for doc in all_docs:
            doc_id = getattr(doc, 'document_id', None)
            if doc_id == document_id:
                found_doc = doc
                break
        
        if not found_doc:
            document_path_cache[document_id] = (None, None)
            return None, None
        
        filename = getattr(found_doc, 'filename', 'document.pdf')
        
        # THOROUGH: Check ALL possible locations and patterns
        possible_paths = [
            f"storage/uploads/{document_id}_{filename}",
            f"storage/uploads/{filename}",
            f"storage/uploads/{document_id}.pdf",
            f"storage/uploads/{document_id}.PDF",
            getattr(found_doc, 'file_path', None),
            f"uploads/{filename}",
            f"../storage/uploads/{filename}",
            f"storage/chroma/documents/{document_id}_{filename}",
            f"storage/chroma/uploads/{document_id}_{filename}",
            f"storage/chroma/{document_id}_{filename}",
        ]
        
        for path in possible_paths:
            if path and os.path.exists(path) and os.path.isfile(path):
                file_size = os.path.getsize(path)
                if file_size > 100:
                    result = (path, filename)
                    document_path_cache[document_id] = result
                    return result
        
        document_path_cache[document_id] = (None, filename)
        return None, filename
        
    except Exception as e:
        print(f"Error in get_document_file_path: {e}")
        return None, None

def create_pdf_download_response(pdfs, course_name, base_url, phone: str | None = None):
    """Create PDF response - SHOW HEADER MESSAGE FIRST, then PDFs"""
    # Filter to only include PDFs that actually exist
    available_pdfs = []
    
    for pdf in pdfs:
        document_id = pdf.get('document_id')
        if document_id:
            file_path, _ = get_document_file_path(document_id)
            if file_path and os.path.exists(file_path):
                available_pdfs.append(pdf)
    
    if not available_pdfs:
        if phone:
            response_text = localize(
                phone,
                "No PDFs available for this course (files not found).",
                "Tewali PDF ku ssomo lino (fayiro tezirabiddwa)."
            )
        else:
            response_text = "No PDFs available for this course (files not found)."
        escaped_text = escape_xml(response_text)
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
    
    # Build response with HEADER MESSAGE FIRST (like the General course)
    messages_xml = []
    
    # HEADER MESSAGE - This is what you want to show first
    header_text = (
        localize(
            phone,
            f"📚 {course_name} - Available PDFs ({len(available_pdfs)})",
            f"📚 {course_name} - PDF Eziriwo ({len(available_pdfs)})",
        )
        if phone
        else f"📚 {course_name} - Available PDFs ({len(available_pdfs)})"
    )
    header_message = f'''<Message>
        <Body>{escape_xml(header_text)}</Body>
    </Message>'''
    messages_xml.append(header_message)
    
    # NAVIGATION INSTRUCTIONS - Show this right after header
    nav_text = (
        localize(
            phone,
            "💡 Tap any PDF to view it. Use download icon to save.\n\n💡 Navigation:\n0️⃣ Main Menu • 9️⃣ Back to Course • 00️⃣ Exit",
            "💡 Nyiga ku PDF yonna okugilaba. Kozesa akabonero ka download okugikuuma.\n\n💡 Navigation:\n0️⃣ Main Menu • 9️⃣ Ddayo ku Ssomo • 00️⃣ Mala",
        )
        if phone
        else "💡 Tap any PDF to view it. Use download icon to save.\n\n💡 Navigation:\n0️⃣ Main Menu • 9️⃣ Back to Course • 00️⃣ Exit"
    )
    nav_message = f'''<Message>
        <Body>{escape_xml(nav_text)}</Body>
    </Message>'''
    messages_xml.append(nav_message)
    
    # If there's only one PDF, send it directly after the header
    if len(available_pdfs) == 1:
        pdf = available_pdfs[0]
        document_id = pdf.get('document_id')
        
        if document_id:
            file_url = f"{base_url}/webhook/documents/{document_id}/download"
            filename = pdf.get('filename', 'document.pdf')
            
            pdf_message = f'''<Message>
                <Body>📄 {escape_xml(filename)}</Body>
                <Media>{escape_xml(file_url)}</Media>
            </Message>'''
            messages_xml.append(pdf_message)
    
    else:
        # Send each PDF in separate messages after the header
        for i, pdf in enumerate(available_pdfs, 1):
            filename = pdf.get('filename', f'Document {i}')
            document_id = pdf.get('document_id')
            
            if document_id:
                file_url = f"{base_url}/webhook/documents/{document_id}/download"
                pdf_message = f'''<Message>
                    <Body>📄 {escape_xml(filename)}</Body>
                    <Media>{escape_xml(file_url)}</Media>
                </Message>'''
                messages_xml.append(pdf_message)
    
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
{"".join(messages_xml)}
</Response>'''

@router.get("/documents/{document_id}/download")
async def download_document(document_id: str):
    """Download PDF document - OPTIMIZED VERSION"""
    try:
        # Check cache first for instant response
        if document_id in document_path_cache:
            file_path, filename = document_path_cache[document_id]
            if file_path and os.path.exists(file_path):
                return FileResponse(
                    path=file_path,
                    filename=filename,
                    media_type='application/pdf',
                    headers={
                        'Content-Disposition': f'inline; filename="{filename}"',
                        'Cache-Control': 'public, max-age=3600'
                    }
                )
        
        # If not in cache, do quick lookup
        file_path, filename = get_document_file_path(document_id)
        
        if not file_path or not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="PDF not found")
                
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type='application/pdf',
            headers={
                'Content-Disposition': f'inline; filename="{filename}"',
                'Cache-Control': 'public, max-age=3600',
                'X-Accel-Buffering': 'no'
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")

# @app.get("/serve-video/{filename}")
@router.get("/serve-video/{filename}")
def serve_video(filename: str):
    """
    Serve a locally downloaded Moodle video to WhatsApp
    """
    safe_filename = os.path.basename(filename)
    file_path = Path("storage/uploads/videos") / safe_filename
    if not os.path.exists(file_path):
        print(f"❌ Video not found for serving: {file_path}")
        raise HTTPException(status_code=404, detail="Video not found")

    mime_type, _ = mimetypes.guess_type(str(file_path))
    media_type = mime_type or "application/octet-stream"
    file_size = os.path.getsize(file_path)
    print(f"✅ Serving video: {safe_filename} ({file_size} bytes, {media_type})")

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=safe_filename,
        headers={
            "Content-Disposition": "inline",
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*",
        }
    )

def create_smart_video_response(video_urls, course_name, course_id, token, base_url: str = BASE_URL,phone: str | None = None):
    """Download videos and serve them DIRECTLY in WhatsApp messages"""
    if not video_urls:
        if phone:
            response_text = localize(
                phone,
                "No videos available for this course.",
                "Tewali vidiyo ku ssomo lino."
            )
        else:
            response_text = "No videos available for this course."
        escaped_text = escape_xml(response_text)
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
    
    messages_xml = []
    
    # Send header message
    header_text = (
        localize(
            phone,
            f"🎥 {course_name} - Downloading videos...",
            f"🎥 {course_name} - Nkka vidiyo...",
        )
        if phone
        else f"🎥 {course_name} - Downloading videos..."
    )
    header_message = f'''<Message>
        <Body>{escape_xml(header_text)}</Body>
    </Message>'''
    messages_xml.append(header_message)
    
    # Process each video
    downloaded_videos = []
    
    for video in video_urls:
        video_title = video.get('title', 'Video')
        video_url = video.get('url', '')
        
        if video_url:
            try:
                # Download the video to our server
                local_path = download_and_store_video(video_url, course_id, video_title, token)
                
                if local_path:
                    # Get the filename for our server URL
                    filename = os.path.basename(local_path)
                    server_url = f"{base_url}/webhook/serve-video/{quote(filename)}"
                    
                    downloaded_videos.append({
                        'title': video_title,
                        'server_url': server_url,
                        'local_path': local_path
                    })
                    
                else:
                    print(f"Failed to download: {video_title}")
                    
            except Exception as e:
                print(f"Error with {video_title}: {e}")
                import traceback
                traceback.print_exc()
    
    if not downloaded_videos:
        # Fall back to plain direct links when media download/attach is blocked.
        return create_video_links_response(
            video_urls,
            course_name,
            note="Could not download videos to WhatsApp right now. Sharing direct links instead."
            if not phone
            else localize(
                phone,
                "Could not download videos to WhatsApp right now. Sharing direct links instead.",
                "Sisobodde kka vidiyo ku WhatsApp kati. Nsindika enkolagana ezitereevu mu kifo kyazo."
            ),
            phone=phone,
        )
    
    # Now send the videos to WhatsApp
    videos_header_text = (
        localize(
            phone,
            f"🎥 {course_name} - Available Videos ({len(downloaded_videos)})",
            f"🎥 {course_name} - Vidiyo Eziriwo ({len(downloaded_videos)})",
        )
        if phone
        else f"🎥 {course_name} - Available Videos ({len(downloaded_videos)})"
    )
    videos_header = f'''<Message>
        <Body>{escape_xml(videos_header_text)}</Body>
    </Message>'''
    messages_xml.append(videos_header)
    
    nav_text = (
        localize(
            phone,
            "💡 Each video will appear below. Tap to play directly in WhatsApp!\n\n💡 Navigation:\n0️⃣ Main Menu • 9️⃣ Back to Course • 00️⃣ Exit",
            "💡 Buli vidiyo ejja kulabika wansi. Nyiga okugizannya butereevu mu WhatsApp!\n\n💡 Navigation:\n0️⃣ Main Menu • 9️⃣ Ddayo ku Ssomo • 00️⃣ Mala",
        )
        if phone
        else "💡 Each video will appear below. Tap to play directly in WhatsApp!\n\n💡 Navigation:\n0️⃣ Main Menu • 9️⃣ Back to Course • 00️⃣ Exit"
    )
    nav_message = f'''<Message>
        <Body>{escape_xml(nav_text)}</Body>
    </Message>'''
    messages_xml.append(nav_message)
    
    # Send each video as embedded media
    for video in downloaded_videos:
        video_title = video['title']
        video_url = video['server_url']
        
        message_xml = f"""
        <Message>
            <Body>🎥 {escape_xml(video_title)}</Body>
            <Media>{escape_xml(video_url)}</Media>
        </Message>
        """
        messages_xml.append(message_xml)
    
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
{"".join(messages_xml)}
</Response>'''


def create_video_links_response(videos, course_name, note: str = "", phone: str | None = None):
    """Return direct video URLs as text messages (works even when media delivery fails)."""
    if not videos:
        if phone:
            response_text = localize(
                phone,
                "No videos available for this course.",
                "Tewali vidiyo ku ssomo lino."
            )
        else:
            response_text = "No videos available for this course."
        escaped_text = escape_xml(response_text)
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'

    messages_xml = []

    header_text = (
        localize(
            phone,
            f"🔗 {course_name} - Video Links",
            f"🔗 {course_name} - Enkolagana za Vidiyo",
        )
        if phone
        else f"🔗 {course_name} - Video Links"
    )
    if note:
        header_text = f"{header_text}\n\n⚠️ {note}"
    messages_xml.append(
        f'''<Message>
        <Body>{escape_xml(header_text)}</Body>
    </Message>'''
    )

    sent = 0
    for i, video in enumerate(videos, start=1):
        video_url = (video or {}).get("url", "")
        if not video_url:
            continue
        video_title = (video or {}).get("title", "Video")
        body = f"🎥 {i}. {video_title}\n{video_url}"
        messages_xml.append(
            f'''<Message>
            <Body>{escape_xml(body)}</Body>
        </Message>'''
        )
        sent += 1
        if sent >= 5:
            break

    total_with_urls = sum(1 for item in videos if (item or {}).get("url"))
    if total_with_urls > sent:
        remaining = total_with_urls - sent
        remaining_text = (
            localize(phone, f"... and {remaining} more video link(s).", f"... era waliwo enkolagana za vidiyo endala {remaining}.")
            if phone
            else f"... and {remaining} more video link(s)."
        )
        messages_xml.append(
            f'''<Message>
            <Body>{escape_xml(remaining_text)}</Body>
        </Message>'''
        )

    open_link_text = (
        localize(
            phone,
            "💡 Open any link in your browser.\n\nNavigation:\n9️⃣ Back • 0️⃣ Main Menu",
            "💡 Ggulawo enkolagana yonna mu browser yo.\n\nNavigation:\n9️⃣ Ddayo • 0️⃣ Main Menu",
        )
        if phone
        else "💡 Open any link in your browser.\n\nNavigation:\n9️⃣ Back • 0️⃣ Main Menu"
    )
    messages_xml.append(
        f'''<Message>
        <Body>{escape_xml(open_link_text)}</Body>
    </Message>'''
    )

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
{"".join(messages_xml)}
</Response>'''

import hashlib


def download_and_store_video(moodle_url, course_id, video_title, token):
    """
    Download Moodle video - USING THE WORKING APPROACH FROM test_sample.py
    """
    try:
        max_video_bytes = int(os.getenv("WHATSAPP_MAX_VIDEO_BYTES", str(15 * 1024 * 1024)))
        parsed = urlparse(moodle_url)
        normalized_path = parsed.path or ""
        if "/webservice/pluginfile.php/" not in normalized_path and "/pluginfile.php/" in normalized_path:
            normalized_path = normalized_path.replace("/pluginfile.php/", "/webservice/pluginfile.php/", 1)
            moodle_url = parsed._replace(path=normalized_path).geturl()
            parsed = urlparse(moodle_url)

        # Try the logged-in user's token first, then fallback token if available.
        fallback_token = os.getenv("MOODLE_TOKEN")
        token_candidates = []
        if token:
            token_candidates.append(token)
        if fallback_token and fallback_token not in token_candidates:
            token_candidates.append(fallback_token)
        if not token_candidates:
            token_candidates.append(None)

        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'video/mp4,video/*;q=0.9,*/*;q=0.8',
            'Referer': 'https://elearning.cadh.africa/',
        }

        videos_dir = Path("storage/uploads/videos")
        videos_dir.mkdir(parents=True, exist_ok=True)
        safe_title = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in video_title)
        source_ext = Path(parsed.path or "").suffix.lower()
        if source_ext not in {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv", ".flv", ".3gp"}:
            source_ext = ".mp4"
        filename = f"course_{course_id}_{safe_title}{source_ext}"
        local_path = videos_dir / filename

        for token_candidate in token_candidates:
            query_params = parse_qs(parsed.query)
            if token_candidate:
                query_params['token'] = [token_candidate]
            query_params['forcedownload'] = ['1']
            download_url = parsed._replace(query=urlencode(query_params, doseq=True)).geturl()

            try:
                head_response = requests.head(
                    download_url,
                    headers=headers,
                    verify=False,
                    timeout=10,
                    allow_redirects=True
                )
                if head_response.status_code >= 400:
                    print(f"HEAD check failed ({head_response.status_code}), trying GET anyway...")
                content_length = int(head_response.headers.get("content-length") or 0)
                if content_length and content_length > max_video_bytes:
                    print(f"Video too large for WhatsApp ({content_length} bytes), skipping")
                    continue
            except requests.RequestException as head_error:
                print(f"HEAD check error ({head_error}), trying GET anyway...")

            print("\nDownloading...")
            get_response = requests.get(download_url, headers=headers, stream=True, timeout=60, verify=False)
            print("download response",get_response)
            if get_response.status_code != 200:
                print(f"Video download failed (GET {get_response.status_code})")
                continue

            content_type = get_response.headers.get("content-type", "").lower()
            if "video" not in content_type and "octet-stream" not in content_type:
                sample = next(get_response.iter_content(200), b"")
                print(f"📄 Non-video response: {sample[:120]}")
                continue

            downloaded = 0
            with open(local_path, "wb") as f:
                for chunk in get_response.iter_content(8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if downloaded > max_video_bytes:
                            print(f"Downloaded file exceeded WhatsApp limit ({downloaded} bytes), skipping")
                            break

            if downloaded < 1000:
                print("File too small")
                local_path.unlink(missing_ok=True)
                continue
            if downloaded > max_video_bytes:
                local_path.unlink(missing_ok=True)
                continue

            return str(local_path)

        return None

    except Exception as e:
        print(f"Video download error: {e}")
        import traceback
        traceback.print_exc()
        return None
    

# ====== NEW: MINIMAL MOODLE INTEGRATION ======

def create_moodle_pdf_response(pdfs, course_name, phone: str | None = None):
    """Create response for Moodle PDFs"""
    if not pdfs:
        response_text = (
            localize(phone, f"No PDFs available for {course_name}", f"Tewali PDF eziriwo ku {course_name}")
            if phone
            else f"No PDFs available for {course_name}"
        )
        escaped_text = escape_xml(response_text)
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
    
    messages_xml = []
    
    header_text = (
        localize(
            phone,
            f"📚 {course_name} - PDFs ({len(pdfs)})",
            f"📚 {course_name} - PDF ({len(pdfs)})",
        )
        if phone
        else f"📚 {course_name} - PDFs ({len(pdfs)})"
    )
    header = f'''<Message>
        <Body>{escape_xml(header_text)}</Body>
    </Message>'''
    messages_xml.append(header)
    
    for pdf in pdfs[:5]:  # Limit to 5 PDFs
        pdf_message = f'''<Message>
            <Body>📄 {escape_xml(pdf['title'])}</Body>
            <Media>{escape_xml(pdf['url'])}</Media>
        </Message>'''
        messages_xml.append(pdf_message)
    
    if len(pdfs) > 5:
        remaining = f'''<Message>
            <Body>{escape_xml(localize(phone, f"... and {len(pdfs) - 5} more PDFs", f"... era waliwo PDF endala {len(pdfs) - 5}") if phone else f"... and {len(pdfs) - 5} more PDFs")}</Body>
        </Message>'''
        messages_xml.append(remaining)
    
    nav_text = (
        localize(
            phone,
            "💡 Tap any PDF to view it in WhatsApp.\n\nNavigation:\n9️⃣ Back • 0️⃣ Main Menu",
            "💡 Nyiga ku PDF yonna okugiraba mu WhatsApp.\n\nNavigation:\n9️⃣ Ddayo • 0️⃣ Main Menu",
        )
        if phone
        else "💡 Tap any PDF to view it in WhatsApp.\n\nNavigation:\n9️⃣ Back • 0️⃣ Main Menu"
    )
    nav_message = f'''<Message>
        <Body>{escape_xml(nav_text)}</Body>
    </Message>'''
    messages_xml.append(nav_message)
    
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
{"".join(messages_xml)}
</Response>'''

# Email configuration
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USER)

async def _send_email(to_email: str, subject: str, body: str) -> bool:
    """Send email as fallback when teacher doesn't have WhatsApp"""
    if not SMTP_USER or not SMTP_PASSWORD:
        print("⚠️ Email not configured. Set SMTP_USER and SMTP_PASSWORD in .env")
        return False
    
    try:
        def send_email_sync():
            msg = MIMEMultipart()
            msg['From'] = SMTP_FROM_EMAIL
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        
        await run_blocking(send_email_sync)
        print(f"✅ Email sent to {to_email}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return False
    
async def handle_moodle_login_flow(phone, raw_msg):
    state = user_state.get(phone)

    # ===== USERNAME STEP =====
    if state == "moodle_username":
        user_moodle_data.setdefault(phone, {})
        user_moodle_data[phone]["username"] = raw_msg.strip()
        user_state[phone] = "moodle_password"

        response_text = localize(
            phone,
            "🔐 *Moodle Login*\n\n"
            "Please enter your Moodle password:",
            "🔐 *Okweyingiza ku Moodle*\n\n"
            "Wandiika akasumuluzo ko aka Moodle:"
        )
        escaped_text = escape_xml(response_text)
        raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
        return Response(content=raw_xml, media_type="application/xml")

    # ===== PASSWORD STEP =====
    if state == "moodle_password":
        username = user_moodle_data.get(phone, {}).get("username")
        if not username:
            user_state[phone] = "moodle_username"
            response_text = localize(
                phone,
                "🔐 *Login Required*\n\n"
                "Please enter your Moodle username:",
                "🔐 *Okweyingiza Kwetaagisa*\n\n"
                "Wandiika erinnya lyo ery'okweyingiza ku Moodle:"
            )
            escaped_text = escape_xml(response_text)
            raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
            return Response(content=raw_xml, media_type="application/xml")
        password = raw_msg  # RAW, NOT lowercased

        auth_result = await authenticate_moodle_user_async(username, password)

        if not auth_result:
            user_state[phone] = "moodle_username"
            response_text = localize(
                phone,
                "*Login failed*\n\n"
                "Invalid username or password.\n"
                "Please enter your Moodle username again:",
                "*Okweyingiza kulemye*\n\n"
                "Erinnya oba akasumuluzo si kituufu.\n"
                "Wandiika nate erinnya lyo ery'okweyingiza ku Moodle:"
            )
            escaped_text = escape_xml(response_text)
            raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
            return Response(content=raw_xml, media_type="application/xml")

        # ✅ SUCCESS PATH
        user_moodle_data[phone].update(auth_result)
        intent = user_moodle_data[phone].get('original_intent')

        if intent:
            if intent.get('action') == 'view_enrolled_courses':
                # User wanted to view their enrolled courses
                # Clear intent
                user_moodle_data[phone].pop('original_intent', None)
                
                # Get enrolled courses
                token = auth_result['token']
                userid = auth_result['userid']
                enrolled_courses = await get_user_enrolled_courses_moodle_async(token, userid)
                user_moodle_data[phone]['enrolled_courses'] = enrolled_courses
                
                if not enrolled_courses:
                    response_text = localize(
                        phone,
                        "🎓 *Your Enrolled Courses*\n\n"
                        "You are not enrolled in any courses yet.\n\n"
                        "💡 Browse courses (option 1) to enroll in new courses.\n\n"
                        "0️⃣ Main Menu • #️⃣ Exit",
                        "🎓 *Amasomo Go Ge Nnegattako*\n\n"
                        "Tonnawegatta ku ssomo lyonna okutuuka kati.\n\n"
                        "💡 Kozesa option 1 okulaba amasomo n'okweegatta ku mapya.\n\n"
                        "0️⃣ Main Menu • #️⃣ Mala"
                    )
                else:
                    course_list = "\n".join([f"{i+1}. {course['name']}" for i, course in enumerate(enrolled_courses)])
                    response_text = localize(
                        phone,
                        "🎓 *Your Enrolled Courses*\n\n"
                        f"{course_list}\n\n"
                        "0️⃣ Main Menu • #️⃣ Exit\n\n"
                        "Select a course number to access:",
                        "🎓 *Amasomo Go Ge Nnegattako*\n\n"
                        f"{course_list}\n\n"
                        "0️⃣ Main Menu • #️⃣ Mala\n\n"
                        "Londa namba y'essomo okulyingiramu:"
                    )
                user_state[phone] = "my_courses"
                
                escaped_text = escape_xml(response_text)
                raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
                return Response(content=raw_xml, media_type="application/xml")
            
            # ===== TAKE QUIZ INTENT =====
            elif intent.get('action') == 'take_quiz':
                # User wanted to take a quiz
                # Clear intent
                user_moodle_data[phone].pop('original_intent', None)
                
                # Get enrolled courses
                token = auth_result['token']
                userid = auth_result['userid']
                enrolled_courses = await get_user_enrolled_courses_moodle_async(token, userid)
                user_moodle_data[phone]['enrolled_courses'] = enrolled_courses
                
                if not enrolled_courses:
                    response_text = (
                        "📝 *Take a Quiz*\n\n"
                        "You are not enrolled in any courses yet.\n\n"
                        "💡 Browse courses (option 1) to enroll in new courses.\n\n"
                        "0️⃣ Main Menu • #️⃣ Exit"
                    )
                    user_state[phone] = "main_menu"
                else:
                    course_list = "\n".join([f"{i+1}. {course['name']}" for i, course in enumerate(enrolled_courses)])
                    response_text = (
                        "📝 *Select a Course for Quiz*\n\n"
                        f"{course_list}\n\n"
                        "0️⃣ Main Menu • #️⃣ Exit\n\n"
                        "Select a course number to view its quizzes:"
                    )
                    user_state[phone] = "quiz_course_selection"
                
                escaped_text = escape_xml(response_text)
                raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
                return Response(content=raw_xml, media_type="application/xml")
            
            elif intent.get('action') == 'check_enrollment':
                # User wanted to check enrollment for a course they browsed
                course_id = intent['course_id']
                
                # Get course details
                courses = await get_available_courses_async()
                course_data = courses.get(str(course_id), {})
                
                if not course_data:
                    response_text = localize(phone, "Course not found.", "Essomo terirabiddwa.")
                    escaped_text = escape_xml(response_text)
                    raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
                    return Response(content=raw_xml, media_type="application/xml")
                
                # Check enrollment
                token = auth_result['token']
                userid = auth_result['userid']
                is_enrolled = await is_user_enrolled_in_course_async(token, userid, course_id)
                
                # Clear intent
                user_moodle_data[phone].pop('original_intent', None)
                
                if is_enrolled:
                    user_state[phone] = f"enrolled_{course_id}"
                    # Get fresh resources with user's token
                    token = user_moodle_data[phone]['token']
                    contents = await get_course_contents_moodle_async(token, int(course_id))
                    resources = await run_blocking(extract_moodle_resources, contents, token)
                    
                    # FIXED: Correct the print statements
                    print("\n" + "="*50)
                    print("RESOURCES FOUND:")
                    print(f"Resources keys: {resources.keys()}")
                    print(f"Presentations count: {len(resources.get('presentations', []))}")
                    if resources.get('presentations'):
                        print("Presentations:")
                        for ppt in resources['presentations']:
                            print(f"  - {ppt.get('title')} ({ppt.get('filename')})")
                    print("="*50 + "\n")
                    
                    # Show dynamic overview
                    overview = create_course_overview(resources, course_data['name'], len(course_data.get('quizzes', [])))
                    print("OVERVIEW MENU:")
                    print(overview)
                    print("="*50)
                    
                    response_text = overview
                    return twiml_message(overview)
                else:
                    # User NOT enrolled - show enroll option
                    user_state[phone] = f"browsing_{course_id}"
                    response_text = localize(
                        phone,
                        f"📚 *{course_data['name']}*\n\n"
                        f"📊 *Course Overview:*\n"
                        f"• {len(course_data.get('pdfs', []))} PDF Documents\n"
                        f"• {len(course_data.get('videos', []))} Video Resources\n\n"
                        f"• {len(course_data.get('quizzes', []))} quizzes\n\n"
                        "🔒 *You are NOT enrolled in this course*\n\n"
                        "1️⃣ Enroll in this Course\n\n"
                        "💡 *Navigation:*\n"
                        "0️⃣ Main Menu • 9️⃣ Back to Browse • #️⃣ Exit",
                        f"📚 *{course_data['name']}*\n\n"
                        f"📊 *Okulaba Essomo mu Bufunze:*\n"
                        f"• {len(course_data.get('pdfs', []))} PDF Documents\n"
                        f"• {len(course_data.get('videos', []))} Video Resources\n\n"
                        "🔒 *Tonnawegatta ku ssomo lino*\n\n"
                        "1️⃣ Weegatte ku Ssomo lino\n\n"
                        "💡 *Navigation:*\n"
                        "0️⃣ Main Menu • 9️⃣ Ddayo ku Kulaba Amasomo • #️⃣ Mala"
                    )
                
                escaped_text = escape_xml(response_text)
                raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
                return Response(content=raw_xml, media_type="application/xml")
            
            elif intent.get('action') == 'enroll':
                # Handle enrollment
                course_id = intent['course_id']
                course_name = intent['course_name']

                enrolled = await enroll_user_in_course_async(
                    token=auth_result['token'],
                    userid=auth_result['userid'],
                    courseid=course_id,
                )

                if enrolled:
                    # refresh enrolled courses
                    token = auth_result['token']
                    userid = auth_result['userid']
                    user_moodle_data[phone]['enrolled_courses'] = await get_user_enrolled_courses_moodle_async(
                        token,
                        userid,
                    )

                    # clear intent
                    user_moodle_data[phone].pop('original_intent', None)

                    # Set state to enrolled course
                    user_state[phone] = f"enrolled_{course_id}"
                    
                    # Get course data to show content
                    # courses = get_available_courses()
                    # course_data = courses.get(str(course_id), {})
                    user_state[phone] = f"enrolled_{course_id}"
                    # Get fresh resources with user's token
                    token = user_moodle_data[phone]['token']
                    contents = await get_course_contents_moodle_async(token, int(course_id))
                    resources = await run_blocking(extract_moodle_resources, contents, token)
                    
                    # FIXED: Correct the print statements
                    print("\n" + "="*50)
                    print("RESOURCES FOUND:")
                    print(f"Resources keys: {resources.keys()}")
                    print(f"Presentations count: {len(resources.get('presentations', []))}")
                    if resources.get('presentations'):
                        print("Presentations:")
                        for ppt in resources['presentations']:
                            print(f"  - {ppt.get('title')} ({ppt.get('filename')})")
                    print("="*50 + "\n")
                    
                    # Show dynamic overview
                    overview = create_course_overview(resources, course_data['name'], len(course_data.get('quizzes', [])))
                    print("OVERVIEW MENU:")
                    print(overview)
                    print("="*50)
                    
                    response_text = overview
                    return twiml_message(overview)

                else:
                    response_text = localize(
                        phone,
                        "Enrollment failed. Please try again.",
                        "Okweyunga kulemye. Gezaako nate."
                    )
                    escaped_text = escape_xml(response_text)
                    raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
                    return Response(content=raw_xml, media_type="application/xml")
                
            # Add this to the intent handling section
            elif intent.get('action') == 'ask_trainer':
                # User wanted to ask a trainer after login
                user_moodle_data[phone].pop('original_intent', None)
                
                # Get user's ENROLLED courses
                token = auth_result['token']
                userid = auth_result['userid']
                enrolled_courses = await get_user_enrolled_courses_moodle_async(token, userid)
                
                if not enrolled_courses:
                    response_text = localize(
                        phone,
                        "📚 *No Enrolled Courses*\n\n"
                        "You are not enrolled in any courses yet.\n\n"
                        "Please enroll in courses first (Option 1 from main menu).\n\n"
                        "0️⃣ Main Menu",
                        "📚 *Tewali Masomo Gewegattako*\n\n"
                        "Tonnawegatta ku masomo gonna.\n\n"
                        "Sooka weegatte ku masomo (Option 1 okuva ku main menu).\n\n"
                        "0️⃣ Main Menu"
                    )
                    user_state[phone] = "main_menu"
                else:
                    # Store enrolled courses and go to course selection
                    user_moodle_data[phone]['enrolled_courses'] = enrolled_courses
                    user_state[phone] = "trainer_course_selection"
                    
                    course_list = "\n".join([f"{i+1}. {course['name']}" for i, course in enumerate(enrolled_courses)])
                    response_text = localize(
                        phone,
                        f"👨‍🏫 *Ask a Trainer*\n\n"
                        f"📋 *Instructions:*\n"
                        f"• Select a course you're enrolled in from the list below\n"
                        f"• Type your question about that course\n"
                        f"• Your question will be sent directly to the course teacher(s)\n"
                        f"• Teachers will reply to you via WhatsApp\n\n"
                        f"📚 *Your Enrolled Courses:*\n"
                        f"{course_list}\n\n"
                        f"Enter the course number:\n\n"
                        f"0️⃣ Main Menu • #️⃣ Exit",
                        f"👨‍🏫 *Buuza Omusomesa*\n\n"
                        f"📋 *Ebigendererwa:*\n"
                        f"• Londa essomo lino okuva mu lukalala wammanga\n"
                        f"• Wandiika ekibuuzo kyo ku essomo eryo\n"
                        f"• Ekibuuzo kyo kijja kusindikibwa eri omusomesa w'essomo\n"
                        f"• Abasomesa bajja kukuddamu okuyita mu WhatsApp\n\n"
                        f"📚 *Amasomo Go Gewegattako:*\n"
                        f"{course_list}\n\n"
                        f"Wandiika namba y'essomo:\n\n"
                        f"0️⃣ Main Menu • #️⃣ Mala"
                    )
                
                escaped_text = escape_xml(response_text)
                raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
                return Response(content=raw_xml, media_type="application/xml")
        
        # If no intent or intent not handled, go to main menu
        user_state[phone] = "main_menu"
        response_text = localize(
            phone,
            f"✅ *Login Successful!*\n\n"
            f"Welcome, *{auth_result['fullname']}* 🎉\n\n"
            "You can now continue enrolling in courses.\n\n"
            "Reply with:\n"
            "1️⃣ Browse Courses\n"
            "2️⃣ My Enrolled Courses\n"
            "0️⃣ Main Menu",
            f"✅ *Okweyingiza Kuyise Bulungi!*\n\n"
            f"Tukwaniriza, *{auth_result['fullname']}* 🎉\n\n"
            "Kati osobola okugenda mu maaso n'okweegatta ku masomo.\n\n"
            "Ddamu nga okozesa:\n"
            "1️⃣ Laba Amasomo\n"
            "2️⃣ Amasomo Gange Ge Nnegattako\n"
            "0️⃣ Main Menu"
        )
        
        escaped_text = escape_xml(response_text)
        raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
        return Response(content=raw_xml, media_type="application/xml")

    # ===== SAFETY NET =====
    return None

async def is_enrolled_live(phone, course_id):
    if phone not in user_moodle_data:
        return False

    token = user_moodle_data[phone].get('token')
    userid = user_moodle_data[phone].get('userid')

    if not token or not userid:
        return False

    return await is_user_enrolled_in_course_async(token, userid, int(course_id))

def main_menu_text(phone: str, first_time: bool = False):
    if first_time:
        return localize(
            phone,
            "👋 Hello! Welcome to MoH E-Learning Assistant!\n\n"
            "📚 *Select Option to continue:*\n"
            "1️⃣ Browse Courses\n"
            "2️⃣ My Enrolled Courses\n"
            "3️⃣ Take a Quiz\n"
            "4️⃣ View Quiz Results\n"
            "5️⃣ Ask Trainer for Help\n"
            "6️⃣ Ask Question Q&A\n"
            "7️⃣ Change Language\n\n"
            "0️⃣ Main Menu • #️⃣ Exit",
            "👋 Ki bulungi! Tukwaniriza ku MoH E-Learning Assistant!\n\n"
            "📚 *Ebikolebwa Eriwo:*\n"
            "1️⃣ Laba Amasomo\n"
            "2️⃣ Amasomo Gange Ge Nnegattako\n"
            "3️⃣ Kola Ekigezo\n"
            "4️⃣ Laba Ebivudde mu Kigezo\n"
            "5️⃣ Saba Omusomesa Obuyambi\n"
            "6️⃣ Buuza Ekibuuzo\n"
            "7️⃣ Kyusa Olulimi\n\n"
            "0️⃣ Main Menu • #️⃣ Mala"
        )

    return localize(
        phone,
        "👋 Welcome back to MoH E-Learning Assistant!\n\n"
        "📚 *Select Option to continue:*\n"
        "1️⃣ Browse Courses\n"
        "2️⃣ My Enrolled Courses\n"
        "3️⃣ Take a Quiz\n"
        "4️⃣ View Quiz Results\n"
        "5️⃣ Ask Trainer for Help\n"
        "6️⃣ Ask Question Q&A\n"
        "7️⃣ Change Language\n\n"
        "0️⃣ Main Menu • #️⃣ Exit",
        "👋 Tukwaniriza nate ku MoH E-Learning Assistant!\n\n"
        "📚 *Ebikolebwa Eriwo:*\n"
        "1️⃣ Laba Amasomo\n"
        "2️⃣ Amasomo Gange Ge Nnegattako\n"
        "3️⃣ Kola Ekigezo\n"
        "4️⃣ Laba Ebivudde mu Kigezo\n"
        "5️⃣ Saba Omusomesa Obuyambi\n"
        "6️⃣ Buuza Ekibuuzo\n"
        "7️⃣ Kyusa Olulimi\n\n"
        "0️⃣ Main Menu • #️⃣ Mala"
    )


def create_quiz_response(course_data, base_url: str = BASE_URL):
    """Create response showing all quizzes with clickable links for each module"""
    
    # Get quizzes from the course data
    quizzes_by_module = {}
    module_order = []
    
    # Organize quizzes by section/module
    if 'sections' in course_data:
        for section in course_data['sections']:
            section_name = section.get('name', 'Unknown Module')
            if 'quizzes' in section and section['quizzes']:
                if section_name not in quizzes_by_module:
                    quizzes_by_module[section_name] = []
                    module_order.append(section_name)
                quizzes_by_module[section_name].extend(section['quizzes'])
    
    # Count total quizzes
    total_quizzes = sum(len(quizzes) for quizzes in quizzes_by_module.values())
    
    if total_quizzes == 0:
        response_text = f"📝 *{course_data['name']} - Quizzes*\n\n❌ No quizzes available for this course yet.\n\n💡 *Navigation:*\n0️⃣ Main Menu • 9️⃣ Back to Course • #️⃣ Exit"
        escaped_text = escape_xml(response_text)
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
    
    # Build ONE comprehensive message with everything in the correct order
    full_message = f"📝 *{course_data['name']} - Available Quizzes* ({total_quizzes} total)\n\n"
    full_message += "💡 Tap any quiz link below to open it in your browser and start the assessment.\n\n"
    
    # Add each module and its quizzes
    for module_name in module_order:
        quizzes = quizzes_by_module[module_name]
        if quizzes:
            full_message += f"📌 *{module_name}*\n\n"
            
            for i, quiz in enumerate(quizzes, 1):
                quiz_title = quiz.get('title', f'Quiz {i}')
                quiz_url = quiz.get('url', '')
                full_message += f"{i}. {quiz_title}\n🔗 {quiz_url}\n\n"
    
    # Add navigation at the end
    full_message += "💡 *Navigation:*\n0️⃣ Main Menu • 9️⃣ Back to Course • #️⃣ Exit"
    
    # Send as ONE single message
    escaped_text = escape_xml(full_message)
    raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
    return raw_xml


@router.post("/")  
async def whatsapp_reply(Body: str = Form(default=""), From: str = Form(default="")):
    raw_msg = (Body or "").strip()
    user_msg = raw_msg.lower()
    phone = normalize_phone_key(From or "")
    base_url = BASE_URL
    courses_cache_local = None

    async def get_courses(force_refresh: bool = False):
        nonlocal courses_cache_local
        if force_refresh or courses_cache_local is None:
            courses_cache_local = await get_available_courses_async(force_refresh=force_refresh)
        return courses_cache_local

    # Twilio status callbacks may hit this webhook without message content.
    if not phone or not raw_msg:
        return twiml_message()

    # ====== FIRST CONTACT ======
    if phone not in user_state:
        user_state[phone] = "language_selection"
        return twiml_message(language_selection_text())

    # ====== LANGUAGE SELECTION ======
    if user_state.get(phone) in {"language_selection", "language_selection_menu"}:
        change_mode = user_state.get(phone) == "language_selection_menu"
        first_time = not change_mode
        if user_msg in {"1", "english", "en"}:
            set_session_language(phone, "en")
            user_state[phone] = "main_menu"
            if change_mode:
                return twiml_message(
                    localize(
                        phone,
                        "✅ Language changed to English.\n\n",
                        "✅ Olulimi lukyusiddwa ne lufuuka Lungereza.\n\n"
                    ) + main_menu_text(phone)
                )
            return twiml_message(main_menu_text(phone, first_time=first_time))
        if user_msg in {"2", "luganda", "lg"}:
            set_session_language(phone, "lg")
            user_state[phone] = "main_menu"
            if change_mode:
                return twiml_message(
                    localize(
                        phone,
                        "✅ Language changed to Luganda.\n\n",
                        "✅ Olulimi lukyusiddwa ne lufuuka Luganda.\n\n"
                    ) + main_menu_text(phone)
                )
            return twiml_message(main_menu_text(phone, first_time=first_time))
        if change_mode and user_msg in {"0", "menu", "main menu"}:
            user_state[phone] = "main_menu"
            return twiml_message(main_menu_text(phone))
        if user_msg in {"#", "exit", "quit"}:
            user_state.pop(phone, None)
            clear_session_language(phone)
            return twiml_message(goodbye_text(phone))
        return twiml_message(language_selection_text(invalid=True, change_mode=change_mode))

    # ====== CHECK FOR MOODLE LOGIN FLOW FIRST ======
    if user_state.get(phone, "") in ["moodle_username", "moodle_password"]:
        login_response = await handle_moodle_login_flow(phone, raw_msg)
        if login_response:
            return login_response 

    # ====== MANUAL CACHE REFRESH ======
    if user_msg in ["refresh", "reload", "sync"]:
        try:
            clear_courses_cache()
            fresh_courses = await get_courses(force_refresh=True)
            if fresh_courses:
                response_text = localize(
                    phone,
                    f"🔄 Course list refreshed.\n\nFound {len(fresh_courses)} course(s) from Moodle.\n\nReply 1 to browse courses.",
                    f"🔄 Olukalala lw'amasomo luzziddwa buggya.\n\nTulabye amasomo {len(fresh_courses)} okuva ku Moodle.\n\nDdamu ne 1 okulaba amasomo."
                )
            else:
                response_text = browse_courses_empty_text(phone)
        except Exception:
            response_text = localize(
                phone,
                "⚠️ Refresh failed. Please try again in a few seconds.",
                "⚠️ Okuzza obuggya kulemye. Gezaako nate mu kaseera katono."
            )

        return twiml_message(response_text)
    
    # ====== MAIN MENU ======
    if user_state[phone] == "main_menu":
        if user_msg in ["1", "browse"]:
            user_state[phone] = "browse_courses"
            courses = await get_courses(force_refresh=False)
            course_ids = list(courses.keys())

            if not courses:
                response_text = browse_courses_empty_text(phone)
            else:
                course_list = "\n".join([f"{i+1}. {course['name']}" for i, course in enumerate(courses.values())])
                response_text = localize(
                    phone,
                    "📚 *Browse Available Courses*\n\n"
                    f"{course_list}\n\n"
                    "0️⃣ Main Menu • #️⃣ Exit\n\n"
                    "Select a course number to view details:",
                    "📚 *Laba Amasomo Agaliwo*\n\n"
                    f"{course_list}\n\n"
                    "0️⃣ Main Menu • #️⃣ Mala\n\n"
                    "Londa namba y'essomo okulaba ebisingawo:"
                )
                
        elif user_msg in ["2", "enrolled"]:
            # Check if user is logged into Moodle
            if phone in user_moodle_data and 'token' in user_moodle_data[phone]:
                # User is logged in - show their enrolled courses
                token = user_moodle_data[phone]['token']
                userid = user_moodle_data[phone]['userid']
                
                enrolled_courses = await get_user_enrolled_courses_moodle_async(token, userid)
                
                if not enrolled_courses:
                    response_text = localize(
                        phone,
                        "🎓 *Your Enrolled Courses*\n\n"
                        "You are not enrolled in any courses yet.\n\n"
                        "💡 Browse courses (option 1) to enroll in new courses.\n\n"
                        "0️⃣ Main Menu • #️⃣ Exit",
                        "🎓 *Amasomo Go Ge Nnegattako*\n\n"
                        "Tonnawegatta ku ssomo lyonna okutuuka kati.\n\n"
                        "💡 Kozesa option 1 okulaba amasomo n'okweegatta ku mapya.\n\n"
                        "0️⃣ Main Menu • #️⃣ Mala"
                    )
                else:
                    course_list = "\n".join([f"{i+1}. {course['name']}" for i, course in enumerate(enrolled_courses)])
                    response_text = localize(
                        phone,
                        "🎓 *Your Enrolled Courses*\n\n"
                        f"{course_list}\n\n"
                        "0️⃣ Main Menu • #️⃣ Exit\n\n"
                        "Select a course number to access:",
                        "🎓 *Amasomo Go Ge Nnegattako*\n\n"
                        f"{course_list}\n\n"
                        "0️⃣ Main Menu • #️⃣ Mala\n\n"
                        "Londa namba y'essomo okulyingiramu:"
                    )
                user_state[phone] = "my_courses"
            else:
                # User not logged in - prompt for login
                # 🎯 FIRST: Ensure user_moodle_data[phone] exists
                if phone not in user_moodle_data:
                    user_moodle_data[phone] = {}
                
                # 🎯 SECOND: Set the intent BEFORE changing state
                user_moodle_data[phone]['original_intent'] = {
                    'action': 'view_enrolled_courses'
                }
                
                # 🎯 THIRD: Change state to start login flow
                user_state[phone] = "moodle_username"
                
                response_text = localize(
                    phone,
                    "🔐 *Login Required*\n\n"
                    "To view your enrolled courses, you need to login first.\n\n"
                    "Please enter your username:",
                    "🔐 *Okweyingiza Kwetaagisa*\n\n"
                    "Okulaba amasomo go ge nnegattako, sooka weyingize.\n\n"
                    "Wandiika erinnya lyo ery'okweyingiza:"
                )

        elif user_msg in ["3", "quiz"]:
            # Check if user is logged into Moodle
            if phone in user_moodle_data and 'token' in user_moodle_data[phone]:
                # User is logged in - show their enrolled courses
                token = user_moodle_data[phone]['token']
                userid = user_moodle_data[phone]['userid']
                
                enrolled_courses = await get_user_enrolled_courses_moodle_async(token, userid)
                
                if not enrolled_courses:
                    response_text = (
                        "📝 *Take a Quiz*\n\n"
                        "You are not enrolled in any courses yet.\n\n"
                        "💡 Browse courses (option 1) to enroll in new courses.\n\n"
                        "0️⃣ Main Menu • #️⃣ Exit"
                    )
                    user_state[phone] = "main_menu"
                else:
                    # Store enrolled courses for later use
                    user_moodle_data[phone]['enrolled_courses'] = enrolled_courses
                    
                    # Build course list
                    course_list = "\n".join([f"{i+1}. {course['name']}" for i, course in enumerate(enrolled_courses)])
                    response_text = (
                        "📝 *Select a Course for Quiz*\n\n"
                        f"{course_list}\n\n"
                        "0️⃣ Main Menu • #️⃣ Exit\n\n"
                        "Select a course number to view its quizzes:"
                    )
                    user_state[phone] = "quiz_course_selection"
            else:
                # User not logged in - prompt for login
                if phone not in user_moodle_data:
                    user_moodle_data[phone] = {}
                
                user_moodle_data[phone]['original_intent'] = {
                    'action': 'take_quiz'
                }
                
                user_state[phone] = "moodle_username"
                response_text = (
                    "🔐 *Login Required*\n\n"
                    "To take quizzes, you need to login to Moodle first.\n\n"
                    "Please enter your username:"
                )
            
        elif user_msg in ["4", "results"]:
            user_state[phone] = "view_results"
            response_text = localize(
                phone,
                "📊 *Your Quiz Results*\n\n"
                "🦠 Infection Prevention: 85%\n"
                "🛡️ Safety Procedures: 92%\n"
                "🚨 Emergency Protocols: 78%\n\n"
                "Overall Performance: Good! 🎉\n\n"
                "0️⃣ Main Menu • 3️⃣ Take New Quiz",
                "📊 *Ebivudde mu Bigezo Byo*\n\n"
                "🦠 Infection Prevention: 85%\n"
                "🛡️ Safety Procedures: 92%\n"
                "🚨 Emergency Protocols: 78%\n\n"
                "Emitendera gyo okutwalira awamu: Girungi! 🎉\n\n"
                "0️⃣ Main Menu • 3️⃣ Kola Ekigezo Ekipya"
            )
            
        elif user_msg in ["5", "help", "trainer"]:
            # Check if user is logged into Moodle
            if phone not in user_moodle_data or 'token' not in user_moodle_data.get(phone, {}):
                # Store intent for after login
                if phone not in user_moodle_data:
                    user_moodle_data[phone] = {}
                user_moodle_data[phone]['original_intent'] = {
                    'action': 'ask_trainer'
                }
                user_state[phone] = "moodle_username"
                response_text = localize(
                    phone,
                    "🔐 *Login Required*\n\n"
                    "To ask a trainer, you need to login to Moodle first.\n\n"
                    "Please enter your Moodle username:",
                    "🔐 *Okweyingiza Kwetaagisa*\n\n"
                    "Okubuuza omusomesa, sooka weyingize ku Moodle.\n\n"
                    "Wandiika erinnya lyo ery'okweyingiza ku Moodle:"
                )
                return twiml_message(response_text)
            
            # User is logged in - get their ENROLLED courses
            token = user_moodle_data[phone]['token']
            userid = user_moodle_data[phone]['userid']
            enrolled_courses = await get_user_enrolled_courses_moodle_async(token, userid)
            
            if not enrolled_courses:
                response_text = localize(
                    phone,
                    "📚 *No Enrolled Courses*\n\n"
                    "You are not enrolled in any courses yet.\n\n"
                    "Please enroll in courses first (Option 1 from main menu).\n\n"
                    "0️⃣ Main Menu",
                    "📚 *Tewali Masomo Gewegattako*\n\n"
                    "Tonnawegatta ku masomo gonna.\n\n"
                    "Sooka weegatte ku masomo (Option 1 okuva ku main menu).\n\n"
                    "0️⃣ Main Menu"
                )
                user_state[phone] = "main_menu"
                return twiml_message(response_text)
            
            # Store enrolled courses and go to course selection
            user_moodle_data[phone]['enrolled_courses'] = enrolled_courses
            user_state[phone] = "trainer_course_selection"
            
            # Build course list
            course_list = "\n".join([f"{i+1}. {course['name']}" for i, course in enumerate(enrolled_courses)])
            response_text = localize(
                phone,
                f"👨‍🏫 *Ask a Trainer*\n\n"
                f"📋 *Instructions:*\n"
                f"• Select a course you're enrolled in from the list below\n"
                f"• Type your question about that course\n"
                f"• Your question will be sent to the course teacher(s)\n"
                f"• Teachers will reply to you via WhatsApp or Email\n\n"
                f"📚 *Your Enrolled Courses:*\n"
                f"{course_list}\n\n"
                f"Enter the course number:\n\n"
                f"0️⃣ Main Menu • #️⃣ Exit",
                f"👨‍🏫 *Buuza Omusomesa*\n\n"
                f"📋 *Ebigendererwa:*\n"
                f"• Londa essomo lino okuva mu lukalala wammanga\n"
                f"• Wandiika ekibuuzo kyo ku essomo eryo\n"
                f"• Ekibuuzo kyo kijja kusindikibwa eri omusomesa w'essomo\n"
                f"• Abasomesa bajja kukuddamu okuyita mu WhatsApp oba Email\n\n"
                f"📚 *Amasomo Go Gewegattako:*\n"
                f"{course_list}\n\n"
                f"Wandiika namba y'essomo:\n\n"
                f"0️⃣ Main Menu • #️⃣ Mala"
            )
            return twiml_message(response_text)
            
        elif user_msg in ["6", "ask", "question"]:
            # Fetch courses (cached first)
            courses = user_moodle_data.get(phone, {}).get('available_courses')
            if not courses:
                courses = get_available_courses()

            # Store courses for context
            if phone not in user_moodle_data:
                user_moodle_data[phone] = {}
            user_moodle_data[phone]['available_courses'] = courses

            # Move directly to question mode
            user_state[phone] = "question_mode"

            # Format course list (for display only)
            if courses:
                course_list = "\n".join([f"• {c['name']}" for c in courses.values()])
                course_text = f"📚 *Available Courses:*\n{course_list}\n\n"
            else:
                course_text = ""

            response_text = (
                f"{course_text}"
                "💬 *Ask Your Question*\n\n"
                "You can ask about any of the courses above.\n\n"
                "Just type your question below:\n\n"
                "0️⃣ Main Menu • #️⃣ Exit"
            )

            return twiml_message(response_text)
        
        elif user_msg in ["7", "language", "lang", "olulimi"]:
            user_state[phone] = "language_selection_menu"
            response_text = language_selection_text(change_mode=True)
            
        elif user_msg in ["#", "exit", "quit"]:
            response_text = goodbye_text(phone)
            user_state.pop(phone, None)
            clear_session_language(phone)
        else:
            response_text = localize(
                phone,
                "Invalid option. Please reply with:\n"
                "1️⃣-7️⃣ for actions or 0️⃣ for main menu",
                "Olonze bubi. Ddamu nga okozesa:\n"
                "1️⃣-7️⃣ okukola ebikolebwa oba 0️⃣ okudda ku main menu"
            )
        
        return twiml_message(response_text)

    # ====== QUIZ SELECTION HANDLER ======
    if user_state[phone] == "quiz_selection":
        if user_msg in ["0", "menu", "main menu"]:
            user_state[phone] = "main_menu"
            return twiml_message(main_menu_text(phone))
        if user_msg in ["#", "exit"]:
            user_state.pop(phone, None)
            clear_session_language(phone)
            return twiml_message(goodbye_text(phone))
        if user_msg in ["1", "2", "3"]:
            user_state[phone] = "view_results"
            quiz_names = {
                "1": "Infection Prevention Basics",
                "2": "Safety Procedures",
                "3": "Emergency Protocols",
            }
            return twiml_message(
                localize(
                    phone,
                    f"✅ You selected *{quiz_names[user_msg]}*.\n\n"
                    "This demo bot currently shows sample results only.\n\n"
                    "4️⃣ View Quiz Results • 0️⃣ Main Menu",
                    f"✅ Olonze *{quiz_names[user_msg]}*.\n\n"
                    "Demo bot eno eraga ebyokulabirako byokka ku bivudde mu bigezo.\n\n"
                    "4️⃣ Laba Ebivudde mu Kigezo • 0️⃣ Main Menu"
                )
            )
        return twiml_message(localize(phone, "Please select quiz 1, 2, 3 or 0 for main menu.", "Londa ekigezo 1, 2, 3 oba 0 okudda ku main menu."))

    # ====== VIEW RESULTS HANDLER ======
    if user_state[phone] == "view_results":
        if user_msg in ["0", "menu", "main menu"]:
            user_state[phone] = "main_menu"
            return twiml_message(main_menu_text(phone))
        if user_msg in ["3", "quiz", "take new quiz"]:
            user_state[phone] = "quiz_selection"
            return twiml_message(
                localize(
                    phone,
                    "📝 *Quiz Center*\n\n"
                    "Available quizzes:\n"
                    "1. Infection Prevention Basics\n"
                    "2. Safety Procedures\n"
                    "3. Emergency Protocols\n\n"
                    "0️⃣ Main Menu • #️⃣ Exit\n\n"
                    "Select a quiz number to start:",
                    "📝 *Ekifo ky'Ebigezo*\n\n"
                    "Ebigezo ebiriwo:\n"
                    "1. Infection Prevention Basics\n"
                    "2. Safety Procedures\n"
                    "3. Emergency Protocols\n\n"
                    "0️⃣ Main Menu • #️⃣ Mala\n\n"
                    "Londa namba y'ekigezo okutandika:"
                )
            )
        if user_msg in ["#", "exit"]:
            user_state.pop(phone, None)
            clear_session_language(phone)
            return twiml_message(goodbye_text(phone))
        return twiml_message(
            localize(
                phone,
                "📊 *Your Quiz Results*\n\n"
                "🦠 Infection Prevention: 85%\n"
                "🛡️ Safety Procedures: 92%\n"
                "🚨 Emergency Protocols: 78%\n\n"
                "Overall Performance: Good! 🎉\n\n"
                "0️⃣ Main Menu • 3️⃣ Take New Quiz",
                "📊 *Ebivudde mu Bigezo Byo*\n\n"
                "🦠 Infection Prevention: 85%\n"
                "🛡️ Safety Procedures: 92%\n"
                "🚨 Emergency Protocols: 78%\n\n"
                "Emitendera gyo okutwalira awamu: Girungi! 🎉\n\n"
                "0️⃣ Main Menu • 3️⃣ Kola Ekigezo Ekipya"
            )
        )


    # ====== TRAINER COURSE SELECTION HANDLER ======
    # This handles when user selects a course number from the list
    if user_state[phone] == "trainer_course_selection":
        if user_msg in ["0", "menu", "main menu"]:
            user_state[phone] = "main_menu"
            return twiml_message(main_menu_text(phone))
        
        if user_msg in ["#", "exit"]:
            user_state.pop(phone, None)
            clear_session_language(phone)
            return twiml_message(goodbye_text(phone))
        
        # User should enter a course number
        if not user_msg.isdigit():
            response_text = localize(
                phone,
                "Please enter a valid course number from the list.",
                "Wandiika namba y'essomo esinga okuva ku lukalala."
            )
            return twiml_message(response_text)
        
        selected_index = int(user_msg) - 1
        enrolled_courses = user_moodle_data.get(phone, {}).get('enrolled_courses', [])
        
        if not enrolled_courses:
            # Try to fetch again
            token = user_moodle_data[phone]['token']
            userid = user_moodle_data[phone]['userid']
            enrolled_courses = await get_user_enrolled_courses_moodle_async(token, userid)
            user_moodle_data[phone]['enrolled_courses'] = enrolled_courses
        
        if 0 <= selected_index < len(enrolled_courses):
            selected_course = enrolled_courses[selected_index]
            course_id = selected_course['id']
            course_name = selected_course['name']
            
            # Get teachers for this specific course from Moodle
            token = user_moodle_data[phone]['token']
            
            # Import teacher function from moodle_service
            from app.services.moodle_service import get_course_teachers_comprehensive_async
            
            teachers = await get_course_teachers_comprehensive_async(token, course_id)
            
            if not teachers:
                response_text = localize(
                    phone,
                    f"⚠️ *No Teachers Assigned*\n\n"
                    f"No teachers are currently assigned to '{course_name}'.\n\n"
                    f"Please contact the administrator.\n\n"
                    f"0️⃣ Main Menu",
                    f"⚠️ *Tewali Basomesa Bagabuddwa*\n\n"
                    f"Tewali musomesa agabudwa ku '{course_name}' kati.\n\n"
                    f"Tukirira omuddukanya.\n\n"
                    f"0️⃣ Main Menu"
                )
                user_state[phone] = "main_menu"
                return twiml_message(response_text)
            
            # Store selected course and teachers
            user_moodle_data[phone]['selected_course'] = {
                'id': course_id,
                'name': course_name,
                'teachers': teachers
            }
            user_state[phone] = "trainer_question_input"
            
            # Show teacher info to the learner
            teacher_names = ", ".join([t.get('fullname', 'Teacher') for t in teachers[:3]])
            if len(teachers) > 3:
                teacher_names += f" and {len(teachers) - 3} others"
            
            response_text = localize(
                phone,
                f"👨‍🏫 *Ask {course_name} Teacher(s)*\n\n"
                f"📋 Course: {course_name}\n"
                f"👨‍🏫 Teachers: {teacher_names}\n\n"
                f"Please type your question below:\n\n"
                f"0️⃣ Cancel",
                f"👨‍🏫 *Buuza Omusomesa wa {course_name}*\n\n"
                f"📋 Essomo: {course_name}\n"
                f"👨‍🏫 Abasomesa: {teacher_names}\n\n"
                f"Wandiika ekibuuzo kyo wansi:\n\n"
                f"0️⃣ Siba"
            )
            return twiml_message(response_text)
        else:
            response_text = localize(
                phone,
                f"Invalid course number. Please select 1-{len(enrolled_courses)}.",
                f"Namba y'essomo si ntuufu. Londa 1-{len(enrolled_courses)}."
            )
            return twiml_message(response_text)

    # # ====== TRAINER QUESTION INPUT HANDLER ======
    # # This handles when user types their question after selecting a course
    # if user_state[phone] == "trainer_question_input":
    #     if user_msg in ["0", "menu", "main menu"]:
    #         user_state[phone] = "main_menu"
    #         if phone in user_moodle_data:
    #             user_moodle_data[phone].pop('selected_course', None)
    #         return twiml_message(main_menu_text(phone))
        
    #     if user_msg in ["#", "exit"]:
    #         user_state.pop(phone, None)
    #         clear_session_language(phone)
    #         return twiml_message(goodbye_text(phone))
        
    #     # Get the selected course and teachers
    #     selected_data = user_moodle_data.get(phone, {}).get('selected_course')
        
    #     if not selected_data:
    #         user_state[phone] = "main_menu"
    #         response_text = localize(phone, "Session expired. Please start over.", "Session yazze. Sooka ku ntandikwa.")
    #         return twiml_message(response_text)
        
    #     course_id = selected_data['id']
    #     course_name = selected_data['name']
    #     teachers = selected_data['teachers']
    #     question = raw_msg
        
    #     # Get the learner's name
    #     learner_name = user_moodle_data.get(phone, {}).get('fullname', 'A learner')
        
    #     # Generate unique question ID
    #     question_id = f"Q{int(time.time())}_{phone[-6:]}"
        
    #     # Store question for tracking
    #     if 'pending_questions' not in user_moodle_data:
    #         user_moodle_data['pending_questions'] = {}
        
    #     user_moodle_data['pending_questions'][question_id] = {
    #         'learner_phone': phone,
    #         'learner_name': learner_name,
    #         'course_id': course_id,
    #         'course_name': course_name,
    #         'question': question,
    #         'timestamp': datetime.now().isoformat(),
    #         'status': 'pending',
    #         'teachers_notified': []
    #     }
        
    #     # Send question to each teacher assigned to this course
    #     notified_count = 0
    #     for teacher in teachers:
    #         if teacher.get('contact_method') == 'whatsapp' and teacher.get('phone'):
    #             message = (
    #                 f"👨‍🏫 *New Question from Student*\n\n"
    #                 f"📚 Course: {course_name}\n"
    #                 f"👤 Student: {learner_name}\n"
    #                 f"📱 Student Phone: {phone}\n"
    #                 f"❓ Question: {question}\n\n"
    #                 f"━━━━━━━━━━━━━━━━━━━━\n"
    #                 f"💡 *To reply to this student:*\n"
    #                 f"Send: /reply {question_id} [your answer]\n\n"
    #                 f"Example: /reply {question_id} Thank you for your question. The answer is...\n"
    #                 f"━━━━━━━━━━━━━━━━━━━━\n"
    #                 f"✅ The student will receive your reply immediately."
    #             )
                
    #             teacher_whatsapp = teacher['phone']
    #             if not teacher_whatsapp.startswith('whatsapp:'):
    #                 teacher_whatsapp = f"whatsapp:{teacher_whatsapp}"
                
    #             await _send_whatsapp_message(teacher_whatsapp, message)
    #             notified_count += 1
    #             user_moodle_data['pending_questions'][question_id]['teachers_notified'].append({
    #                 'name': teacher.get('fullname'),
    #                 'phone': teacher_whatsapp
    #             })
    #             print(f"✅ Notified teacher {teacher.get('fullname')} for course {course_name}")
        
    #     # Clear selected course and return to main menu
    #     user_moodle_data[phone].pop('selected_course', None)
    #     user_state[phone] = "main_menu"
        
    #     if notified_count > 0:
    #         response_text = localize(
    #             phone,
    #             f"✅ *Question Sent Successfully!*\n\n"
    #             f"📚 Course: {course_name}\n"
    #             f"👨‍🏫 Notified: {notified_count} teacher(s)\n"
    #             f"❓ Question: {question[:100]}...\n\n"
    #             f"📋 Reference ID: {question_id}\n\n"
    #             f"Teachers have been notified and will respond shortly.\n\n"
    #             f"💡 You will receive their response here on WhatsApp.\n\n"
    #             f"0️⃣ Main Menu",
    #             f"✅ *Ekibuuzo Kisindikiddwa!*\n\n"
    #             f"📚 Essomo: {course_name}\n"
    #             f"👨‍🏫 Bamanyisiddwa: {notified_count} omusomesa\n"
    #             f"❓ Ekibuuzo: {question[:100]}...\n\n"
    #             f"📋 Koodi y'ekibuuzo: {question_id}\n\n"
    #             f"Abasomesa bamanyisiddwa era bajja kukuddamu mangu.\n\n"
    #             f"💡 Ojja kufuna okuddamu kwaabwe wano ku WhatsApp.\n\n"
    #             f"0️⃣ Main Menu"
    #         )
    #     else:
    #         response_text = localize(
    #             phone,
    #             f"⚠️ *Unable to Send Question*\n\n"
    #             f"📚 Course: {course_name}\n\n"
    #             f"No WhatsApp-enabled teachers found for this course.\n\n"
    #             f"Please contact support or try another course.\n\n"
    #             f"0️⃣ Main Menu",
    #             f"⚠️ *Tewali Basomesa Baliwoko*\n\n"
    #             f"📚 Essomo: {course_name}\n\n"
    #             f"Tewali musomesa alina WhatsApp ku ssomo lino.\n\n"
    #             f"Tukirira support oba gezaako essomo eddala.\n\n"
    #             f"0️⃣ Main Menu"
    #         )
        
    #     return twiml_message(response_text)

    # ====== TRAINER QUESTION INPUT HANDLER ======
    if user_state[phone] == "trainer_question_input":
        if user_msg in ["0", "menu", "main menu"]:
            user_state[phone] = "main_menu"
            if phone in user_moodle_data:
                user_moodle_data[phone].pop('selected_course', None)
            return twiml_message(main_menu_text(phone))
        
        if user_msg in ["#", "exit"]:
            user_state.pop(phone, None)
            clear_session_language(phone)
            return twiml_message(goodbye_text(phone))
        
        # Get the selected course and teachers
        selected_data = user_moodle_data.get(phone, {}).get('selected_course')
        
        if not selected_data:
            user_state[phone] = "main_menu"
            response_text = localize(phone, "Session expired. Please start over.", "Session yazze. Sooka ku ntandikwa.")
            return twiml_message(response_text)
        
        course_id = selected_data['id']
        course_name = selected_data['name']
        teachers = selected_data['teachers']
        question = raw_msg
        
        # Get the learner's name
        learner_name = user_moodle_data.get(phone, {}).get('fullname', 'A learner')
        
        # Generate unique question ID
        question_id = f"Q{int(time.time())}_{phone[-6:]}"
        
        # Store question for tracking
        if 'pending_questions' not in user_moodle_data:
            user_moodle_data['pending_questions'] = {}
        
        user_moodle_data['pending_questions'][question_id] = {
            'learner_phone': phone,
            'learner_name': learner_name,
            'course_id': course_id,
            'course_name': course_name,
            'question': question,
            'timestamp': datetime.now().isoformat(),
            'status': 'pending',
            'teachers_notified': []
        }
        
        # Send question to each teacher using available contact methods
        whatsapp_count = 0
        email_count = 0
        
        for teacher in teachers:
            teacher_name = teacher.get('fullname', 'Teacher')
            teacher_email = teacher.get('email')
            teacher_phone = teacher.get('phone')
            notified = False
            
            # Try WhatsApp if phone number exists
            if teacher_phone:
                message = (
                    f"👨‍🏫 *New Question from Student*\n\n"
                    f"📚 Course: {course_name}\n"
                    f"👤 Student: {learner_name}\n"
                    f"📱 Student Phone: {phone}\n"
                    f"❓ Question: {question}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"💡 *To reply to this student:*\n"
                    f"Send: /reply {question_id} [your answer]\n\n"
                    f"Example: /reply {question_id} Thank you for your question...\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"✅ The student will receive your reply immediately."
                )
                
                teacher_whatsapp = teacher_phone
                if not teacher_whatsapp.startswith('whatsapp:'):
                    teacher_whatsapp = f"whatsapp:{teacher_whatsapp}"
                
                success = await _send_whatsapp_message(teacher_whatsapp, message)
                if success:
                    whatsapp_count += 1
                    notified = True
                    user_moodle_data['pending_questions'][question_id]['teachers_notified'].append({
                        'name': teacher_name,
                        'method': 'whatsapp',
                        'contact': teacher_whatsapp
                    })
                    print(f"✅ Notified teacher {teacher_name} via WhatsApp")
            
            # Fallback to email if WhatsApp failed or no phone number
            if not notified and teacher_email:
                subject = f"[Moodle Support] New Question from {learner_name} - {course_name}"
                body = f"""
Dear {teacher_name},

A student has asked a question about {course_name}.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STUDENT INFORMATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Name: {learner_name}
Phone: {phone}
Course: {course_name}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUESTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{question}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW TO REPLY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
To reply to this student:
1. Send a WhatsApp message to: {phone}
2. Or reply to this email

Reference ID: {question_id}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The student is waiting for your response.
"""
                
                success = await _send_email(teacher_email, subject, body)
                if success:
                    email_count += 1
                    notified = True
                    user_moodle_data['pending_questions'][question_id]['teachers_notified'].append({
                        'name': teacher_name,
                        'method': 'email',
                        'contact': teacher_email
                    })
                    print(f"✅ Notified teacher {teacher_name} via Email to {teacher_email}")
                else:
                    print(f"⚠️ Failed to send email to {teacher_name}")
            
            if not notified:
                print(f"⚠️ No contact method for teacher {teacher_name}")
        
        total_notified = whatsapp_count + email_count
        
        # Clear selected course and return to main menu
        user_moodle_data[phone].pop('selected_course', None)
        user_state[phone] = "main_menu"
        
        if total_notified > 0:
            # Build notification summary
            methods = []
            if whatsapp_count > 0:
                methods.append(f"{whatsapp_count} via WhatsApp")
            if email_count > 0:
                methods.append(f"{email_count} via Email")
            
            response_text = localize(
                phone,
                f"✅ *Question Sent Successfully!*\n\n"
                f"📚 Course: {course_name}\n"
                f"👨‍🏫 Notified: {total_notified} teacher(s) ({', '.join(methods)})\n"
                f"❓ Question: {question[:100]}...\n\n"
                f"📋 Reference ID: {question_id}\n\n"
                f"Teachers have been notified and will respond shortly.\n\n"
                f"💡 You will receive their response here on WhatsApp.\n\n"
                f"0️⃣ Main Menu",
                f"✅ *Ekibuuzo Kisindikiddwa!*\n\n"
                f"📚 Essomo: {course_name}\n"
                f"👨‍🏫 Bamanyisiddwa: {total_notified} omusomesa ({', '.join(methods)})\n"
                f"❓ Ekibuuzo: {question[:100]}...\n\n"
                f"📋 Koodi y'ekibuuzo: {question_id}\n\n"
                f"Abasomesa bamanyisiddwa era bajja kukuddamu mangu.\n\n"
                f"💡 Ojja kufuna okuddamu kwaabwe wano ku WhatsApp.\n\n"
                f"0️⃣ Main Menu"
            )
        else:
            response_text = localize(
                phone,
                f"⚠️ *Unable to Send Question*\n\n"
                f"📚 Course: {course_name}\n\n"
                f"No contact methods available for teachers of this course.\n\n"
                f"Please contact support or try another course.\n\n"
                f"0️⃣ Main Menu",
                f"⚠️ *Tewali Basomesa Baliwoko*\n\n"
                f"📚 Essomo: {course_name}\n\n"
                f"Tewali musomesa alina WhatsApp oba email ku ssomo lino.\n\n"
                f"Tukirira support oba gezaako essomo eddala.\n\n"
                f"0️⃣ Main Menu"
            )
        
        return twiml_message(response_text)

    # ====== QUESTION MODE HANDLER ======
    if user_state[phone] == "question_mode":
    
        if user_msg in ["0", "menu", "main menu"]:
            user_state[phone] = "main_menu"
            # Clear the selected course
            if phone in user_moodle_data:
                user_moodle_data[phone].pop('selected_question_course', None)
            return twiml_message(main_menu_text(phone))
        
        if user_msg == "9" and user_state[phone] == "question_mode_with_course":
            # Go back to course selection
            user_state[phone] = "main_menu"
            return twiml_message(main_menu_text(phone))
        
        if user_msg in ["#", "exit"]:
            user_state.pop(phone, None)
            clear_session_language(phone)
            return twiml_message(goodbye_text(phone))

        if WHATSAPP_ASYNC_QA and _twilio_ready():
            payload = ChatRequest(
                question=raw_msg,
                context_prompt="Respond in Luganda." if get_session_language(phone) == "lg" else None,
            )
            await OUTBOUND_QUEUE.put({"type": "qa", "phone": phone, "payload": payload})
            response_text = localize(
                phone,
                "✅ Got it! I'm working on your answer and will reply shortly.",
                "✅ Nkimanyi! Nkolela ku kibuuzo kyo era ndiddamu mangu."
            )
            return twiml_message(response_text)

        try:
            # Get course context if available
            course_context = ""
            selected_course = None
            
            if user_state[phone] == "question_mode_with_course" and phone in user_moodle_data:
                selected_course = user_moodle_data[phone].get('selected_question_course', {})
                if selected_course:
                    course_context = f" (regarding the course: {selected_course['name']})"
            
            # Call the AI knowledge assistant
            chat_response = answer_question(
                ChatRequest(
                    question=raw_msg,
                    context_prompt=f"Answer based on the course materials. User is asking about: {selected_course['name'] if selected_course else 'general topics'}" if course_context else None,
                )
            )            
            # Format the response
            response_text = f"🤖 {chat_response.answer}\n\n"
            if selected_course:
                response_text += f"📚 *Course:* {selected_course['name']}\n\n"
            response_text += "Ask another question, or reply 0 for main menu (or 9 to change course)."

        except Exception as e:
            print(f"Q&A error: {e}")
            response_text = "⚠️ I could not process your question right now.\n\nPlease try again, or reply 0 for main menu."
        
        # USE html.escape to ensure the XML is 100% valid
        safe_text = html.escape(response_text)
        raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{safe_text}</Message></Response>'
        return Response(content=raw_xml, media_type="application/xml")

    # ====== MY ENROLLED COURSES HANDLER ======
    if user_state[phone] == "my_courses":
        if user_msg in ["0", "menu", "main menu"]:
            user_state[phone] = "main_menu"
            response_text = main_menu_text(phone)
        elif user_msg == "9":
            user_state[phone] = "main_menu"
            response_text = main_menu_text(phone)
        elif user_msg in ["#", "exit"]:
            response_text = goodbye_text(phone)
            user_state.pop(phone, None)
            clear_session_language(phone)
        else:
            # Get user's enrolled courses
            if phone in user_moodle_data and 'token' in user_moodle_data[phone]:
                token = user_moodle_data[phone]['token']
                userid = user_moodle_data[phone]['userid']
                enrolled_courses = await get_user_enrolled_courses_moodle_async(token, userid)
                if user_msg.isdigit() and 1 <= int(user_msg) <= len(enrolled_courses):
                    selected_course = enrolled_courses[int(user_msg)-1]
                    course_id = selected_course['id']
                    
                    # Get course details and resources
                    all_courses = await get_courses(force_refresh=False)
                    course_data = all_courses.get(str(course_id), {})
                    
                    if course_data:
                        # Get fresh resources with user's token
                        token = user_moodle_data[phone]['token']
                        contents = await get_course_contents_moodle_async(token, int(course_id))
                        resources = await run_blocking(extract_moodle_resources, contents, token)
                        
                        user_state[phone] = f"enrolled_{course_id}"
                        
                        # Show dynamic overview
                        overview = create_course_overview(resources, selected_course['name'], len(course_data.get('quizzes', [])))
                        response_text = overview
                    else:
                        response_text = localize(
                            phone,
                            f"Course content not available for: {selected_course['name']}\n\nPlease try another course or contact support.",
                            f"Ebirimu eby'essomo tebiriwo ku: {selected_course['name']}\n\nGezaako essomo eddala oba otuukirire abayambi."
                        )
                else:
                    response_text = localize(
                        phone,
                        "Invalid course number.\n\n💡 *Navigation:*\n0️⃣ Main Menu • #️⃣ Exit",
                        "Namba y'essomo si ntuufu.\n\n💡 *Navigation:*\n0️⃣ Main Menu • #️⃣ Mala"
                    )
            else:
                response_text = localize(phone, "Please login first to access your courses.", "Sooka weyingize okufuna amasomo go.")
                user_state[phone] = "main_menu"
        
        escaped_text = escape_xml(response_text)
        raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
        return Response(content=raw_xml, media_type="application/xml")
    
    # ====== QUIZ COURSE SELECTION HANDLER ======
    if user_state[phone] == "quiz_course_selection":
        if user_msg in ["0", "menu", "main menu"]:
            user_state[phone] = "main_menu"
            response_text = (
                "👋 Welcome back to MoH E-Learning Assistant!\n\n"
                "📚 *Select Option to continue:*\n"
                "1️⃣ Browse Courses\n"
                "2️⃣ My Enrolled Courses\n"
                "3️⃣ Take a Quiz\n"
                "4️⃣ View Quiz Results\n"
                "5️⃣ Ask Trainer for Help\n"
                "6️⃣ Ask Question Q&A\n\n"
                "0️⃣ Main Menu • #️⃣ Exit"
            )
        elif user_msg in ["#", "exit"]:
            response_text = "👋 Thank you for using MoH E-Learning Assistant!"
            user_state.pop(phone, None)
        else:
            # Get user's enrolled courses
            if phone in user_moodle_data and 'enrolled_courses' in user_moodle_data[phone]:
                enrolled_courses = user_moodle_data[phone]['enrolled_courses']
                
                if user_msg.isdigit() and 1 <= int(user_msg) <= len(enrolled_courses):
                    selected_course = enrolled_courses[int(user_msg)-1]
                    course_id = selected_course['id']
                    
                    # Get course details with quizzes
                    all_courses = await get_courses(force_refresh=False)
                    course_data = all_courses.get(str(course_id), {})
                    
                    if course_data and course_data.get('quizzes') and len(course_data['quizzes']) > 0:
                        # Show the quiz response directly
                        raw_xml = create_quiz_response(course_data, base_url)
                        return Response(content=raw_xml, media_type="application/xml")
                    else:
                        response_text = (
                            f"📝 *{selected_course['name']}*\n\n"
                            "❌ No quizzes available for this course yet.\n\n"
                            "💡 *Navigation:*\n"
                            "0️⃣ Main Menu • 9️⃣ Back to Course Selection • #️⃣ Exit"
                        )
                        # Keep user in quiz_course_selection state to select another course
                else:
                    response_text = (
                        "Invalid course number.\n\n"
                        "Please select a valid course number.\n\n"
                        "0️⃣ Main Menu • #️⃣ Exit"
                    )
            else:
                response_text = "Session expired. Please start again."
                user_state[phone] = "main_menu"
        
        escaped_text = escape_xml(response_text)
        raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
        return Response(content=raw_xml, media_type="application/xml")

    # ====== BROWSE COURSES HANDLER ======
    if user_state[phone] == "browse_courses":
        if user_msg in ["0", "menu", "main menu"]:
            user_state[phone] = "main_menu"
            response_text = main_menu_text(phone)
            return twiml_message(response_text)
            
        elif user_msg in ["#", "exit"]:
            response_text = goodbye_text(phone)
            user_state.pop(phone, None)
            return twiml_message(response_text)
            
        else:
            # Get fresh courses list
            all_courses = await get_courses(force_refresh=False)
            
            if not all_courses:
                response_text = "No courses available at the moment. Please try again later."
                return twiml_message(response_text)
                
            course_keys = list(all_courses.keys())
            
            # Check if user input is a valid number
            if user_msg.isdigit():
                selected_num = int(user_msg)
                
                if 1 <= selected_num <= len(course_keys):
                    selected_course_id = course_keys[selected_num - 1]
                    selected_course = all_courses[selected_course_id]
                                        
                    # CHECK IF USER IS LOGGED IN
                    if phone not in user_moodle_data or 'token' not in user_moodle_data.get(phone, {}):
                        # Store original intent for after login
                        user_moodle_data.setdefault(phone, {})
                        user_moodle_data[phone]['original_intent'] = {
                            'action': 'check_enrollment',
                            'course_id': int(selected_course_id),
                            'course_name': selected_course['name']
                        }
                        user_state[phone] = "moodle_username"
                        
                        response_text = (
                            f"🔐 *Login Required*\n\n"
                            f"To view '{selected_course['name']}' or enroll, please login first.\n\n"
                            "Enter your Moodle username:"
                        )
                        return twiml_message(response_text)
                    
                    # User is logged in - check enrollment
                    token = user_moodle_data[phone]['token']
                    userid = user_moodle_data[phone]['userid']
                    
                    try:
                        enrolled_courses = await get_user_enrolled_courses_moodle_async(token, userid)
                        user_moodle_data[phone]['enrolled_courses'] = enrolled_courses
                        
                        # Check if user is enrolled in this course
                        is_enrolled = any(str(course['id']) == str(selected_course_id) for course in enrolled_courses)
                        
                        if is_enrolled:
                            # User is enrolled - get course contents and show overview
                            user_state[phone] = f"enrolled_{selected_course_id}"
                            
                            # Get course contents with user's token
                            contents = await get_course_contents_moodle_async(token, int(selected_course_id))
                            resources = await run_blocking(extract_moodle_resources, contents, token)
                            
                            # Show dynamic overview
                            overview = create_course_overview(
                                resources, 
                                selected_course['name'], 
                                len(selected_course.get('quizzes', []))
                            )
                            return twiml_message(overview)
                            
                        else:
                            # User is not enrolled - show enroll option
                            user_state[phone] = f"browsing_{selected_course_id}"
                            
                            # Get course contents preview (without enrollment)
                            contents = await get_course_contents_moodle_async(token, int(selected_course_id))
                            resources = await run_blocking(extract_moodle_resources, contents, token)
                            
                            # Count resources for preview
                            total_files = sum(len(resources.get(cat, [])) for cat in resources.keys())
                            
                            response_text = (
                                f"📚 *{selected_course['name']}*\n\n"
                                f"📊 *Course Overview:*\n"
                                f"• {len(resources.get('documents', []))} Documents\n"
                                f"• {len(resources.get('videos', []))} Videos\n"
                                f"• {len(resources.get('presentations', []))} Presentations\n"
                                f"• {len(selected_course.get('quizzes', []))} Quizzes\n\n"
                                f"📁 Total Resources: {total_files}\n\n"
                                f"🔒 *You are NOT enrolled in this course*\n\n"
                                f"1️⃣ Enroll in this Course\n\n"
                                f"💡 *Navigation:*\n"
                                f"0️⃣ Main Menu • 9️⃣ Back to Browse • #️⃣ Exit"
                            )
                            return twiml_message(response_text)
                            
                    except Exception as e:
                        print(f"❌ Error checking enrollment: {e}")
                        response_text = "An error occurred. Please try again or contact support."
                        return twiml_message(response_text)
                        
                else:
                    response_text = (
                        f"Invalid course number. Please select a number between 1 and {len(course_keys)}.\n\n"
                        "0️⃣ Main Menu • #️⃣ Exit"
                    )
                    return twiml_message(response_text)
            else:
                response_text = (
                    "Invalid input. Please enter a valid course number.\n\n"
                    "0️⃣ Main Menu • #️⃣ Exit"
                )
                return twiml_message(response_text)

    # ====== ENROLLED COURSE ACTIONS ======
    courses = await get_courses(force_refresh=False)
    print(courses)
    for course_id, course_data in courses.items():
        if user_state[phone] == f"enrolled_{course_id}":
            # Check if user is logged in
            if phone not in user_moodle_data or 'token' not in user_moodle_data[phone]:
                response_text = localize(phone, "Please login to access course materials.", "Sooka weyingize okufuna ebikozesebwa by'essomo.")
                return twiml_message(response_text)
            
            # User is logged in - use Moodle system
            token = user_moodle_data[phone]['token']
            
            # Get ALL resources using the dynamic extractor
            contents = await get_course_contents_moodle_async(token, int(course_id))
            resources = await run_blocking(extract_moodle_resources, contents, token)
            
            # ====== HANDLE NAVIGATION FIRST ======
            if user_msg == "9":
                user_state[phone] = "browse_courses"
                
                # Get and display the course list
                all_courses = get_available_courses(force_refresh=False)
                
                if not all_courses:
                    response_text = browse_courses_empty_text(phone)
                else:
                    course_list = "\n".join([f"{i+1}. {course['name']}" for i, course in enumerate(all_courses.values())])
                    response_text = localize(
                        phone,
                        "📚 *Browse All Courses*\n\n"
                        f"{course_list}\n\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        "💡 Select a course number to view details\n\n"
                        "0️⃣ Main Menu • #️⃣ Exit",
                        "📚 *Laba Amasomo Gonna*\n\n"
                        f"{course_list}\n\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        "💡 Londa namba y'essomo okulaba ebisingawo\n\n"
                        "0️⃣ Main Menu • #️⃣ Mala"
                    )
                
                return twiml_message(response_text)
            
            if user_msg in ["0", "menu", "main menu"]:
                user_state[phone] = "main_menu"
                response_text = main_menu_text(phone)
                return twiml_message(response_text)
            
            if user_msg in ["#", "exit"]:
                response_text = goodbye_text(phone)
                user_state.pop(phone, None)
                clear_session_language(phone)
                return twiml_message(response_text)
            
            # ====== THEN HANDLE CATEGORY SELECTION ======
            # Define all possible categories in desired display order
            all_categories = [
                ('documents', '📄'),
                ('presentations', '📊'),
                ('spreadsheets', '📈'),
                ('images', '🖼️'),
                ('audio', '🎵'),
                ('videos', '🎥'),
                ('archives', '📦'),
                ('other', '📁')
            ]
            
            # Get ONLY the categories that actually have content
            available_categories = []
            for category_key, icon in all_categories:
                if resources.get(category_key):
                    available_categories.append((category_key, icon))
            
            # Get quiz count
            quiz_count = len(course_data.get('quizzes', []))
            
            # Check if user selected a category (based on menu position)
            if user_msg.isdigit():
                selected_index = int(user_msg) - 1
                
                # Check if selection is within available categories
                if 0 <= selected_index < len(available_categories):
                    category_key, icon = available_categories[selected_index]
                    
                    # SPECIAL HANDLING FOR VIDEOS - Show options menu
                    if category_key == 'videos':
                        # Set state to moodle_videos for this course
                        user_state[phone] = f"moodle_videos_{course_id}"
                        
                        # Get videos from resources
                        videos = resources.get('videos', [])
                        video_count = len(videos)
                        
                        # Create options menu
                        response_text = (
                            f"🎥 *{course_data['name']} - Videos*\n\n"
                            f"Found {video_count} video(s).\n\n"
                            f"How would you like to access them?\n\n"
                            f"1️⃣ Get direct links (view in browser)\n"
                            f"2️⃣ Download to WhatsApp\n\n"
                            f"9️⃣ Back to Course • 0️⃣ Main Menu"
                        )
                        return twiml_message(response_text)
                    else:
                        # For all other categories, use the generic content response
                        raw_xml = create_generic_content_response(resources, course_data['name'], category_key)
                        return Response(content=raw_xml, media_type="application/xml")
                
                # Check if selection is the quiz option (always after categories)
                elif selected_index == len(available_categories) and quiz_count > 0:
                    raw_xml = create_quiz_response(course_data, base_url)
                    return Response(content=raw_xml, media_type="application/xml")
                
                # Handle invalid selections
                else:
                    response_text = localize(
                        phone,
                        "Invalid option. Please select a valid number.\n\n"
                        "0️⃣ Main Menu • 9️⃣ Back to My Courses • #️⃣ Exit",
                        "Olonze namba esinga. Londa namba esinga.\n\n"
                        "0️⃣ Main Menu • 9️⃣ Ddayo ku Masomo Gange • #️⃣ Mala"
                    )
                    return twiml_message(response_text)
            
            # If user input is not a digit, show the overview menu
            else:
                # Show dynamic overview menu
                overview = create_course_overview(resources, course_data['name'], quiz_count)
                return twiml_message(overview)

        # ====== MOODLE VIDEOS HANDLER ======
    courses = await get_courses(force_refresh=False)
    for course_id, course_data in courses.items():
        if user_state[phone] == f"moodle_videos_{course_id}":
            if user_msg == "1":
                # Get direct links (view in browser)
                token = user_moodle_data[phone]['token']
                contents = await get_course_contents_moodle_async(token, int(course_id))
                resources = await run_blocking(extract_moodle_resources, contents, token)
                videos = resources.get('videos', [])
                course_name = course_data["name"]
                
                if not videos:
                    response_text = localize(phone, "No videos available.", "Tewali vidiyo ziriwo.")
                else:
                    raw_xml = create_video_links_response(videos, course_name, phone=phone)
                    return Response(content=raw_xml, media_type="application/xml")
            elif user_msg == "2":
                # Download videos to WhatsApp
                token = user_moodle_data[phone]['token']
                contents = await get_course_contents_moodle_async(token, int(course_id))
                resources = await run_blocking(extract_moodle_resources, contents, token)
                video_urls = resources.get('videos', [])
                course_name = course_data["name"]
                
                if not video_urls:
                    response_text = localize(phone, "No videos available for this course.", "Tewali vidiyo ku ssomo lino.")
                    return twiml_message(response_text)
                
                # Send immediate acknowledgment
                ack_text = localize(
                    phone,
                    f"🎥 Downloading {len(video_urls)} video(s) for {course_name}. I'll send them shortly...",
                    f"🎥 Nkka vidiyo {len(video_urls)} ez'essomo {course_name}. Nja kuzisindika mangu..."
                )
                
                # Process videos asynchronously
                async def process_and_send_videos():
                    for video in video_urls:
                        video_title = video.get('title', 'Video')
                        video_url = video.get('url', '')
                        
                        if video_url:
                            try:
                                # Download video
                                local_path = await run_blocking(
                                    download_and_store_video, 
                                    video_url, 
                                    course_id, 
                                    video_title, 
                                    token
                                )
                                
                                if local_path and base_url:
                                    filename = os.path.basename(local_path)
                                    server_url = f"{base_url}/webhook/serve-video/{quote(filename)}"
                                    
                                    # Send as separate media message
                                    await _send_whatsapp_media(phone, f"🎥 {video_title}", server_url)
                                    
                            except Exception as e:
                                print(f"Error with {video_title}: {e}")
                                await _send_whatsapp_message(
                                    phone, 
                                    f"⚠️ Could not download: {video_title}"
                                )
                    
                    # Send completion message
                    await _send_whatsapp_message(
                        phone,
                        localize(
                            phone,
                            "✅ All videos sent! Reply 0 for main menu or 9 to go back.",
                            "✅ Vidiyo zonna zisindikiddwa! Ddamu ne 0 okudda ku main menu oba 9 okuddayo."
                        )
                    )
                
                # Start background task
                asyncio.create_task(process_and_send_videos())
                
                # Return immediate acknowledgment
                return twiml_message(ack_text)
                
            elif user_msg == "9":
                user_state[phone] = f"enrolled_{course_id}"
                response_text = localize(phone, "↩️ Returning to course options...", "↩️ Okudda ku by'oyinza okukola mu ssomo...")
                
            elif user_msg == "0":
                user_state[phone] = "main_menu"
                response_text = localize(phone, "Returning to main menu...", "Okudda ku main menu...")
                
            else:
                response_text = (
                    "Please select:\n"
                    "1️⃣ Get direct links (view in browser)\n"
                    "2️⃣ Download to WhatsApp\n"
                    "9️⃣ Back • 0️⃣ Main Menu"
                )
            
            return twiml_message(response_text)
    
    # ====== BROWSING SPECIFIC COURSE HANDLER ======
    for course_id, course_data in courses.items():
        if user_state[phone] == f"browsing_{course_id}":
            base_url = BASE_URL
                
            if user_msg == "1":
                # Check if user is logged into Moodle
                if phone in user_moodle_data and 'token' in user_moodle_data[phone]:
                    # User is logged in - try to enroll
                    token = user_moodle_data[phone]['token']
                    userid = user_moodle_data[phone]['userid']
                    
                    # FIRST: Check if already enrolled (to avoid duplicate enrollment)
                    already_enrolled = False
                    try:
                        enrolled_courses = await get_user_enrolled_courses_moodle_async(token, userid)
                        for course in enrolled_courses:
                            if str(course['id']) == str(course_id):
                                already_enrolled = True
                                break
                    except Exception as e:
                        print(f"⚠️ Could not check current enrollments: {e}")
                    
                    if already_enrolled:
                        # User is already enrolled - show course content with proper resources
                        user_state[phone] = f"enrolled_{course_id}"
                        
                        # Get fresh resources with user's token
                        token = user_moodle_data[phone]['token']
                        contents = await get_course_contents_moodle_async(token, int(course_id))
                        resources = await run_blocking(extract_moodle_resources, contents, token)
                        
                        # FIXED: Correct the print statements
                        print("\n" + "="*50)
                        print("RESOURCES FOUND:")
                        print(f"Resources keys: {resources.keys()}")
                        print(f"Presentations count: {len(resources.get('presentations', []))}")
                        if resources.get('presentations'):
                            print("Presentations:")
                            for ppt in resources['presentations']:
                                print(f"  - {ppt.get('title')} ({ppt.get('filename')})")
                        print("="*50 + "\n")
                        
                        # Show dynamic overview
                        overview = create_course_overview(resources, course_data['name'], len(course_data.get('quizzes', [])))
                        print("OVERVIEW MENU:")
                        print(overview)
                        print("="*50)
                        
                        response_text = overview
                        return twiml_message(overview)
                    else:
                        # Try to enroll
                        success = await enroll_user_in_course_async(token, userid, int(course_id))
                        
                        if success:
                            await asyncio.sleep(2)  # Give Moodle time to process
                            if await is_enrolled_live(phone, course_id):
                                user_state[phone] = f"enrolled_{course_id}"
                            else:
                                user_state[phone] = "browse_courses"
                            # Verify enrollment by fetching updated course list
                            try:
                                updated_courses = await get_user_enrolled_courses_moodle_async(token, userid)
                                user_moodle_data[phone]['enrolled_courses'] = updated_courses
                                
                                # Verify the course is in the list
                                enrollment_verified = False
                                for course in updated_courses:
                                    if str(course['id']) == str(course_id):
                                        enrollment_verified = True
                                        break
                                
                                if enrollment_verified:
                                    user_state[phone] = f"enrolled_{course_id}"
                                    user_state[phone] = f"enrolled_{course_id}"
                        
                                    # Get fresh resources with user's token
                                    token = user_moodle_data[phone]['token']
                                    contents = await get_course_contents_moodle_async(token, int(course_id))
                                    resources = await run_blocking(extract_moodle_resources, contents, token)
                                    
                                    # FIXED: Correct the print statements
                                    print("\n" + "="*50)
                                    print("RESOURCES FOUND:")
                                    print(f"Resources keys: {resources.keys()}")
                                    print(f"Presentations count: {len(resources.get('presentations', []))}")
                                    if resources.get('presentations'):
                                        print("Presentations:")
                                        for ppt in resources['presentations']:
                                            print(f"  - {ppt.get('title')} ({ppt.get('filename')})")
                                    print("="*50 + "\n")
                                    
                                    # Show dynamic overview
                                    overview = create_course_overview(resources, course_data['name'], len(course_data.get('quizzes', [])))
                                    print("OVERVIEW MENU:")
                                    print(overview)
                                    print("="*50)
                                    
                                    response_text = overview
                                    return twiml_message(overview)
                                else:
                                    # Enrollment didn't stick
                                    response_text = localize(
                                        phone,
                                        f"⚠️ *ENROLLMENT PENDING*\n\n"
                                        f"Enrollment in '{course_data['name']}' was submitted but not yet confirmed.\n\n"
                                        f"This can happen if:\n"
                                        f"• Moodle is processing your request\n"
                                        f"• There's a delay in the system\n\n"
                                        f"Please wait a few minutes and check 'My Enrolled Courses' again.",
                                        f"⚠️ *OKWEGATTA KUKYALI KULINDIRWA*\n\n"
                                        f"Okwegatta ku '{course_data['name']}' kwasindikiddwa naye tekunnakakasibwa.\n\n"
                                        f"Kino kiyinza okubaawo singa:\n"
                                        f"• Moodle ekyakola ku kusaba kwo\n"
                                        f"• Waliwo okulwawo mu sisitemu\n\n"
                                        f"Lindako katono oddemu olabe 'Amasomo Gange Ge Nnegattako'."
                                    )
                                    user_state[phone] = "browse_courses"
                                    
                            except Exception as e:
                                print(f"Failed to verify enrollment: {e}")
                                response_text = localize(
                                    phone,
                                    f"⚠️ *ENROLLMENT SUBMITTED*\n\n"
                                    f"Enrollment in '{course_data['name']}' was submitted.\n\n"
                                    f"Please check 'My Enrolled Courses' in a few moments to confirm.",
                                    f"⚠️ *OKWEGATTA KWASINDIKIDDWA*\n\n"
                                    f"Okwegatta ku '{course_data['name']}' kwasindikiddwa.\n\n"
                                    f"Ddamu olabe 'Amasomo Gange Ge Nnegattako' mu kaseera katono okukakasa."
                                )
                                user_state[phone] = "browse_courses"
                            
                        else:
                            # Enrollment API call failed
                            response_text = localize(
                                phone,
                                f"*ENROLLMENT FAILED*\n\n"
                                f"Could not enroll in: {course_data['name']}\n\n"
                                f"This might be because:\n"
                                f"• The course is full\n"
                                f"• Enrollment is restricted\n"
                                f"• Technical error with Moodle\n\n"
                                f"Please try another course or contact support.",
                                f"*OKWEGATTA KULEMYE*\n\n"
                                f"Tetusobodde kukwegatta ku: {course_data['name']}\n\n"
                                f"Kiyinza okuba nga:\n"
                                f"• Essomo lijjudde\n"
                                f"• Okwegatta kukugiddwa\n"
                                f"• Wabaddewo ensobi ya Moodle\n\n"
                                f"Gezaako essomo eddala oba otuukirire abayambi."
                            )
                else:
                    # User not logged in - prompt for Moodle login
                    if phone not in user_moodle_data:
                        user_moodle_data[phone] = {}
                    
                    user_moodle_data[phone]['original_intent'] = {
                        'action': 'enroll',
                        'course_id': int(course_id),
                        'course_name': course_data['name']
                    }
                    
                    # Ask for Moodle username
                    user_state[phone] = "moodle_username"
                    response_text = localize(
                        phone,
                        f"🔐 *Moodle Login Required*\n\n"
                        f"To enroll in '{course_data['name']}', you need to login to Moodle.\n\n"
                        "Please enter your Moodle username:",
                        f"🔐 *Okweyingiza ku Moodle Kwetaagisa*\n\n"
                        f"Okweegatta ku '{course_data['name']}', olina okusooka okweyingiza ku Moodle.\n\n"
                        "Wandiika erinnya lyo ery'okweyingiza ku Moodle:"
                    )   
            
            elif user_msg == "9":
                # Back to course selection
                user_state[phone] = "browse_courses"
                response_text = localize(phone, "↩️ Returning to browse courses...", "↩️ Okudda ku kulaba amasomo...")
                
            elif user_msg in ["0", "menu"]:
                user_state[phone] = "main_menu"
                response_text = main_menu_text(phone)
                
            elif user_msg == "#":
                response_text = goodbye_text(phone)
                user_state.pop(phone, None)
                clear_session_language(phone)
                
            else:
                response_text = localize(
                    phone,
                    "Please select 1 to enroll or use navigation options.\n\n💡 *Navigation:*\n0️⃣ Main Menu • 9️⃣ Back to Browse • #️⃣ Exit",
                    "Londa 1 okweegatta oba kozesa navigation options.\n\n💡 *Navigation:*\n0️⃣ Main Menu • 9️⃣ Ddayo ku Kulaba Amasomo • #️⃣ Mala"
                )
            
            return twiml_message(response_text)

    # ====== FALLBACK FOR UNKNOWN SESSION STATES ======
    user_state[phone] = "main_menu"
    return twiml_message(
        localize(phone, "⚠️ Session state was reset.\n\n", "⚠️ Embeera ya session ezziddwawo.\n\n") + main_menu_text(phone)
    )
# Additional WhatsApp endpoints
@router.get("/status")
async def whatsapp_status():
    """Check WhatsApp service status"""
    return {"status": "active", "service": "whatsapp"}

@router.get("/info")
async def whatsapp_info():
    """WhatsApp service information"""
    return {
        "service": "whatsapp",
        "description": "WhatsApp chatbot for MoH E-Learning Assistant",
        "endpoints": {
            "webhook": "/whatsapp/",
            "status": "/whatsapp/status",
            "documents": "/whatsapp/documents/{id}/download",
            "serve-video": "/whatsapp/serve-video"
        }
    }
@router.post("/teacher-reply")
async def teacher_reply_webhook(Body: str = Form(default=""), From: str = Form(default="")):
    """Webhook for teachers to reply to learner questions"""
    raw_msg = (Body or "").strip()
    teacher_phone = normalize_phone_key(From or "")
    
    if not raw_msg:
        return twiml_message()
    
    # Handle reply command
    if raw_msg.startswith("/reply"):
        parts = raw_msg.split(" ", 2)
        if len(parts) >= 3:
            question_id = parts[1]
            reply = parts[2]
            
            # Get question data
            pending_questions = user_moodle_data.get('pending_questions', {})
            question_data = pending_questions.get(question_id)
            
            if not question_data or question_data.get('status') != 'pending':
                response_text = f"❌ Question {question_id} not found or already answered"
                return twiml_message(response_text)
            
            learner_phone = question_data['learner_phone']
            course_name = question_data['course_name']
            original_question = question_data['question']
            
            # Send reply to learner
            message = (
                f"👨‍🏫 *Response from Teacher*\n\n"
                f"📚 Course: {course_name}\n"
                f"❓ Your Question: {original_question}\n\n"
                f"💬 Response:\n{reply}\n\n"
                f"Reply 5️⃣ to ask another question, or 0️⃣ for main menu."
            )
            
            await _send_whatsapp_message(learner_phone, message)
            
            # Update question status
            question_data['status'] = 'answered'
            question_data['teacher_reply'] = reply
            question_data['replied_at'] = datetime.now().isoformat()
            question_data['teacher_phone'] = teacher_phone
            
            response_text = f"✅ Reply sent to learner for question {question_id}"
        else:
            response_text = "❌ Use: /reply [question_id] [your answer]\n\nExample: /reply Q12345 Thank you for your question..."
        
        return twiml_message(response_text)
    
    # Show help for teachers
    response_text = (
        "👨‍🏫 *Teacher Commands*\n\n"
        "To reply to a learner's question:\n"
        "/reply [question_id] [your answer]\n\n"
        "Example:\n"
        "/reply Q12345 Thank you for your question about infection prevention..."
    )
    return twiml_message(response_text)

# Startup optimization
@router.on_event("startup")
async def startup_event():
    """Pre-load courses on startup for instant response"""
    await get_available_courses_async()
    start_preload_worker()
    if WHATSAPP_ASYNC_QA and _twilio_ready():
        for _ in range(max(1, WHATSAPP_OUTBOUND_WORKERS)):
            asyncio.create_task(_outbound_worker())


@router.on_event("shutdown")
async def shutdown_event():
    await close_async_client()

# Keep backward compatibility - export app if needed for direct usage
app = FastAPI(title="WhatsApp Chat")
app.include_router(router, prefix="/webhook") 

# For static files if needed
app.mount("/uploads", StaticFiles(directory="storage/uploads"), name="uploads")
app.mount("/storage/uploads", StaticFiles(directory="storage/uploads"), name="storage_uploads")
