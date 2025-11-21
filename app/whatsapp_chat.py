import os
import json
import subprocess
from fastapi import FastAPI, Form, Response, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.config import get_settings
from datetime import datetime 
from app.services.document_store import DocumentStore
from app.services.video_store import VideoStore
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
import functools
import time
import asyncio
from starlette.requests import Request  
import threading


cache_lock = threading.Lock()
user_state = {}
app = FastAPI()
user_state = {}
settings = get_settings()
conversation_history = {}
document_store = DocumentStore(settings.chroma_path)
video_store = VideoStore(settings.chroma_path)
document_path_cache = {}
courses_cache = {}
courses_cache_timestamp = 0
CACHE_DURATION = 300  # 5 minutes

app.mount("/uploads", StaticFiles(directory="storage/uploads"), name="uploads")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/storage/uploads", StaticFiles(directory="storage/uploads"), name="storage_uploads")

def escape_xml(text: str) -> str:
    return (text.replace('&', '&amp;')
               .replace('<', '&lt;')
               .replace('>', '&gt;')
               .replace('"', '&quot;')
               .replace("'", '&apos;'))

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
            # Most likely location - UUID_filename pattern
            f"storage/uploads/{document_id}_{filename}",
            # Direct filename in uploads
            f"storage/uploads/{filename}",
            # Document ID as filename with PDF extension
            f"storage/uploads/{document_id}.pdf",
            f"storage/uploads/{document_id}.PDF",
            # Check document attributes
            getattr(found_doc, 'file_path', None),
            # Check in parent directories
            f"uploads/{filename}",
            f"../storage/uploads/{filename}",
            # Check in chroma directories
            f"storage/chroma/documents/{document_id}_{filename}",
            f"storage/chroma/uploads/{document_id}_{filename}",
            f"storage/chroma/{document_id}_{filename}",
        ]
        
        for path in possible_paths:
            if path and os.path.exists(path) and os.path.isfile(path):
                file_size = os.path.getsize(path)
                if file_size > 100:  # Reduced minimum size
                    result = (path, filename)
                    document_path_cache[document_id] = result
                    print(f"✅ Found PDF file: {path}")
                    return result
        
        # If not found, log all the paths we checked
        print(f"❌ PDF not found for document_id: {document_id}")
        print(f"   Filename: {filename}")
        print(f"   Checked paths: {[p for p in possible_paths if p]}")
        
        document_path_cache[document_id] = (None, filename)
        return None, filename
        
    except Exception as e:
        print(f"❌ Error in get_document_file_path: {e}")
        return None, None

