import token
from urllib.parse import quote, urlparse, parse_qs, urlencode
import hashlib
import os
import mimetypes
import json
import subprocess
import tempfile
import shutil
import subprocess
from openai import base_url
import requests
from fastapi import APIRouter, Form, Response, HTTPException, Query, Request,FastAPI  
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from app.config import get_settings
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
    clear_courses_cache,
    preload_courses_background,
    normalize_moodle_file_url,
    authenticate_moodle_user,
    get_user_enrolled_courses_moodle,
    get_user_not_enrolled_courses,
    get_course_contents_moodle,
    extract_moodle_resources,
    enroll_user_in_course,
    get_moodle_user_id,
    is_user_enrolled_in_course,
)
from urllib.parse import quote, unquote, urlparse
import urllib3

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
courses_cache_timestamp = 0
CACHE_DURATION = 300  # 5 minutes

# ====== NEW: MOODLE USER AUTHENTICATION STORAGE ======
user_moodle_data = {}  # phone -> {token, userid, username, enrolled_courses, etc}

# Disable SSL warnings for Moodle
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def escape_xml(text: str) -> str:
    return (text.replace('&', '&amp;')
               .replace('<', '&lt;')
               .replace('>', '&gt;')
               .replace('"', '&quot;')
               .replace("'", '&apos;'))


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

def create_pdf_download_response(pdfs, course_name, base_url):
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
        response_text = "No PDFs available for this course (files not found)."
        escaped_text = escape_xml(response_text)
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
    
    # Build response with HEADER MESSAGE FIRST (like the General course)
    messages_xml = []
    
    # HEADER MESSAGE - This is what you want to show first
    header_message = f'''<Message>
        <Body>📚 {escape_xml(course_name)} - Available PDFs ({len(available_pdfs)})</Body>
    </Message>'''
    messages_xml.append(header_message)
    
    # NAVIGATION INSTRUCTIONS - Show this right after header
    nav_message = f'''<Message>
        <Body>💡 Tap any PDF to view it. Use download icon to save.\n\n💡 Navigation:\n0️⃣ Main Menu • 9️⃣ Back to Course • 00️⃣ Exit</Body>
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

def create_smart_video_response(video_urls, course_name, course_id, token, base_url: str = "https://elearning.cadh.africa"):
    """Download videos and serve them DIRECTLY in WhatsApp messages"""

    if not video_urls:
        response_text = "No videos available for this course."
        escaped_text = escape_xml(response_text)
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
    
    messages_xml = []
    
    # Send header message
    header_message = f'''<Message>
        <Body>🎥 {escape_xml(course_name)} - Downloading videos...</Body>
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
        )
    
    # Now send the videos to WhatsApp
    videos_header = f'''<Message>
        <Body>🎥 {escape_xml(course_name)} - Available Videos ({len(downloaded_videos)})</Body>
    </Message>'''
    messages_xml.append(videos_header)
    
    nav_message = f'''<Message>
        <Body>💡 Each video will appear below. Tap to play directly in WhatsApp!\n\n💡 Navigation:\n0️⃣ Main Menu • 9️⃣ Back to Course • 00️⃣ Exit</Body>
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


def create_video_links_response(videos, course_name, note: str = ""):
    """Return direct video URLs as text messages (works even when media delivery fails)."""
    if not videos:
        response_text = "No videos available for this course."
        escaped_text = escape_xml(response_text)
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'

    messages_xml = []

    header_text = f"🔗 {course_name} - Video Links"
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
        messages_xml.append(
            f'''<Message>
            <Body>{escape_xml(f"... and {remaining} more video link(s).")}</Body>
        </Message>'''
        )

    messages_xml.append(
        '''<Message>
        <Body>💡 Open any link in your browser.\n\nNavigation:\n9️⃣ Back • 0️⃣ Main Menu</Body>
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

