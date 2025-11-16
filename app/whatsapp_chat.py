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

user_state = {}
app = FastAPI()
user_state = {}
settings = get_settings()
conversation_history = {}
document_store = DocumentStore(settings.chroma_path)
video_store = VideoStore(settings.chroma_path)

app.mount("/uploads", StaticFiles(directory="storage/uploads"), name="uploads")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def escape_xml(text: str) -> str:
    return (text.replace('&', '&amp;')
               .replace('<', '&lt;')
               .replace('>', '&gt;')
               .replace('"', '&quot;')
               .replace("'", '&apos;'))

def get_document_file_path(document_id: str):
    """Get the actual file path from document_id - ONLY if file exists in storage"""
    try:
        all_docs = document_store.list()
        print(f"🔍 Looking for document_id: {document_id}")
        print(f"🔍 Total documents in database: {len(all_docs)}")
        
        found_doc = None
        available_ids = []
        
        # First, find the document in the database
        for doc in all_docs:
            doc_id = getattr(doc, 'document_id', None)
            filename = getattr(doc, 'filename', 'No filename')
            available_ids.append(f"{doc_id} - {filename}")
            
            if doc_id == document_id:
                found_doc = doc
                print(f"✅ FOUND IN DATABASE: {doc_id} - {filename}")
                break
        
        if not found_doc:
            print(f"❌ Document ID {document_id} not found in database.")
            print(f"📋 Available document IDs: {available_ids}")
            return None, None
        
        # Now check if the file actually exists in storage
        filename = getattr(found_doc, 'filename', 'document.pdf')
        
        # Priority 1: Check existing file path attributes
        existing_paths = [
            getattr(found_doc, 'file_path', None),
            getattr(found_doc, 'path', None),
            getattr(found_doc, 'storage_path', None),
            getattr(found_doc, 'file_location', None),
        ]
        
        # Priority 2: Check common upload directories with the filename
        upload_dirs = [
            "storage/uploads",  # Most likely location
            "uploads",
            "storage",
            "documents", 
            "files",
            "./storage/uploads",
            "./uploads",
            "../storage/uploads",
        ]
        
        # Combine all possible paths to check
        all_possible_paths = []
        
        # Add existing paths from document attributes
        for path in existing_paths:
            if path and path not in all_possible_paths:
                all_possible_paths.append(path)
        
        # Add filename-based paths from upload directories
        for upload_dir in upload_dirs:
            if os.path.exists(upload_dir):
                possible_path = os.path.join(upload_dir, filename)
                if possible_path not in all_possible_paths:
                    all_possible_paths.append(possible_path)
                
                # Also check for UUID-based filenames (common pattern)
                uuid_based_path = os.path.join(upload_dir, f"{document_id}_{filename}")
                if uuid_based_path not in all_possible_paths:
                    all_possible_paths.append(uuid_based_path)
        
        # Check all possible paths for existence
        print(f"🔍 Checking {len(all_possible_paths)} possible file locations...")
        existing_files = []
        
        for file_path in all_possible_paths:
            if file_path and os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                if file_size > 0:  # Ensure it's not an empty file
                    print(f"✅ FOUND EXISTING FILE: {file_path} ({file_size} bytes)")
                    existing_files.append((file_path, file_size))
        
        # Return the first existing file (prioritize by size if multiple found)
        if existing_files:
            # Sort by file size (largest first) to prioritize actual PDFs over small error files
            existing_files.sort(key=lambda x: x[1], reverse=True)
            best_file_path, best_file_size = existing_files[0]
            print(f"✅ USING FILE: {best_file_path} ({best_file_size} bytes)")
            return best_file_path, filename
        
        # No existing file found
        print(f"❌ NO EXISTING FILE FOUND for document: {filename}")
        print(f"📋 Checked {len(all_possible_paths)} locations")
        return None, None
        
    except Exception as e:
        print(f"❌ Error in get_document_file_path: {e}")
        return None, None
    
# @app.get("/debug/documents")
# async def debug_documents():
#     """Debug endpoint to see all stored documents"""
#     try:
#         all_docs = document_store.list()
#         documents_info = []
        
#         for doc in all_docs:
#             doc_info = {
#                 'document_id': getattr(doc, 'document_id', 'No ID'),
#                 'filename': getattr(doc, 'filename', 'No filename'),
#                 'file_path': getattr(doc, 'file_path', 'No path'),
#                 'path': getattr(doc, 'path', 'No path'),
#                 'storage_path': getattr(doc, 'storage_path', 'No path'),
#                 'file_location': getattr(doc, 'file_location', 'No path'),
#                 'course_id': getattr(doc, 'course_id', 'No course'),
#             }
#             documents_info.append(doc_info)
            