def get_available_courses():
    """Get courses from both documents AND videos - FIXED VERSION"""
    global courses_cache, courses_cache_timestamp
    
    # Return cached version if recent (thread-safe check)
    current_time = time.time()
    with cache_lock:
        if current_time - courses_cache_timestamp < CACHE_DURATION and courses_cache:
            return courses_cache.copy()

    # If cache expired or empty, rebuild it
    all_docs = document_store.list()
    all_videos = video_store.list()
    
    courses = {}
    base_url = "https://f19d4f372e4e.ngrok-free.app"
    
    # Build courses with documents
    for doc in all_docs:
        course_id = getattr(doc, 'course_id', None) 
        if not course_id:
            course_id = "general"
        
        course_name = getattr(doc, 'course_name', None) or f"Course: {course_id.title()}"
        
        if course_id not in courses:
            courses[course_id] = {
                'id': course_id,
                'name': course_name,
                'pdfs': [],
                'videos': []
            }
        
        doc_id = getattr(doc, 'document_id', None)
        filename = getattr(doc, 'filename', 'Unknown Document')
        
        if doc_id:
            file_path, _ = get_document_file_path(doc_id)
            file_exists = file_path and os.path.exists(file_path)
            
            if file_exists:
                courses[course_id]['pdfs'].append({
                    'filename': filename,
                    'download_url': f"/webhook/documents/{doc_id}/download",
                    'document_id': doc_id,
                    'file_exists': True
                })

    # IMPROVED: Process videos - ONLY ADD VIDEOS THAT HAVE WORKING URLs
    for video in all_videos:
        course_id = getattr(video, 'course_id', None)
        if not course_id:
            course_id = "general"
        
        course_name = getattr(video, 'course_name', None) or f"Course: {course_id.title()}"
        
        if course_id not in courses:
            courses[course_id] = {
                'id': course_id,
                'name': course_name,
                'pdfs': [],
                'videos': []
            }
        
        video_id = getattr(video, 'video_id', None)
        video_title = getattr(video, 'title', 'Unknown Video')
        file_path = getattr(video, 'file_path', None)
        existing_url = getattr(video, 'url', None)
        
        final_url = None
        video_type = None
        file_exists = False
        
        # Handle direct URLs first (YouTube, external URLs)
        if existing_url:
            if 'youtube.com' in existing_url or 'youtu.be' in existing_url:
                video_type = 'youtube'
                final_url = existing_url
                file_exists = True  # YouTube URLs always work
                print(f"✅ Added YouTube video: {video_title}")
            else:
                # For other direct URLs, we assume they work
                video_type = 'direct'
                final_url = existing_url
                file_exists = True
                print(f"✅ Added direct URL video: {video_title}")
        
        # Handle uploaded videos with file paths - ONLY IF FILE EXISTS
        elif file_path:
            # Normalize the file path
            file_path = os.path.normpath(file_path)
            filename = os.path.basename(file_path)
            
            # Check if file exists in the stored location
            if os.path.exists(file_path):
                final_url = f"{base_url}/serve-video/{filename}"
                video_type = 'uploaded'
                file_exists = True
                print(f"✅ Added uploaded video (file exists): {video_title} -> {file_path}")
            else:
                # File doesn't exist in stored location, try to find it
                print(f"⚠️ Video file not found at stored path: {file_path}")
                
                # Try to find the file in common locations
                possible_locations = [
                    f"storage/uploads/{filename}",
                    f"storage/chroma/videos/{filename}",
                    f"storage/chroma/documents/{filename}",
                    f"storage/chroma/uploads/{filename}",
                    f"storage/chroma/{filename}",
                    f"uploads/{filename}",
                ]
                
                for location in possible_locations:
                    if os.path.exists(location):
                        final_url = f"{base_url}/serve-video/{filename}"
                        video_type = 'uploaded'
                        file_exists = True
                        print(f"✅ Found video in alternate location: {location}")
                        break
        
        # If we still don't have a URL, try to construct one from video_id - BUT CHECK FILE EXISTS
        if not final_url and video_id:
            # Try common video extensions
            video_extensions = ['.mp4', '.avi', '.mov', '.mkv']
            for ext in video_extensions:
                potential_filenames = [
                    f"{video_id}{ext}",
                    f"{video_id}_{video_title}{ext}" if video_title != 'Unknown Video' else None,
                    f"{video_id}_video{ext}",
                ]
                
                for potential_filename in potential_filenames:
                    if potential_filename:
                        # Check if this file actually exists before creating URL
                        possible_paths = [
                            f"storage/uploads/{potential_filename}",
                            f"storage/chroma/videos/{potential_filename}",
                            f"storage/chroma/documents/{potential_filename}",
                            f"storage/chroma/uploads/{potential_filename}",
                            f"storage/chroma/{potential_filename}",
                            f"uploads/{potential_filename}",
                        ]
                        
                        for check_path in possible_paths:
                            if os.path.exists(check_path):
                                final_url = f"{base_url}/serve-video/{potential_filename}"
                                video_type = 'uploaded'
                                file_exists = True
                                print(f"✅ Found video by constructed filename: {check_path}")
                                break
                        if file_exists:
                            break
                if file_exists:
                    break
        
        # ONLY add the video if we have a valid URL AND the file exists (or it's a direct URL)
        if final_url and video_type and file_exists:
            courses[course_id]['videos'].append({
                'url': final_url,
                'title': video_title,
                'type': video_type,
                'video_id': video_id,
            })
            print(f"✅ FINAL - Added video: {video_title}")
        else:
            print(f"❌ FINAL - Skipping video (no valid URL/file): {video_title} (ID: {video_id})")

    # Update cache thread-safely
    with cache_lock:
        courses_cache = courses
        courses_cache_timestamp = current_time
    
    print(f"📊 Final courses data: {len(courses)} courses")
    for course_id, course_data in courses.items():
        print(f"  - {course_data['name']}: {len(course_data['videos'])} videos, {len(course_data['pdfs'])} PDFs")
    
    return courses