def create_moodle_pdf_response(pdfs, course_name):
    """Create response for Moodle PDFs"""
    if not pdfs:
        response_text = f"No PDFs available for {course_name}"
        escaped_text = escape_xml(response_text)
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
    
    messages_xml = []
    
    header = f'''<Message>
        <Body>📚 {escape_xml(course_name)} - PDFs ({len(pdfs)})</Body>
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
            <Body>... and {len(pdfs) - 5} more PDFs</Body>
        </Message>'''
        messages_xml.append(remaining)
    
    nav_message = f'''<Message>
        <Body>💡 Tap any PDF to view it in WhatsApp.\n\nNavigation:\n9️⃣ Back • 0️⃣ Main Menu</Body>
    </Message>'''
    messages_xml.append(nav_message)
    
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
{"".join(messages_xml)}
</Response>'''

async def handle_moodle_login_flow(phone, raw_msg):
    state = user_state.get(phone)

    # ===== USERNAME STEP =====
    if state == "moodle_username":
        user_moodle_data.setdefault(phone, {})
        user_moodle_data[phone]["username"] = raw_msg.strip()
        user_state[phone] = "moodle_password"

        response_text = (
            "🔐 *Moodle Login*\n\n"
            "Please enter your Moodle password:"
        )
        escaped_text = escape_xml(response_text)
        raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
        return Response(content=raw_xml, media_type="application/xml")

    # ===== PASSWORD STEP =====
    if state == "moodle_password":
        username = user_moodle_data.get(phone, {}).get("username")
        if not username:
            user_state[phone] = "moodle_username"
            response_text = (
                "🔐 *Login Required*\n\n"
                "Please enter your Moodle username:"
            )
            escaped_text = escape_xml(response_text)
            raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
            return Response(content=raw_xml, media_type="application/xml")
        password = raw_msg  # RAW, NOT lowercased

        auth_result = authenticate_moodle_user(username, password)

        if not auth_result:
            user_state[phone] = "moodle_username"
            response_text = (
                "*Login failed*\n\n"
                "Invalid username or password.\n"
                "Please enter your Moodle username again:"
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
                enrolled_courses = get_user_enrolled_courses_moodle(token, userid)
                user_moodle_data[phone]['enrolled_courses'] = enrolled_courses
                
                if not enrolled_courses:
                    response_text = (
                        "🎓 *Your Enrolled Courses*\n\n"
                        "You are not enrolled in any courses yet.\n\n"
                        "💡 Browse courses (option 1) to enroll in new courses.\n\n"
                        "0️⃣ Main Menu • #️⃣ Exit"
                    )
                else:
                    course_list = "\n".join([f"{i+1}. {course['name']}" for i, course in enumerate(enrolled_courses)])
                    response_text = (
                        "🎓 *Your Enrolled Courses*\n\n"
                        f"{course_list}\n\n"
                        "0️⃣ Main Menu • #️⃣ Exit\n\n"
                        "Select a course number to access:"
                    )
                user_state[phone] = "my_courses"
                
                escaped_text = escape_xml(response_text)
                raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
                return Response(content=raw_xml, media_type="application/xml")
            
            elif intent.get('action') == 'check_enrollment':
                # User wanted to check enrollment for a course they browsed
                course_id = intent['course_id']
                
                # Get course details
                courses = get_available_courses()
                course_data = courses.get(str(course_id), {})
                
                if not course_data:
                    response_text = "Course not found."
                    escaped_text = escape_xml(response_text)
                    raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
                    return Response(content=raw_xml, media_type="application/xml")
                
                # Check enrollment
                token = auth_result['token']
                userid = auth_result['userid']
                is_enrolled = is_user_enrolled_in_course(token, userid, course_id)
                
                # Clear intent
                user_moodle_data[phone].pop('original_intent', None)
                
                if is_enrolled:
                    # User IS enrolled - show course content menu
                    user_state[phone] = f"enrolled_{course_id}"
                    response_text = (
                        f"🎓 *{course_data['name']}*\n\n"
                        f"✅ *Status:* You are already enrolled\n\n"
                        f"📊 *Course Overview:*\n"
                        f"• {len(course_data.get('pdfs', []))} PDF Documents\n"
                        f"• {len(course_data.get('videos', []))} Video Resources\n\n"
                        "What would you like to access?\n"
                        "1️⃣ Study Materials (PDFs)\n"
                        "2️⃣ Video Lessons\n"
                        "3️⃣ Course Overview\n\n"
                        "💡 *Navigation:*\n"
                        "0️⃣ Main Menu • 9️⃣ Back to Browse • #️⃣ Exit"
                    )
                else:
                    # User NOT enrolled - show enroll option
                    user_state[phone] = f"browsing_{course_id}"
                    response_text = (
                        f"📚 *{course_data['name']}*\n\n"
                        f"📊 *Course Overview:*\n"
                        f"• {len(course_data.get('pdfs', []))} PDF Documents\n"
                        f"• {len(course_data.get('videos', []))} Video Resources\n\n"
                        "🔒 *You are NOT enrolled in this course*\n\n"
                        "1️⃣ Enroll in this Course\n\n"
                        "💡 *Navigation:*\n"
                        "0️⃣ Main Menu • 9️⃣ Back to Browse • #️⃣ Exit"
                    )
                
                escaped_text = escape_xml(response_text)
                raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
                return Response(content=raw_xml, media_type="application/xml")
            
            elif intent.get('action') == 'enroll':
                # Handle enrollment (existing code)
                course_id = intent['course_id']
                course_name = intent['course_name']

                enrolled = enroll_user_in_course(
                    token=auth_result['token'],
                    userid=auth_result['userid'],
                    courseid=course_id
                )

                if enrolled:
                    # refresh enrolled courses
                    token = auth_result['token']
                    userid = auth_result['userid']
                    user_moodle_data[phone]['enrolled_courses'] = get_user_enrolled_courses_moodle(token, userid)

                    # clear intent
                    user_moodle_data[phone].pop('original_intent', None)

                    # Set state to enrolled course
                    user_state[phone] = f"enrolled_{course_id}"
                    
                    # Get course data to show content
                    courses = get_available_courses()
                    course_data = courses.get(str(course_id), {})
                    
                    # AUTOMATICALLY SHOW CONTENT MENU
                    response_text = (
                        f"🎉 *Enrollment Successful!*\n\n"
                        f"✅ You are now enrolled in: *{course_name}*\n\n"
                        f"📊 *Course Overview:*\n"
                        f"• {len(course_data.get('pdfs', []))} PDF Documents\n"
                        f"• {len(course_data.get('videos', []))} Video Resources\n\n"
                        "What would you like to access first?\n"
                        "1️⃣ Study Materials (PDFs)\n"
                        "2️⃣ Video Lessons\n"
                        "3️⃣ Course Overview\n\n"
                        "💡 *Navigation:*\n"
                        "0️⃣ Main Menu • 9️⃣ Back to Courses • #️⃣ Exit"
                    )
                    
                    escaped_text = escape_xml(response_text)
                    raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
                    return Response(content=raw_xml, media_type="application/xml")

                else:
                    response_text = "Enrollment failed. Please try again."
                    escaped_text = escape_xml(response_text)
                    raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
                    return Response(content=raw_xml, media_type="application/xml")
        
        # If no intent or intent not handled, go to main menu
        user_state[phone] = "main_menu"
        response_text = (
            f"✅ *Login Successful!*\n\n"
            f"Welcome, *{auth_result['fullname']}* 🎉\n\n"
            "You can now continue enrolling in courses.\n\n"
            "Reply with:\n"
            "1️⃣ Browse Courses\n"
            "2️⃣ My Enrolled Courses\n"
            "0️⃣ Main Menu"
        )
        
        escaped_text = escape_xml(response_text)
        raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
        return Response(content=raw_xml, media_type="application/xml")

    # ===== SAFETY NET =====
    return None


def is_enrolled_live(phone, course_id):
    if phone not in user_moodle_data:
        return False

    token = user_moodle_data[phone].get('token')
    userid = user_moodle_data[phone].get('userid')

    if not token or not userid:
        return False

    return is_user_enrolled_in_course(token, userid, int(course_id))

def main_menu_text():
    return (
        "👋 Welcome back to MoH E-Learning Assistant!\n\n"
        "📚 *Available Actions:*\n"
        "1️⃣ Browse Courses\n"
        "2️⃣ My Enrolled Courses\n"
        "3️⃣ Take a Quiz\n"
        "4️⃣ View Quiz Results\n"
        "5️⃣ Ask Trainer for Help\n"
        "6️⃣ Ask Question Q&A\n\n"
        "0️⃣ Main Menu • #️⃣ Exit"
    )

@router.post("/")  
async def whatsapp_reply(Body: str = Form(...), From: str = Form(...)):
    raw_msg = Body.strip()
    user_msg = raw_msg.lower()
    phone = normalize_phone_key(From)
    base_url = "https://elearning.cadh.africa"
    
    # ====== CHECK FOR MOODLE LOGIN FLOW FIRST ======
    if user_state.get(phone, "") in ["moodle_username", "moodle_password"]:
        login_response = await handle_moodle_login_flow(phone, raw_msg)
        if login_response:
            return login_response 

    # ====== MANUAL CACHE REFRESH ======
    if user_msg in ["refresh", "reload", "sync"]:
        try:
            clear_courses_cache()
            fresh_courses = get_available_courses(force_refresh=True)
            response_text = (
                f"🔄 Course list refreshed.\n\n"
                f"Found {len(fresh_courses)} course(s) from Moodle.\n\n"
                "Reply 1 to browse courses."
            )
        except Exception:
            response_text = "⚠️ Refresh failed. Please try again in a few seconds."

        escaped_text = escape_xml(response_text)
        raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
        return Response(content=raw_xml, media_type="application/xml")
    
    # ====== FIRST CONTACT ======
    if phone not in user_state:
        user_state[phone] = "main_menu"
        response_text = (
            "👋 Hello! Welcome to the MoH E-Learning Assistant!\n\n"
            "📚 *Available Actions:*\n"
            "1️⃣ Browse Courses\n"
            "2️⃣ My Enrolled Courses\n"
            "3️⃣ Take a Quiz\n"
            "4️⃣ View Quiz Results\n"
            "5️⃣ Ask Trainer for Help\n"
            "6️⃣ Ask Question Q&A\n\n"
            "0️⃣ Main Menu • #️⃣ Exit"
        )
        escaped_text = escape_xml(response_text)
        raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
        return Response(content=raw_xml, media_type="application/xml")
    
    # ====== MAIN MENU ======
    if user_state[phone] == "main_menu":
        if user_msg in ["1", "browse"]:
            user_state[phone] = "browse_courses"
            courses = get_available_courses(force_refresh=True)
            course_ids = list(courses.keys())

            if not courses:
                response_text = (
                    "📚 *Browse Courses*\n\n"
                    "Currently no courses are available.\n\n"
                    "0️⃣ Main Menu • #️⃣ Exit"
                )
            else:
                course_list = "\n".join([f"{i+1}. {course['name']}" for i, course in enumerate(courses.values())])
                response_text = (
                    "📚 *Browse Available Courses*\n\n"
                    f"{course_list}\n\n"
                    "0️⃣ Main Menu • #️⃣ Exit\n\n"
                    "Select a course number to view details:"
                )      
                
        elif user_msg in ["2", "enrolled"]:
            # Check if user is logged into Moodle
            if phone in user_moodle_data and 'token' in user_moodle_data[phone]:
                # User is logged in - show their enrolled courses
                token = user_moodle_data[phone]['token']
                userid = user_moodle_data[phone]['userid']
                
                enrolled_courses = get_user_enrolled_courses_moodle(token, userid)
                
                if not enrolled_courses:
                    response_text = (
                        "🎓 *Your Enrolled Courses*\n\n"
                        "You are not enrolled in any courses yet.\n\n"
                        "💡 Browse courses (option 1) to enroll in new courses.\n\n"
                        "0️⃣ Main Menu • #️⃣ Exit"
                    )
                else:
                    course_list = "\n".join([f"{i+1}. {course['name']}" for i, course in enumerate(enrolled_courses)])
                    response_text = (
                        "🎓 *Your Enrolled Courses*\n\n"
                        f"{course_list}\n\n"
                        "0️⃣ Main Menu • #️⃣ Exit\n\n"
                        "Select a course number to access:"
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
                
                response_text = (
                    "🔐 *Login Required*\n\n"
                    "To view your enrolled courses, you need to login first.\n\n"
                    "Please enter your username:"
                )

        elif user_msg in ["3", "quiz"]:
            user_state[phone] = "quiz_selection"
            response_text = (
                "📝 *Quiz Center*\n\n"
                "Available quizzes:\n"
                "1. Infection Prevention Basics\n"
                "2. Safety Procedures\n"
                "3. Emergency Protocols\n\n"
                "0️⃣ Main Menu • #️⃣ Exit\n\n"
                "Select a quiz number to start:"
            )
            
        elif user_msg in ["4", "results"]:
            user_state[phone] = "view_results"
            response_text = (
                "📊 *Your Quiz Results*\n\n"
                "🦠 Infection Prevention: 85%\n"
                "🛡️ Safety Procedures: 92%\n"
                "🚨 Emergency Protocols: 78%\n\n"
                "Overall Performance: Good! 🎉\n\n"
                "0️⃣ Main Menu • 3️⃣ Take New Quiz"
            )
            
        elif user_msg in ["5", "help", "trainer"]:
            user_state[phone] = "ask_trainer"
            response_text = (
                "👨‍🏫 *Trainer Support*\n\n"
                "Need help with a specific topic? Our trainers are here to assist you!\n\n"
                "Please describe what you need help with:\n"
                "• Specific topic confusion\n"
                "• Technical issues\n"
                "• Course content questions\n"
                "• Other learning support\n\n"
                "0️⃣ Main Menu • #️⃣ Exit"
            )
            
        elif user_msg in ["6", "ask", "question"]:
            user_state[phone] = "question_mode"
            
            # Show available course materials for context
            courses = get_available_courses(force_refresh=True)
            if not courses:
                response_text = (
                    "🤖 *Document Q&A*\n\n"
                    "No course materials available yet.\n\n"
                    "Please upload documents first, then ask questions about them.\n\n"
                    "0️⃣ Main Menu • #️⃣ Exit"
                )
            else:
                # Build list of available materials
                materials_list = "📚 *Available Course Materials:*\n\n"
                
                for course_id, course_data in courses.items():
                    materials_list += f"🏷️ *{course_data['name']}*\n"
                    
                    materials_list += "\n"
                
                materials_list += (
                    "💡 *Ask questions about:*\n"
                    "• Specific topics from these materials\n"
                    "0️⃣ Main Menu • #️⃣ Exit"
                )
                
                response_text = materials_list
            
        elif user_msg in ["#", "exit", "quit"]:
            response_text = "👋 Thank you for using MoH E-Learning Assistant!"
            user_state.pop(phone, None)
        else:
            response_text = (
                "Invalid option. Please reply with:\n"
                "1️⃣-6️⃣ for actions or 0️⃣ for main menu"
            )
        
        escaped_text = escape_xml(response_text)
        raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
        return Response(content=raw_xml, media_type="application/xml")

    # ====== MY ENROLLED COURSES HANDLER ======
    if user_state[phone] == "my_courses":
        if user_msg in ["0", "menu", "main menu"]:
            user_state[phone] = "main_menu"
            response_text = (
                "👋 Welcome back to MoH E-Learning Assistant!\n\n"
                "📚 *Available Actions:*\n"
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
            if phone in user_moodle_data and 'token' in user_moodle_data[phone]:
                token = user_moodle_data[phone]['token']
                userid = user_moodle_data[phone]['userid']
                enrolled_courses = get_user_enrolled_courses_moodle(token, userid)
                
                if user_msg.isdigit() and 1 <= int(user_msg) <= len(enrolled_courses):
                    selected_course = enrolled_courses[int(user_msg)-1]
                    course_id = selected_course['id']
                    
                    # Get course details
                    all_courses = get_available_courses()
                    course_data = all_courses.get(str(course_id), {})
                    
                    if course_data:
                        user_state[phone] = f"enrolled_{course_id}"
                        response_text = (
                            f"🎓 *{selected_course['name']}*\n\n"
                            f"📊 *Course Overview:*\n"
                            f"• {len(course_data.get('pdfs', []))} PDF Documents\n"
                            f"• {len(course_data.get('videos', []))} Video Resources\n\n"
                            "What would you like to access?\n"
                            "1️⃣ Study Materials (PDFs)\n"
                            "2️⃣ Video Lessons\n"
                            "3️⃣ Course Overview\n\n"
                            "💡 *Navigation:*\n"
                            "0️⃣ Main Menu • 9️⃣ Back to My Courses • #️⃣ Exit"
                        )
                    else:
                        response_text = (
                            f"Course content not available for: {selected_course['name']}\n\n"
                            "Please try another course or contact support."
                        )
                else:
                    response_text = (
                        "Invalid course number.\n\n"
                        "💡 *Navigation:*\n"
                        "0️⃣ Main Menu • #️⃣ Exit"
                    )
            else:
                response_text = "Please login first to access your courses."
                user_state[phone] = "main_menu"
        
        escaped_text = escape_xml(response_text)
        raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
        return Response(content=raw_xml, media_type="application/xml")

    # ====== BROWSE COURSES HANDLER ======
    if user_state[phone] == "browse_courses":
        if user_msg in ["0", "menu", "main menu"]:
            user_state[phone] = "main_menu"
            response_text = main_menu_text()
        elif user_msg in ["#", "exit"]:
            response_text = "👋 Thank you for using MoH E-Learning Assistant!"
            user_state.pop(phone, None)
        else:
            all_courses = get_available_courses()
            course_keys = list(all_courses.keys())  # these are actual Moodle IDs as strings

            if user_msg.isdigit() and 1 <= int(user_msg) <= len(course_keys):
                selected_course_id = int(course_keys[int(user_msg) - 1])
                selected_course = all_courses[str(selected_course_id)]

                # CHECK IF LOGGED IN
                if phone not in user_moodle_data or 'token' not in user_moodle_data[phone]:
                    # Store original intent so we can continue after login
                    user_moodle_data.setdefault(phone, {})['original_intent'] = {
                        'action': 'check_enrollment',
                        'course_id': selected_course_id
                    }
                    user_state[phone] = "moodle_username"
                    response_text = (
                        f"🔐 *Login Required*\n\n"
                        f"To view '{selected_course['name']}' or enroll, please login first.\n\n"
                        "Enter your username:"
                    )
                else:
                    # Logged in - fetch enrolled courses
                    token = user_moodle_data[phone]['token']
                    userid = user_moodle_data[phone]['userid']
                    enrolled_courses = get_user_enrolled_courses_moodle(token, userid)
                    user_moodle_data[phone]['enrolled_courses'] = enrolled_courses

                    # Check enrollment
                    is_enrolled = any(course['id'] == selected_course_id for course in enrolled_courses)

                    if is_enrolled:
                        user_state[phone] = f"enrolled_{selected_course_id}"
                        response_text = (
                            f"🎓 *{selected_course['name']}*\n\n"
                            f"✅ *Status:* Already enrolled\n\n"
                            f"📊 *Course Overview:*\n"
                            f"• {len(selected_course.get('pdfs', []))} PDFs\n"
                            f"• {len(selected_course.get('videos', []))} Videos\n\n"
                            "What would you like to access?\n"
                            "1️⃣ Study Materials (PDFs)\n"
                            "2️⃣ Video Lessons\n"
                            "3️⃣ Course Overview\n\n"
                            "💡 *Navigation:*\n"
                            "0️⃣ Main Menu • 9️⃣ Back to Browse • #️⃣ Exit"
                        )
                    else:
                        user_state[phone] = f"browsing_{selected_course_id}"
                        response_text = (
                            f"📚 *{selected_course['name']}*\n\n"
                            f"📊 *Course Overview:*\n"
                            f"• {len(selected_course.get('pdfs', []))} PDFs\n"
                            f"• {len(selected_course.get('videos', []))} Videos\n\n"
                            "🔒 *You are NOT enrolled in this course*\n\n"
                            "1️⃣ Enroll in this Course\n\n"
                            "💡 *Navigation:*\n"
                            "0️⃣ Main Menu • 9️⃣ Back to Browse • #️⃣ Exit"
                        )
            else:
                response_text = (
                    "Invalid course number.\n\n"
                    "💡 *Navigation:*\n"
                    "0️⃣ Main Menu • #️⃣ Exit"
                )

        escaped_text = escape_xml(response_text)
        raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
        return Response(content=raw_xml, media_type="application/xml")


    # # ====== ENROLLED COURSE ACTIONS ======
    # for course_id, course_data in get_available_courses().items():
    #     if user_state[phone] == f"enrolled_{course_id}":

    #         # ====== CHECK IF THIS IS A MOODLE-ENROLLED COURSE ======
    #         is_moodle_enrolled = (
    #             phone in user_moodle_data and 
    #             'token' in user_moodle_data[phone] and
    #             any(course['id'] == int(course_id) for course in user_moodle_data[phone].get('enrolled_courses', []))
    #         )
            
    #         if user_msg == "1":
    #             if is_moodle_enrolled:
    #                 # Get Moodle course contents
    #                 token = user_moodle_data[phone]['token']
    #                 contents = get_course_contents_moodle(token, int(course_id))
    #                 resources = extract_moodle_resources(contents, token)
    #                 pdfs = resources.get('pdfs', [])
    #                 course_name = course_data["name"]
                    
    #                 if pdfs:
    #                     raw_xml = create_moodle_pdf_response(pdfs, course_name)
    #                     return Response(content=raw_xml, media_type="application/xml")
    #                 else:
    #                     response_text = "No PDFs available for this Moodle course."
    #             else:
    #                 # Use existing PDF system
    #                 pdfs = course_data["pdfs"]
    #                 course_name = course_data["name"]
    #                 raw_xml = create_pdf_download_response(pdfs, course_name, base_url)
    #                 return Response(content=raw_xml, media_type="application/xml")
                
    #         elif user_msg == "2":
    #             if is_moodle_enrolled:
    #                 # Get Moodle course contents
    #                 token = user_moodle_data[phone]['token']
    #                 contents = get_course_contents_moodle(token, int(course_id))
    #                 resources = extract_moodle_resources(contents, token)
    #                 videos = resources.get('videos', [])
    #                 course_name = course_data["name"]
                    
    #                 if videos:
    #                     response_text = (
    #                         f"🎥 *{course_name} - Videos*\n\n"
    #                         f"Found {len(videos)} video(s).\n\n"
    #                         f"Would you like to:\n"
    #                         f"1️⃣ Get direct links to videos\n"
    #                         f"2️⃣ Download and send videos\n\n"
    #                         f"9️⃣ Back • 0️⃣ Main Menu"
    #                     )
    #                     user_state[phone] = f"moodle_videos_{course_id}"
    #                 else:
    #                     response_text = "No videos available for this Moodle course."
    #             else:
    #                 # Use existing video system
    #                 video_urls = course_data["videos"]
    #                 course_name = course_data["name"] 
    #                 raw_xml = create_smart_video_response(video_urls, course_name, course_id, token, base_url)
    #                 return Response(content=raw_xml, media_type="application/xml")
                
    #         elif user_msg == "3":
    #             response_text = (
    #                 f"📋 *{course_data['name']} - Course Overview*\n\n"
    #                 f"This course contains:\n"
    #                 f"• {len(course_data['pdfs'])} PDF study materials\n"
    #                 f"• {len(course_data['videos'])} video lessons\n\n"
    #                 "Access your materials:\n"
    #                 "1️⃣ Study Materials (PDFs)\n"
    #                 "2️⃣ Video Lessons\n\n"
    #                 "💡 *Navigation:*\n"
    #                 "0️⃣ Main Menu • 9️⃣ Back to My Courses • #️⃣ Exit"
    #             )
                
    #         elif user_msg == "9":
    #             user_state[phone] = "my_courses"
    #             response_text = "↩️ Returning to your enrolled courses..."
                
    #         elif user_msg in ["0", "menu"]:
    #             user_state[phone] = "main_menu"
    #             response_text = (
    #                 "👋 Welcome back to MoH E-Learning Assistant!\n\n"
    #                 "📚 *Available Actions:*\n"
    #                 "1️⃣ Browse Courses\n"
    #                 "2️⃣ My Enrolled Courses\n"
    #                 "3️⃣ Take a Quiz\n"
    #                 "4️⃣ View Quiz Results\n"
    #                 "5️⃣ Ask Trainer for Help\n"
    #                 "6️⃣ Ask Question Q&A\n\n"
    #                 "0️⃣ Main Menu • #️⃣ Exit"
    #             )
                
    #         elif user_msg == "#":
    #             response_text = "👋 Thank you for using MoH E-Learning Assistant!"
    #             user_state.pop(phone, None)
                
    #         else:
    #             response_text = (
    #                 "Please select 1, 2, or 3.\n\n"
    #                 "💡 *Navigation:*\n"
    #                 "0️⃣ Main Menu • 9️⃣ Back to My Courses • #️⃣ Exit"
    #             )
            
    #         escaped_text = escape_xml(response_text)
    #         raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
    #         return Response(content=raw_xml, media_type="application/xml")

        # ====== ENROLLED COURSE ACTIONS ======
    for course_id, course_data in get_available_courses().items():
        if user_state[phone] == f"enrolled_{course_id}":
            # 🎯 FIXED: Check if user is logged in
            if phone not in user_moodle_data or 'token' not in user_moodle_data[phone]:
                response_text = "Please login to access course materials."
                escaped_text = escape_xml(response_text)
                raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
                return Response(content=raw_xml, media_type="application/xml")
            
            # User is logged in - use Moodle system
            token = user_moodle_data[phone]['token']
            
            if user_msg == "1":
                # Get Moodle course contents
                contents = get_course_contents_moodle(token, int(course_id))
                resources = extract_moodle_resources(contents, token)
                pdfs = resources.get('pdfs', [])
                course_name = course_data["name"]
                
                if pdfs:
                    raw_xml = create_moodle_pdf_response(pdfs, course_name)
                    return Response(content=raw_xml, media_type="application/xml")
                else:
                    response_text = "No PDFs available for this course."
                    
            elif user_msg == "2":
                # Get Moodle course contents for videos
                contents = get_course_contents_moodle(token, int(course_id))
                resources = extract_moodle_resources(contents, token)
                videos = resources.get('videos', [])
                course_name = course_data["name"]
                
                if videos:
                    response_text = (
                        f"🎥 *{course_name} - Videos*\n\n"
                        f"Found {len(videos)} video(s).\n\n"
                        f"Would you like to:\n"
                        f"1️⃣ Get direct links to videos\n"
                        f"2️⃣ Download and send videos\n\n"
                        f"9️⃣ Back • 0️⃣ Main Menu"
                    )
                    user_state[phone] = f"moodle_videos_{course_id}"
                else:
                    response_text = "No videos available for this course."
                    
            elif user_msg == "3":
                response_text = (
                    f"📋 *{course_data['name']} - Course Overview*\n\n"
                    f"This course contains:\n"
                    f"• {len(course_data['pdfs'])} PDF study materials\n"
                    f"• {len(course_data['videos'])} video lessons\n\n"
                    "Access your materials:\n"
                    "1️⃣ Study Materials (PDFs)\n"
                    "2️⃣ Video Lessons\n\n"
                    "💡 *Navigation:*\n"
                    "0️⃣ Main Menu • 9️⃣ Back to My Courses • #️⃣ Exit"
                )
                
            elif user_msg == "9":
                if phone in user_moodle_data and 'token' in user_moodle_data[phone]:
                    user_state[phone] = "my_courses"
                    response_text = "↩️ Returning to your enrolled courses..."
                else:
                    user_state[phone] = "browse_courses"
                    response_text = "↩️ Returning to browse courses..."
                    
            elif user_msg in ["0", "menu"]:
                user_state[phone] = "main_menu"
                response_text = (
                    "👋 Welcome back to MoH E-Learning Assistant!\n\n"
                    "📚 *Available Actions:*\n"
                    "1️⃣ Browse Courses\n"
                    "2️⃣ My Enrolled Courses\n"
                    "3️⃣ Take a Quiz\n"
                    "4️⃣ View Quiz Results\n"
                    "5️⃣ Ask Trainer for Help\n"
                    "6️⃣ Ask Question Q&A\n\n"
                    "0️⃣ Main Menu • #️⃣ Exit"
                )
                
            elif user_msg == "#":
                response_text = "👋 Thank you for using MoH E-Learning Assistant!"
                user_state.pop(phone, None)
                
            else:
                response_text = (
                    "Please select 1, 2, or 3.\n\n"
                    "💡 *Navigation:*\n"
                    "0️⃣ Main Menu • 9️⃣ Back to My Courses • #️⃣ Exit"
                )
            
            escaped_text = escape_xml(response_text)
            raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
            return Response(content=raw_xml, media_type="application/xml")
    
    # ====== MOODLE VIDEOS HANDLER ======
    for course_id, course_data in get_available_courses().items():
        if user_state[phone] == f"moodle_videos_{course_id}":
            if user_msg == "1":
                # Get direct links
                token = user_moodle_data[phone]['token']
                contents = get_course_contents_moodle(token, int(course_id))
                resources = extract_moodle_resources(contents, token)
                videos = resources.get('videos', [])
                course_name = course_data["name"]
                
                if not videos:
                    response_text = "No videos available."
                else:
                    raw_xml = create_video_links_response(videos, course_name)
                    return Response(content=raw_xml, media_type="application/xml")
                    
            elif user_msg == "2":
                # Download videos using URLs generated from the logged-in user's token.
                token = user_moodle_data[phone]['token']
                contents = get_course_contents_moodle(token, int(course_id))
                resources = extract_moodle_resources(contents, token)
                video_urls = resources.get('videos', [])
                course_name = course_data["name"]
                if not video_urls:
                    response_text = "No videos available for this course."
                    escaped_text = escape_xml(response_text)
                    raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
                    return Response(content=raw_xml, media_type="application/xml")

                raw_xml = create_smart_video_response(video_urls, course_name, course_id, token, base_url)
                return Response(content=raw_xml, media_type="application/xml")
                
            elif user_msg == "9":
                user_state[phone] = f"enrolled_{course_id}"
                response_text = "↩️ Returning to course options..."
                
            elif user_msg == "0":
                user_state[phone] = "main_menu"
                response_text = "Returning to main menu..."
                
            else:
                response_text = "Please select 1, 2, or 9."
            
            escaped_text = escape_xml(response_text)
            raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
            return Response(content=raw_xml, media_type="application/xml")
    
    # ====== BROWSING SPECIFIC COURSE HANDLER ======
    for course_id, course_data in get_available_courses().items():
        if user_state[phone] == f"browsing_{course_id}":
            base_url = "https://elearning.cadh.africa"
                
            if user_msg == "1":
                # Check if user is logged into Moodle
                if phone in user_moodle_data and 'token' in user_moodle_data[phone]:
                    # User is logged in - try to enroll
                    token = user_moodle_data[phone]['token']
                    userid = user_moodle_data[phone]['userid']
                    
                    # FIRST: Check if already enrolled (to avoid duplicate enrollment)
                    already_enrolled = False
                    try:
                        enrolled_courses = get_user_enrolled_courses_moodle(token, userid)
                        for course in enrolled_courses:
                            if str(course['id']) == str(course_id):
                                already_enrolled = True
                                break
                    except Exception as e:
                        print(f"⚠️ Could not check current enrollments: {e}")
                    
                    if already_enrolled:
                        # User is already enrolled - show course content
                        user_state[phone] = f"enrolled_{course_id}"
                        response_text = (
                            f"ℹ️ *ALREADY ENROLLED*\n\n"
                            f"You are already enrolled in: *{course_data['name']}*\n\n"
                            f"📊 *Course Overview:*\n"
                            f"• {len(course_data.get('pdfs', []))} PDF Documents\n"
                            f"• {len(course_data.get('videos', []))} Video Resources\n\n"
                            "What would you like to access?\n"
                            "1️⃣ Study Materials (PDFs)\n"
                            "2️⃣ Video Lessons\n"
                            "3️⃣ Course Overview\n\n"
                            "💡 *Navigation:*\n"
                            "0️⃣ Main Menu • 9️⃣ Back to Browse • #️⃣ Exit"
                        )
                    else:
                        # Try to enroll
                        success = enroll_user_in_course(token, userid, int(course_id))
                        
                        if success:
                            time.sleep(2)  # Give Moodle time to process
                            if is_enrolled_live(phone, course_id):
                                user_state[phone] = f"enrolled_{course_id}"
                            else:
                                user_state[phone] = "browse_courses"
                            # Verify enrollment by fetching updated course list
                            try:
                                updated_courses = get_user_enrolled_courses_moodle(token, userid)
                                user_moodle_data[phone]['enrolled_courses'] = updated_courses
                                
                                # Verify the course is in the list
                                enrollment_verified = False
                                for course in updated_courses:
                                    if str(course['id']) == str(course_id):
                                        enrollment_verified = True
                                        break
                                
                                if enrollment_verified:
                                    user_state[phone] = f"enrolled_{course_id}"
                                    
                                    response_text = (
                                        f"🎉 *ENROLLMENT SUCCESSFUL!* 🎉\n\n"
                                        f"✅ You are now enrolled in: *{course_data['name']}*\n\n"
                                        f"📊 *Course Overview:*\n"
                                        f"• {len(course_data.get('pdfs', []))} PDF Documents\n"
                                        f"• {len(course_data.get('videos', []))} Video Resources\n\n"
                                        "What would you like to access first?\n"
                                        "1️⃣ Study Materials (PDFs)\n"
                                        "2️⃣ Video Lessons\n"
                                        "3️⃣ Course Overview\n\n"
                                        "💡 *Navigation:*\n"
                                        "0️⃣ Main Menu • 9️⃣ Back to My Courses • #️⃣ Exit"
                                    )
                                else:
                                    # Enrollment didn't stick
                                    response_text = (
                                        f"⚠️ *ENROLLMENT PENDING*\n\n"
                                        f"Enrollment in '{course_data['name']}' was submitted but not yet confirmed.\n\n"
                                        f"This can happen if:\n"
                                        f"• Moodle is processing your request\n"
                                        f"• There's a delay in the system\n\n"
                                        f"Please wait a few minutes and check 'My Enrolled Courses' again."
                                    )
                                    user_state[phone] = "browse_courses"
                                    
                            except Exception as e:
                                print(f"Failed to verify enrollment: {e}")
                                response_text = (
                                    f"⚠️ *ENROLLMENT SUBMITTED*\n\n"
                                    f"Enrollment in '{course_data['name']}' was submitted.\n\n"
                                    f"Please check 'My Enrolled Courses' in a few moments to confirm."
                                )
                                user_state[phone] = "browse_courses"
                            
                        else:
                            # Enrollment API call failed
                            response_text = (
                                f"*ENROLLMENT FAILED*\n\n"
                                f"Could not enroll in: {course_data['name']}\n\n"
                                f"This might be because:\n"
                                f"• The course is full\n"
                                f"• Enrollment is restricted\n"
                                f"• Technical error with Moodle\n\n"
                                f"Please try another course or contact support."
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
                    response_text = (
                        f"🔐 *Moodle Login Required*\n\n"
                        f"To enroll in '{course_data['name']}', you need to login to Moodle.\n\n"
                        "Please enter your Moodle username:"
                    )   
            
            elif user_msg == "9":
                # Back to course selection
                user_state[phone] = "browse_courses"
                response_text = "↩️ Returning to browse courses..."
                
            elif user_msg in ["0", "menu"]:
                user_state[phone] = "main_menu"
                response_text = (
                    "👋 Welcome back to MoH E-Learning Assistant!\n\n"
                    "📚 *Available Actions:*\n"
                    "1️⃣ Browse Courses\n"
                    "2️⃣ My Enrolled Courses\n"
                    "3️⃣ Take a Quiz\n"
                    "4️⃣ View Quiz Results\n"
                    "5️⃣ Ask Trainer for Help\n"
                    "6️⃣ Ask Question Q&A\n\n"
                    "0️⃣ Main Menu • #️⃣ Exit"
                )
                
            elif user_msg == "#":
                response_text = "👋 Thank you for using MoH E-Learning Assistant!"
                user_state.pop(phone, None)
                
            else:
                response_text = (
                    "Please select 3 to enroll or use navigation options.\n\n"
                    "💡 *Navigation:*\n"
                    "0️⃣ Main Menu • 9️⃣ Back to Browse • #️⃣ Exit"
                )
            
            escaped_text = escape_xml(response_text)
            raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
            return Response(content=raw_xml, media_type="application/xml")
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

# Startup optimization
@router.on_event("startup")
async def startup_event():
    """Pre-load courses on startup for instant response"""
    get_available_courses()
    threading.Thread(target=preload_courses_background, daemon=True).start()

# Keep backward compatibility - export app if needed for direct usage
app = FastAPI(title="WhatsApp Chat")
app.include_router(router, prefix="/webhook") 

# For static files if needed
app.mount("/uploads", StaticFiles(directory="storage/uploads"), name="uploads")
app.mount("/storage/uploads", StaticFiles(directory="storage/uploads"), name="storage_uploads")