#             # Check if file actually exists
#             possible_paths = [
#                 getattr(doc, 'file_path', None),
#                 getattr(doc, 'path', None),
#                 getattr(doc, 'storage_path', None),
#                 getattr(doc, 'file_location', None),
#             ]
            
#             file_exists = False
#             for path in possible_paths:
#                 if path and os.path.exists(path):
#                     doc_info['file_exists'] = True
#                     doc_info['actual_path'] = path
#                     file_exists = True
#                     break
            
#             if not file_exists:
#                 doc_info['file_exists'] = False
#                 # Try uploads directory
#                 filename = getattr(doc, 'filename', None)
#                 if filename:
#                     upload_path = os.path.join("storage/uploads", filename)
#                     if os.path.exists(upload_path):
#                         doc_info['file_exists'] = True
#                         doc_info['actual_path'] = upload_path
        
#         return {
#             "total_documents": len(all_docs),
#             "documents": documents_info
#         }
        
#     except Exception as e:
#         return {"error": str(e)}

def get_available_courses():
    """Get courses from both documents AND videos - FIXED VERSION"""
    all_docs = document_store.list()
    all_videos = video_store.list()
    
    courses = {}
    base_url = "https://5f15b1ed7c02.ngrok-free.app"  # Your ngrok URL
    
    # Process documents (unchanged)
    for doc in all_docs:
        course_id = getattr(doc, 'course_id', None) 
        if not course_id:
            if hasattr(doc, 'filename'):
                if '_' in doc.filename:
                    course_id = doc.filename.split('_')[0]
                elif '-' in doc.filename:
                    course_id = doc.filename.split('-')[0]
                else:
                    course_id = "general"
            else:
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
            courses[course_id]['pdfs'].append({
                'filename': filename,
                'download_url': f"/documents/{doc_id}/download",
                'document_id': doc_id
            })
    
    # Process videos - FIXED: Convert relative URLs to absolute
    for video in all_videos:
        course_id = getattr(video, 'course_id', None)
        if not course_id:
            if hasattr(video, 'title'):
                title = video.title
                if '_' in title:
                    course_id = title.split('_')[0]
                elif '-' in title:
                    course_id = title.split('-')[0]
                else:
                    course_id = "general"
            else:
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
        
        # FIX: Convert relative URLs to absolute URLs
        if existing_url:
            if existing_url.startswith('/'):
                # Convert relative URL to absolute URL
                filename = os.path.basename(existing_url)
                final_url = f"{base_url}/serve-video/{filename}"
                video_type = 'uploaded'
                print(f"🔄 CONVERTED URL: {existing_url} -> {final_url}")
            elif 'youtube.com' in existing_url or 'youtu.be' in existing_url:
                video_type = 'youtube'
                final_url = existing_url
            else:
                video_type = 'direct'
                final_url = existing_url
        elif file_path and os.path.exists(file_path):
            # Fallback: generate URL from file path
            file_path = os.path.normpath(file_path)
            filename = os.path.basename(file_path)
            final_url = f"{base_url}/serve-video/{filename}"
            video_type = 'uploaded'
        
        if final_url and video_type:
            courses[course_id]['videos'].append({
                'url': final_url,  # Now always absolute URL
                'title': video_title,
                'type': video_type,
                'video_id': video_id,
            })
            print(f"✅ VIDEO ADDED: {video_title} -> {final_url}")
    
    return courses