def create_pdf_download_response(pdfs, course_name, base_url):
    """Create PDF response - ONLY SHOW AVAILABLE FILES"""
    # Filter to only include PDFs that actually exist
    available_pdfs = []
    
    for pdf in pdfs:
        document_id = pdf.get('document_id')
        if document_id:
            file_path, _ = get_document_file_path(document_id)
            if file_path and os.path.exists(file_path):
                available_pdfs.append(pdf)
    
    print(f"📊 PDF Response: {len(available_pdfs)} available out of {len(pdfs)} total")
    
    if not available_pdfs:
        response_text = "❌ No PDFs available for this course (files not found)."
        escaped_text = escape_xml(response_text)
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
    
    # If there's only one PDF, send it directly
    if len(available_pdfs) == 1:
        pdf = available_pdfs[0]
        document_id = pdf.get('document_id')
        
        if document_id:
            file_url = f"{base_url}/webhook/documents/{document_id}/download"
            filename = pdf.get('filename', 'document.pdf')
            
            return f'''<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Message>
                    <Body>📄 {escape_xml(course_name)} - {escape_xml(filename)}</Body>
                    <Media>{escape_xml(file_url)}</Media>
                </Message>
            </Response>'''
    
    # Send all available PDFs
    messages_xml = []
    messages_xml.append(f'<Message><Body>📚 {course_name} - Available PDFs ({len(available_pdfs)}):</Body></Message>')
    
    for i, pdf in enumerate(available_pdfs, 1):
        filename = pdf.get('filename', f'Document {i}')
        document_id = pdf.get('document_id')
        
        if document_id:
            file_url = f"{base_url}/webhook/documents/{document_id}/download"
            message_xml = f'''<Message>
                <Body>📄 {filename}</Body>
                <Media>{escape_xml(file_url)}</Media>
            </Message>'''
            messages_xml.append(message_xml)
    
    return f'''<?xml version="1.0" encoding="UTF-8"?>
    <Response>
    {"".join(messages_xml)}
    </Response>'''

@app.get("/documents/{document_id}/download")
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
                        'Cache-Control': 'public, max-age=3600'  # Cache for 1 hour
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
                'Cache-Control': 'public, max-age=3600',  # Browser cache
                'X-Accel-Buffering': 'no'  # For faster streaming
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")