@app.get("/documents/{document_id}/download")
async def download_document(document_id: str):
    """Download PDF document by document_id - ONLY if file exists"""
    try:
        print(f"📄 DOCUMENT DOWNLOAD ENDPOINT CALLED for document_id: {document_id}")
        
        file_path, filename = get_document_file_path(document_id)
        
        if not file_path or not os.path.exists(file_path):
            print(f"❌ Document file not found or doesn't exist: {file_path}")
            raise HTTPException(status_code=404, detail="Document file not found in storage")
        
        # Verify it's a reasonable file size (not an error message)
        file_size = os.path.getsize(file_path)
        if file_size < 1000:  # Less than 1KB is probably an error
            print(f"❌ File too small ({file_size} bytes) - likely an error file")
            raise HTTPException(status_code=404, detail="Document file is invalid")
        
        print(f"✅ Serving document file: {file_path} ({file_size} bytes)")
        
        # Determine content type
        if filename and filename.lower().endswith('.pdf'):
            content_type = "application/pdf"
        elif filename and filename.lower().endswith(('.jpg', '.jpeg')):
            content_type = "image/jpeg"
        elif filename and filename.lower().endswith('.png'):
            content_type = "image/png"
        elif filename and filename.lower().endswith('.docx'):
            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            content_type = "application/octet-stream"
        
        return FileResponse(
            path=file_path,
            media_type=content_type,
            filename=filename,
            headers={
                'Content-Disposition': f'inline; filename="{filename}"',
                'Cache-Control': 'no-cache'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error downloading document: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

def create_pdf_download_response(pdfs, course_name, base_url: str = "https://5f15b1ed7c02.ngrok-free.app"):
    """Create response that sends PDF files directly to WhatsApp"""
    if not pdfs:
        response_text = "❌ No PDFs available for this course."
        escaped_text = escape_xml(response_text)
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
    
    if len(pdfs) == 1:
        pdf = pdfs[0]
        print("Single PDF found:", pdf)
        document_id = pdf.get('document_id')
        
        if document_id:
            file_url = f"{base_url}/documents/{document_id}/download"
            filename = pdf.get('filename', 'document.pdf')
            
            return f'''<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Message>
                    <Body>📄 {course_name} - {filename}</Body>
                    <Media>{escape_xml(file_url)}</Media>
                </Message>
                <Message>
                    <Body>💡 The PDF has been sent. You can:\\n• Tap to view it in WhatsApp\\n• Use the download icon to save it\\n• Share it with others\\n\\n💡 Navigation:\\n0️⃣ Main Menu • 9️⃣ Back to Course • 00️⃣ Exit</Body>
                </Message>
            </Response>'''
                
    messages_xml = []
    messages_xml.append(f'<Message><Body>📚 {course_name} - Available PDFs:</Body></Message>')
    
    for i, pdf in enumerate(pdfs, 1):
        print("Processing PDF:", pdf)
        filename = pdf.get('filename', f'Document {i}')
        document_id = pdf.get('document_id')
        
        if document_id:
            file_url = f"{base_url}/documents/{document_id}/download"
            print("file_url",file_url)
            message_xml = f'''<Message>
        <Body>📄 {filename}</Body>
        <Media>{escape_xml(file_url)}</Media>
    </Message>'''
            messages_xml.append(message_xml)
    
    messages_xml.append('''<Message>
        <Body>💡 Each PDF has been sent separately. Tap any file to view it in WhatsApp or use the download icon to save it.\\n\\n💡 Navigation:\\n0️⃣ Main Menu • 9️⃣ Back to Course • 00️⃣ Exit</Body>
    </Message>''')
    
    return f'''<?xml version="1.0" encoding="UTF-8"?>
    <Response>
    {"".join(messages_xml)}
    </Response>'''

def create_smart_video_response(video_urls, course_name, base_url: str = "https://5f15b1ed7c02.ngrok-free.app"):
    """Create response that sends VIDEO files directly to WhatsApp - URLs are already absolute"""
    if not video_urls:
        response_text = "❌ No videos available for this course."
        escaped_text = escape_xml(response_text)
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
    
    messages_xml = []
    
    # Send the list of videos first
    video_list = "🎥 " + course_name + " - Available Videos:\n\n"
    for i, video in enumerate(video_urls, 1):
        video_list += f"{i}. {video.get('title', f'Video {i}')}\n"
    
    messages_xml.append(f'<Message><Body>{escape_xml(video_list)}</Body></Message>')
    
    print(f"🎬 Creating video response for {len(video_urls)} videos")
    
    # Send each video in a SEPARATE message with proper media
    for i, video in enumerate(video_urls, 1):
        video_title = video.get('title', f'Video {i}')
        video_url = video.get('url', '')
        
        print(f"🎬 Processing video {i}: {video_title}")
        print(f"   URL: {video_url}")  # URL is already absolute
        
        escaped_url = escape_xml(video_url)
        escaped_title = escape_xml(video_title)
        
        # Create SEPARATE message for each video with proper media
        message_xml = f'''<Message>
    <Body>🎥 {escaped_title}</Body>
    <Media>{escaped_url}</Media>
    </Message>'''
        messages_xml.append(message_xml)
        print(f"   ✅ Video {i} added to WhatsApp queue: {video_title}")
    
    # Add navigation message at the end
    messages_xml.append('''<Message>
        <Body>💡 Each video has been sent separately. Tap any video to play it in WhatsApp or use the download icon to save it.\n\n💡 Navigation:\n0️⃣ Main Menu • 9️⃣ Back to Course • 00️⃣ Exit</Body>
    </Message>''')
    
    final_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
    <Response>
    {"".join(messages_xml)}
    </Response>'''
    
    print("🎬 FINAL WHATSAPP XML RESPONSE GENERATED")
    return final_xml

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

@app.post("/")  
async def whatsapp_reply(Body: str = Form(...), From: str = Form(...)):
    print(f"🎯 WEBHOOK HIT - From: {From}, Body: {Body}")
    user_msg = Body.strip().lower()
    phone = From
    
    print(f"📱 Message from {phone}: {user_msg}")

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
            response_text = (
                "🤖 *Document Q&A*\n\n"
                "I can answer questions about your course materials! 📚\n\n"
                "🔍 *I can help with:*\n"
                "• Specific topics from your PDFs\n"
                "• Procedures and guidelines\n" 
                "• Technical concepts\n"
                "• Best practices\n\n"
                "💡 *Try asking:*\n"
                "• \"What are infection prevention techniques?\"\n"
                "• \"How do i test for HIV?\"\n"
                "• \"How is malaria spread?\"\n\n"
                "Ask your question now:\n\n"
                "0️⃣ Main Menu • #️⃣ Exit"
            )
            
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
            print(f"🆘 HELP REQUEST from {phone}: {user_msg}")
            
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
            base_url = "https://5f15b1ed7c02.ngrok-free.app"
            if user_msg == "1":
                pdfs = course_data["pdfs"]
                course_name = course_data["name"]
                raw_xml = create_pdf_download_response(pdfs, course_name, base_url)
                return Response(content=raw_xml, media_type="application/xml")
                
            elif user_msg == "2":
                video_urls = course_data["videos"]
                print("course_data videos",video_urls)
                course_name = course_data["name"] 
                print("course name",course_name)
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

    # Step 9: QUESTION MODE - WITH TYPING INDICATOR SIMULATION
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
            if phone in conversation_history:
                conversation_history.pop(phone)
            response_text = (
                "🤖 *Document Q&A*\n\n"
                "Ask any question about your learning materials:\n\n"
                "💡 Examples:\n"
                "• Infection prevention techniques\n" 
                "• Waste management procedures\n"
                "• Safety guidelines\n"
                "• Emergency protocols\n\n"
                "0️⃣ Main Menu • #️⃣ Exit"
            )
        else:
        # Process the user's question with enhanced typing simulation
            try:
                print(f"🤖 Q&A REQUEST from {phone}: {user_msg}")
                
                # Initialize conversation history
                if phone not in conversation_history:
                    conversation_history[phone] = []
                conversation_history[phone].append(f"User: {user_msg}")
                if len(conversation_history[phone]) > 6:
                    conversation_history[phone] = conversation_history[phone][-6:]
                
                # Send typing simulation messages
                typing_messages = [
                    "💭 _MoH Assistant is thinking..._",
                    "🔍 _Searching through documents..._",
                    "📚 _Analyzing course materials..._"
                ]
                
                # For WhatsApp, we can only return one response per webhook call
                # So we'll combine the typing simulation into one message
                combined_typing = "💭 *MoH Assistant is typing...*\n\n" + "\n".join(typing_messages)
                escaped_typing = escape_xml(combined_typing)
                typing_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_typing}</Message></Response>'
                
                # Process the question
                from app.services.retrieval import answer_question
                from app.schemas import ChatRequest
                
                chat_request = ChatRequest(question=user_msg)
                chat_response = answer_question(chat_request)
                
                # Store response
                conversation_history[phone].append(f"Assistant: {chat_response.answer}")
                
                # Format final response
                if hasattr(chat_response, 'citations') and chat_response.citations:
                    citations_text = "\n\n📚 *Based on:* " + ", ".join([f"{cit.filename}" for cit in chat_response.citations[:2]])
                    if len(chat_response.citations) > 2:
                        citations_text += f" (+{len(chat_response.citations) - 2} more sources)"
                    answer_text = f"✅ *Answer:*\n\n{chat_response.answer}{citations_text}"
                else:
                    answer_text = f"✅ *Answer:*\n\n{chat_response.answer}"
                
                answer_text += "\n\n💡 *What would you like to do next?*\n6️⃣ Ask Another Question • 0️⃣ Main Menu • #️⃣ Exit"
                
                escaped_answer = escape_xml(answer_text)
                response_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_answer}</Message></Response>'
                
                print(f"✅ Q&A RESPONSE sent to {phone}")
                return Response(content=response_xml, media_type="application/xml")
                
            except Exception as e:
                print(f"❌ Q&A Error: {str(e)}")
                error_text = "❌ Sorry, something went wrong. Please try again.\n\n💡 0️⃣ Main Menu • #️⃣ Exit"
                escaped_error = escape_xml(error_text)
                response_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_error}</Message></Response>'
                return Response(content=response_xml, media_type="application/xml")