def create_smart_video_response(video_urls, course_name, base_url: str = "https://f19d4f372e4e.ngrok-free.app"):
    """Create response that sends VIDEO files directly to WhatsApp - WITH TITLES BELOW VIDEOS"""
    if not video_urls:
        response_text = "❌ No videos available for this course."
        escaped_text = escape_xml(response_text)
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
    
    messages_xml = []
    
    # Send the list of videos first (optional header)
    video_list = "🎥 " + course_name + " - Available Videos:\n\n"
    for i, video in enumerate(video_urls, 1):
        video_list += f"{i}. {video.get('title', f'Video {i}')}\n"
    
    messages_xml.append(f'<Message><Body>{escape_xml(video_list)}</Body></Message>')
        
    # Send each video in a SEPARATE message with title BELOW the video (like PDFs)
    for i, video in enumerate(video_urls, 1):
        video_title = video.get('title', f'Video {i}')
        video_url = video.get('url', '')
        escaped_url = escape_xml(video_url)
        escaped_title = escape_xml(video_title)
        
        # Create SEPARATE message for each video with Media FIRST, then Body (title below)
        message_xml = f'''<Message>
            <Media>{escaped_url}</Media>
            <Body>🎥 {escaped_title}</Body>
        </Message>'''   
        messages_xml.append(message_xml)

    # Add navigation message at the end
    messages_xml.append('''<Message>
        <Body>💡 Each video has been sent separately. Tap any video to play it in WhatsApp or use the download icon to save it.\n\n💡 Navigation:\n0️⃣ Main Menu • 9️⃣ Back to Course • 00️⃣ Exit</Body>
    </Message>''')
    
    final_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
    <Response>
    {"".join(messages_xml)}
    </Response>'''
    return final_xml


@app.post("/")  
async def whatsapp_reply(Body: str = Form(...), From: str = Form(...)):
    user_msg = Body.strip().lower()
    phone = From
    
    # Step 1: First contact
    if phone not in user_state:
        user_state[phone] = "main_menu"
        response_text = (
            "👋 Hello! Welcome to the MoH E-Learning Assistant!\n\n"
            "📚 *Available Actions:*\n"
            "1️⃣ Enroll in a course\n"
            "2️⃣ Browse available courses\n"
            "3️⃣ Take a Quiz\n"
            "4️⃣ View Quiz Results\n"
            "5️⃣ Ask Trainer for Help\n"
            "6️⃣ Ask Question Q&A\n\n"
            "0️⃣ Main Menu • #️⃣ Exit"
        )
        escaped_text = escape_xml(response_text)
        raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
        return Response(content=raw_xml, media_type="application/xml")

    # Step 2: Main Menu
    if user_state[phone] == "main_menu":
        if user_msg in ["1", "enroll"]:
            user_state[phone] = "enroll_course"
            courses = get_available_courses()
            
            if not courses:
                response_text = (
                    "📚 *Course Enrollment*\n\n"
                    "Currently no courses are available for enrollment.\n\n"
                    "0️⃣ Main Menu • #️⃣ Exit"
                )
            else:
                course_list = "\n".join([f"{i+1}. {course['name']}" for i, course in enumerate(courses.values())])
                response_text = (
                    "📚 *Course Enrollment*\n\n"
                    "Available courses for enrollment:\n\n"
                    f"{course_list}\n\n"
                    "0️⃣ Main Menu • #️⃣ Exit\n\n"
                    "Please select a course number to enroll:"
                )
                
        elif user_msg in ["2", "browse"]:
            user_state[phone] = "browse_courses"
            courses = get_available_courses()
            
            if not courses:
                response_text = "📚 No courses available at the moment.\n\n💡 0️⃣ Main Menu"
            else:
                course_list = "\n".join([f"{i+1}. {course['name']}" for i, course in enumerate(courses.values())])
                response_text = (
                    "📚 *Available Courses*\n\n"
                    f"{course_list}\n\n"
                    "0️⃣ Main Menu • #️⃣ Exit\n\n"
                    "Select a course number to view content:"
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
            courses = get_available_courses()
            if not courses:
                response_text = (
                    "🤖 *Document Q&A*\n\n"
                    "❌ No course materials available yet.\n\n"
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
                "❌ Invalid option. Please reply with:\n"
                "1️⃣-6️⃣ for actions or 0️⃣ for main menu"
            )
        
        escaped_text = escape_xml(response_text)
        raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
        return Response(content=raw_xml, media_type="application/xml")

    # Step 3: ENROLLMENT FLOW
    if user_state[phone] == "enroll_course":
        if user_msg in ["0", "menu", "main menu"]:
            user_state[phone] = "main_menu"
            response_text = (
                "👋 Welcome back to MoH E-Learning Assistant!\n\n"
                "📚 *Available Actions:*\n"
                "1️⃣ Enroll in a course\n"
                "2️⃣ Browse available courses\n"
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
            courses = get_available_courses()
            course_ids = list(courses.keys())
            
            if user_msg.isdigit() and 1 <= int(user_msg) <= len(course_ids):
                selected_course_id = course_ids[int(user_msg)-1]
                selected_course = courses[selected_course_id]
                
                # Store enrollment info
                if 'enrollments' not in user_state:
                    user_state['enrollments'] = {}
                
                user_state['enrollments'][phone] = {
                    'course_id': selected_course_id,
                    'course_name': selected_course['name'],
                    'enrolled_at': datetime.now().isoformat()
                }
                
                user_state[phone] = f"enrolled_{selected_course_id}"
                
                response_text = (
                    f"🎉 *Enrollment Successful!*\n\n"
                    f"✅ You are now enrolled in: *{selected_course['name']}*\n\n"
                    f"📊 *Course Overview:*\n"
                    f"• {len(selected_course['pdfs'])} PDF Documents\n"
                    f"• {len(selected_course['videos'])} Video Resources\n\n"
                    "What would you like to access first?\n"
                    "1️⃣ Study Materials (PDFs)\n"
                    "2️⃣ Video Lessons\n"
                    "3️⃣ Course Overview\n\n"
                    "0️⃣ Main Menu • 9️⃣ Back to Courses • #️⃣ Exit"
                )
            else:
                response_text = (
                    "❌ Invalid course number.\n\n"
                    "💡 *Navigation:*\n"
                    "0️⃣ Main Menu • 9️⃣ Back to Courses • #️⃣ Exit"
                )
        
        escaped_text = escape_xml(response_text)
        raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
        return Response(content=raw_xml, media_type="application/xml")

    # Step 4: QUIZ SELECTION
    if user_state[phone] == "quiz_selection":
        if user_msg in ["0", "menu", "main menu"]:
            user_state[phone] = "main_menu"
            response_text = (
                "👋 Welcome back to MoH E-Learning Assistant!\n\n"
                "📚 *Available Actions:*\n"
                "1️⃣ Enroll in a course\n"
                "2️⃣ Browse available courses\n"
                "3️⃣ Take a Quiz\n"
                "4️⃣ View Quiz Results\n"
                "5️⃣ Ask Trainer for Help\n"
                "6️⃣ Ask Question Q&A\n\n"
                "💡 *Navigation:*\n"
                "0️⃣ Main Menu • #️⃣ Exit"
            )
        elif user_msg in ["#", "exit"]:
            response_text = "👋 Thank you for using MoH E-Learning Assistant!"
            user_state.pop(phone, None)
        elif user_msg in ["1", "2", "3"]:
            quiz_name = {
                "1": "Infection Prevention Basics",
                "2": "Safety Procedures", 
                "3": "Emergency Protocols"
            }.get(user_msg, "General Knowledge")
            
            user_state[phone] = f"quiz_{user_msg}_q1"
            user_state[f'{phone}_quiz_score'] = 0
            user_state[f'{phone}_current_quiz'] = user_msg
            
            response_text = (
                f"📝 *{quiz_name} - Question 1/5*\n\n"
                "What is the first step in proper hand hygiene?\n\n"
                "A) Use hand sanitizer\n"
                "B) Wash with soap and water\n" 
                "C) Wear gloves\n"
                "D) Dry hands with air dryer\n\n"
                "💡 *Navigation:*\n"
                "0️⃣ End Quiz • 9️⃣ Back to Quizzes • #️⃣ Exit"
            )
        else:
            response_text = (
                "❌ Please select quiz 1, 2, or 3.\n\n"
                "💡 *Navigation:*\n"
                "0️⃣ Main Menu • #️⃣ Exit"
            )
        
        escaped_text = escape_xml(response_text)
        raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
        return Response(content=raw_xml, media_type="application/xml")

    # Step 5: QUIZ IN PROGRESS
    if user_state[phone].startswith("quiz_"):
        if user_msg in ["0", "end quiz", "stop"]:
            score = user_state.get(f'{phone}_quiz_score', 0)
            response_text = (
                f"📊 Quiz ended. Your score: {score}/5\n\n"
                "💡 *Navigation:*\n"
                "3️⃣ Take Another Quiz • 0️⃣ Main Menu"
            )
            user_state[phone] = "main_menu"
        elif user_msg == "9":
            user_state[phone] = "quiz_selection"
            response_text = "↩️ Returning to quiz selection..."
        elif user_msg == "#":
            response_text = "👋 Thank you for using MoH E-Learning Assistant!"
            user_state.pop(phone, None)
        else:
            # Handle quiz answers
            current_quiz = user_state.get(f'{phone}_current_quiz', '1')
            current_question = user_state[phone].split('_')[-1]
            
            if user_msg.upper() in ['A', 'B', 'C', 'D']:
                # Process quiz logic here
                response_text = (
                    f"📝 Question 2/5\n\n"
                    "Which PPE is essential for droplet precautions?\n\n"
                    "A) N95 mask\nB) Surgical mask\nC) Face shield\nD) Gloves only\n\n"
                    "💡 *Navigation:*\n"
                    "0️⃣ End Quiz • 9️⃣ Back to Quizzes • #️⃣ Exit"
                )
            else:
                response_text = (
                    "❌ Please select A, B, C, or D as your answer.\n\n"
                    "💡 *Navigation:*\n"
                    "0️⃣ End Quiz • 9️⃣ Back to Quizzes • #️⃣ Exit"
                )
        
        escaped_text = escape_xml(response_text)
        raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
        return Response(content=raw_xml, media_type="application/xml")

    # Step 6: TRAINER SUPPORT
    if user_state[phone] == "ask_trainer":
        if user_msg in ["0", "menu", "main menu"]:
            user_state[phone] = "main_menu"
            response_text = (
                "👋 Welcome back to MoH E-Learning Assistant!\n\n"
                "📚 *Available Actions:*\n"
                "1️⃣ Enroll in a course\n"
                "2️⃣ Browse available courses\n"
                "3️⃣ Take a Quiz\n"
                "4️⃣ View Quiz Results\n"
                "5️⃣ Ask Trainer for Help\n"
                "6️⃣ Ask Question Q&A\n\n"
                "💡 *Navigation:*\n"
                "0️⃣ Main Menu • #️⃣ Exit"
            )
        elif user_msg in ["#", "exit"]:
            response_text = "👋 Thank you for using MoH E-Learning Assistant!"
            user_state.pop(phone, None)
        else:
            # Store help request            
            response_text = (
                "✅ *Help Request Received!*\n\n"
                "Our training team has been notified and will contact you shortly.\n\n"
                "📞 You can also call: +256 XXX XXX XXX\n"
                "📧 Email: trainer@moh.gov.ug\n\n"
                "💡 *Navigation:*\n"
                "0️⃣ Main Menu • 6️⃣ Ask AI • #️⃣ Exit"
            )
            user_state[phone] = "main_menu"
        
        escaped_text = escape_xml(response_text)
        raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
        return Response(content=raw_xml, media_type="application/xml")

    # Step 7: ENROLLED COURSE ACTIONS
    for course_id, course_data in get_available_courses().items():
        if user_state[phone] == f"enrolled_{course_id}":
            base_url = "https://f19d4f372e4e.ngrok-free.app"
            if user_msg == "1":
                pdfs = course_data["pdfs"]
                course_name = course_data["name"]
                raw_xml = create_pdf_download_response(pdfs, course_name, base_url)
                return Response(content=raw_xml, media_type="application/xml")
                
            elif user_msg == "2":
                video_urls = course_data["videos"]
                course_name = course_data["name"] 
                raw_xml = create_smart_video_response(video_urls, course_name,base_url)
                return Response(content=raw_xml, media_type="application/xml")
                
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
                    "0️⃣ Main Menu • 9️⃣ Back to Courses • #️⃣ Exit"
                )
                
            elif user_msg == "9":
                user_state[phone] = "enroll_course"
                response_text = "↩️ Returning to course selection..."
                
            elif user_msg in ["0", "menu"]:
                user_state[phone] = "main_menu"
                response_text = (
                    "👋 Welcome back to MoH E-Learning Assistant!\n\n"
                    "📚 *Available Actions:*\n"
                    "1️⃣ Enroll in a course\n"
                    "2️⃣ Browse available courses\n"
                    "3️⃣ Take a Quiz\n"
                    "4️⃣ View Quiz Results\n"
                    "5️⃣ Ask Trainer for Help\n"
                    "6️⃣ Ask Question Q&A\n\n"
                    "💡 *Navigation:*\n"
                    "0️⃣ Main Menu • #️⃣ Exit"
                )
                
            elif user_msg == "#":
                response_text = "👋 Thank you for using MoH E-Learning Assistant!"
                user_state.pop(phone, None)
                
            else:
                response_text = (
                    "❌ Please select 1, 2, or 3.\n\n"
                    "💡 *Navigation:*\n"
                    "0️⃣ Main Menu • 9️⃣ Back to Courses • #️⃣ Exit"
                )
            
            escaped_text = escape_xml(response_text)
            raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
            return Response(content=raw_xml, media_type="application/xml")

    # Step 8: BROWSE COURSES
    if user_state[phone] == "browse_courses":
        if user_msg in ["0", "menu", "main menu"]:
            user_state[phone] = "main_menu"
            response_text = (
                "👋 Welcome back to MoH E-Learning Assistant!\n\n"
                "📚 *Available Actions:*\n"
                "1️⃣ Enroll in a course\n"
                "2️⃣ Browse available courses\n"
                "3️⃣ Take a Quiz\n"
                "4️⃣ View Quiz Results\n"
                "5️⃣ Ask Trainer for Help\n"
                "6️⃣ Ask Question Q&A\n\n"
                "💡 *Navigation:*\n"
                "0️⃣ Main Menu • #️⃣ Exit"
            )
        elif user_msg in ["#", "exit"]:
            response_text = "👋 Thank you for using MoH E-Learning Assistant!"
            user_state.pop(phone, None)
        else:
            courses = get_available_courses()
            course_ids = list(courses.keys())
            
            if user_msg.isdigit() and 1 <= int(user_msg) <= len(course_ids):
                selected_course_id = course_ids[int(user_msg)-1]
                selected_course = courses[selected_course_id]
                user_state[phone] = f"browsing_{selected_course_id}"
                
                response_text = (
                    f"📖 *{selected_course['name']}*\n\n"
                    f"📊 *Course Preview:*\n"
                    f"• {len(selected_course['pdfs'])} PDF Documents\n"
                    f"• {len(selected_course['videos'])} Video Resources\n\n"
                    "Choose an option:\n"
                    "1️⃣ View PDF Materials\n"
                    "2️⃣ Watch Video Lessons\n"
                    "3️⃣ Enroll in this Course\n\n"
                    "💡 *Navigation:*\n"
                    "0️⃣ Main Menu • 9️⃣ Back to Courses • #️⃣ Exit"
                )
            else:
                response_text = (
                    "❌ Invalid course number.\n\n"
                    "💡 *Navigation:*\n"
                    "0️⃣ Main Menu • #️⃣ Exit"
                )
        
        escaped_text = escape_xml(response_text)
        raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
        return Response(content=raw_xml, media_type="application/xml")

   # Step 9: QUESTION MODE - IMPROVED VERSION
    if user_state[phone] == "question_mode":
        if user_msg in ["0", "menu", "main menu"]:
            user_state[phone] = "main_menu"
            if phone in conversation_history:
                conversation_history.pop(phone)
            response_text = (
                "👋 Welcome back to MoH E-Learning Assistant!\n\n"
                "📚 *Available Actions:*\n"
                "1️⃣ Enroll in a course\n"
                "2️⃣ Browse available courses\n"
                "3️⃣ Take a Quiz\n"
                "4️⃣ View Quiz Results\n"
                "5️⃣ Ask Trainer for Help\n"
                "6️⃣ Ask Question \n\n"
                "💡 *Navigation:*\n"
                "0️⃣ Main Menu • #️⃣ Exit"
            )
        elif user_msg in ["#", "exit"]:
            response_text = "👋 Thank you for using MoH E-Learning Assistant!"
            if phone in conversation_history:
                conversation_history.pop(phone)
            user_state.pop(phone, None)
        elif user_msg in ["6", "ask", "question", "another"]:
            # Reset conversation for new question
            if phone in conversation_history:
                conversation_history.pop(phone)
            
            # Show simplified materials list
            courses = get_available_courses()
            if not courses:
                response_text = (
                    "🤖 *Document Q&A*\n\n"
                    "❌ No course materials available yet.\n\n"
                    "Please upload documents first.\n\n"
                    "0️⃣ Main Menu • #️⃣ Exit"
                )
            else:
                response_text = (
                    "🤖 *Document Q&A*\n\n"
                    "💡 I can answer questions about your course materials.\n\n"
                    "📚 *Available Topics:*\n"
                    "• IPC Software Requirements\n"
                    "• Infection Prevention\n" 
                    "• Safety Procedures\n"
                    "• And more...\n\n"
                    "🔍 *Ask me anything like:*\n"
                    "• \"What are the software requirements?\"\n"
                    "• \"Explain infection prevention\"\n"
                    "• \"Tell me about safety procedures\"\n\n"
                    "Type your question now:\n\n"
                    "0️⃣ Main Menu • #️⃣ Exit"
                )
        
        else:
            # PROCESS USER'S QUESTION - IMPROVED VERSION
            try:                
                # Initialize conversation history
                if phone not in conversation_history:
                    conversation_history[phone] = []
                
                # Send immediate processing message
                processing_text = "💭 *Searching through course materials...*"
                escaped_processing = escape_xml(processing_text)
                processing_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_processing}</Message></Response>'
                
                # Process the question with BETTER query handling
                from app.services.retrieval import answer_question
                from app.schemas import ChatRequest
                
                # Create a more flexible query
                chat_request = ChatRequest(question=user_msg)
                chat_response = answer_question(chat_request)
                
                # Store conversation
                conversation_history[phone].append(f"User: {user_msg}")
                conversation_history[phone].append(f"Assistant: {chat_response.answer}")
                if len(conversation_history[phone]) > 6:
                    conversation_history[phone] = conversation_history[phone][-6:]
                
                # IMPROVED RESPONSE HANDLING
                answer = chat_response.answer
                
                # Check for empty or generic "not found" responses
                if not answer or any(phrase in answer.lower() for phrase in [
                    "could not find", "not find", "no information", "not available", 
                    "i don't know", "i cannot", "no specific information"
                ]):
                    # Provide more helpful guidance
                    answer_text = (
                        "🔍 *I couldn't find exact matches for your question.*\n\n"
                        "💡 *Try these approaches:*\n"
                        "• Ask about specific topics in your materials\n"
                        "• Use simpler, more direct questions\n"
                        "• Check the main topics in your course documents\n"
                        "• Ask about: software requirements, procedures, guidelines\n\n"
                        "📚 *Available materials include:* IPC Software Requirements\n\n"
                        "6️⃣ Ask Another Question • 0️⃣ Main Menu • #️⃣ Exit"
                    )
                else:
                    # Format successful response
                    if hasattr(chat_response, 'citations') and chat_response.citations:
                        unique_sources = list(set([cit.filename for cit in chat_response.citations]))
                        citations_text = "\n\n📚 *Source: " + ", ".join(unique_sources[:2]) + "*"
                        if len(unique_sources) > 2:
                            citations_text += f" (+{len(unique_sources) - 2} more)"
                    else:
                        citations_text = "\n\n📚 *From course materials*"
                    
                    answer_text = f"🤖 *Answer:*\n\n{answer}{citations_text}\n\n💡 6️⃣ Ask Another Question • 0️⃣ Main Menu • #️⃣ Exit"
                
                escaped_answer = escape_xml(answer_text)
                response_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_answer}</Message></Response>'
                return Response(content=response_xml, media_type="application/xml")
                
            except Exception as e:
                print(f"❌ Q&A Error: {str(e)}")
                # More user-friendly error message
                error_text = (
                    "❌ *I'm having trouble accessing the knowledge base right now.*\n\n"
                    "💡 *Please try:*\n"
                    "• Asking again in a moment\n"
                    "• Using different wording\n"
                    "• Contacting support if this continues\n\n"
                    "0️⃣ Main Menu • #️⃣ Exit"
                )
                escaped_error = escape_xml(error_text)
                response_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_error}</Message></Response>'
                return Response(content=response_xml, media_type="application/xml")
            

async def background_cache_refresh():
    """Periodically refresh document cache"""
    while True:
        await asyncio.sleep(300) 
        all_docs = document_store.list()
        for doc in all_docs:
            doc_id = getattr(doc, 'document_id', None)
            if doc_id:
                get_document_file_path(doc_id)

@app.on_event("startup")
async def startup_event():
    """Startup optimizations"""
    all_docs = document_store.list()
    for doc in all_docs:
        doc_id = getattr(doc, 'document_id', None)
        if doc_id:
            get_document_file_path(doc_id)
    
    # Start background cache refresh
    asyncio.create_task(background_cache_refresh())
    
@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    """Add cache headers and monitor performance"""
    start_time = time.time()
    response = await call_next(request)
    
    # Add performance header
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    
    # Cache headers for static resources
    if "/documents/" in str(request.url):
        response.headers["Cache-Control"] = "public, max-age=3600"
    
    return response

@app.post("/cache/reset")
async def reset_cache():
    """Manually reset all caches"""
    global courses_cache, courses_cache_timestamp, document_path_cache
    
    with cache_lock:
        courses_cache = {}
        courses_cache_timestamp = 0
        document_path_cache.clear()
    
    return {
        "message": "All caches reset successfully",
        "courses_cache_cleared": True,
        "document_path_cache_cleared": True,
        "cache_sizes": {
            "courses_cache": 0,
            "document_path_cache": 0
        }
    }