
from fastapi import FastAPI, Form, Response
from twilio.twiml.messaging_response import MessagingResponse
from app.health_courses import courses 
from app.services.retrieval import answer_question
from app.schemas import ChatRequest
from app.config import get_settings
from app.services.document_store import DocumentStore
app = FastAPI() 

user_state = {}
settings = get_settings()
document_store = DocumentStore(settings.chroma_path)

def escape_xml(text: str) -> str:
    """Escape special characters for XML"""
    return (text.replace('&', '&amp;')
               .replace('<', '&lt;')
               .replace('>', '&gt;')
               .replace('"', '&quot;')
               .replace("'", '&apos;'))

def is_youtube_url(url: str) -> bool:
    """Check if the URL is a YouTube link"""
    youtube_domains = ['youtube.com', 'youtu.be', 'www.youtube.com', 'm.youtube.com']
    return any(domain in url for domain in youtube_domains)

def create_smart_video_response(video_urls, course_name):
    """Create organized response with separate sections for direct videos and YouTube"""
    print(f"🎬 Creating smart video response for: {course_name}")
    
    if not video_urls:
        response_text = "❌ No videos available for this course."
        escaped_text = escape_xml(response_text)
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
    
    # Separate YouTube links and direct videos
    youtube_links = [url for url in video_urls if is_youtube_url(url)]
    direct_videos = [url for url in video_urls if not is_youtube_url(url)]
    messages_xml = []
    # Send direct videos first (playable in WhatsApp)
    if direct_videos:
        videos_message = f"🎥 {course_name} - Videos (Playable in WhatsApp):"
        messages_xml.append(f'''<Message>
        <Body>{escape_xml(videos_message)}</Body>
    </Message>''')
        
        for i, video_url in enumerate(direct_videos):
            escaped_url = escape_xml(video_url)
            caption = f"Video {i+1}"
            message_xml = f'''<Message>
        <Body>{escape_xml(caption)}</Body>
        <Media>{escaped_url}</Media>
    </Message>'''
            messages_xml.append(message_xml)
    
    # Send YouTube links as clickable text
    if youtube_links:
        youtube_message = f"📺 {course_name} - YouTube Videos:\n\n"
        youtube_message += "\n".join([f"▶️ Video {i+1}: {link}" for i, link in enumerate(youtube_links)])
        youtube_message += "\n\nClick any YouTube link to watch in the YouTube app."
        
        message_xml = f'''<Message>
        <Body>{escape_xml(youtube_message)}</Body>
    </Message>'''
        messages_xml.append(message_xml)
    
    if messages_xml:
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
{"".join(messages_xml)}
</Response>'''
    else:
        response_text = "❌ No valid video URLs found."
        escaped_text = escape_xml(response_text)
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'

def process_question(question: str, course_context: str = None):
    """Process question using your existing document Q&A system"""
    try:
        # Add course context if provided
        if course_context:
            contextual_question = f"{question} [Course: {course_context}]"
        else:
            contextual_question = question
            
        # Create chat request
        chat_request = ChatRequest(question=contextual_question)
        
        # Get answer from your AI system
        chat_response = answer_question(chat_request)
        ai_answer = chat_response.answer
        
        # Format response with citations if available
        if hasattr(chat_response, 'citations') and chat_response.citations:
            citations_text = "\n\n📚 Sources: " + ", ".join([f"Doc {i+1}" for i in range(len(chat_response.citations))])
            return f"🤖 {ai_answer}{citations_text}"
        else:
            return f"🤖 {ai_answer}"
            
    except Exception as e:
        return (
            "⚠️ Sorry, I'm having trouble accessing the knowledge base right now. "
            "Please try again later or contact support."
        )

@app.post("/")  
async def whatsapp_reply(Body: str = Form(...), From: str = Form(...)):
    user_msg = Body.strip().lower()
    phone = From
    # Step 1: First contact
    if phone not in user_state:
        user_state[phone] = "main_menu"
        response_text = (
            "👋 Hello! Welcome to the MoH E-Learning Assistant.\n\n"
            "Please choose an action:\n"
            "1️⃣ Enroll in a course\n"
            "2️⃣ View available courses\n"
            "3️⃣ Ask Questions (Document Q&A)\n"
            "4️⃣ Exit"
        )
        escaped_text = escape_xml(response_text)
        raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
        return Response(content=raw_xml, media_type="application/xml")

    # Step 2: Main Menu with Natural Language Support
    if user_state[phone] == "main_menu":
        if user_msg in ["1", "2", "3", "4"]:
            # Handle numeric options
            if user_msg in ["1", "2"]:
                user_state[phone] = "choose_course"
                course_list = "\n".join([f"{k}. {v['name']}" for k, v in courses.items()])
                response_text = f"📚 Please select a course:\n\n{course_list}"
            elif user_msg == "3":
                user_state[phone] = "question_mode"
                response_text = (
                    "🤖 Document Q&A Mode Activated!\n\n"
                    "You can now ask questions about your uploaded documents.\n"
                    "Examples:\n"
                    "• 'What are the key infection prevention techniques?'\n" 
                    "• 'Explain waste management procedures'\n"
                    "• 'Summarize the safety guidelines'\n\n"
                    "Type your question or 'back' to return to main menu."
                )
            elif user_msg == "4":
                response_text = "👋 Goodbye! You can message anytime to continue learning."
                user_state.pop(phone, None)
        elif "course" in user_msg or "enroll" in user_msg:
            user_state[phone] = "choose_course"
            course_list = "\n".join([f"{k}. {v['name']}" for k, v in courses.items()])
            response_text = f"📚 Please select a course:\n\n{course_list}"
        elif any(word in user_msg for word in ['ask', 'question', 'help', 'info', 'what', 'how', 'explain']):
            user_state[phone] = "question_mode"
            response_text = "🤖 Document Q&A Mode Activated! Ask me anything about your documents..."
        elif any(word in user_msg for word in ['exit', 'quit', 'bye', 'goodbye']):
            response_text = "👋 Goodbye! You can message anytime to continue learning."
            user_state.pop(phone, None)
        else:
            # If it's a question-like message, go directly to Q&A
            if '?' in user_msg or any(word in user_msg for word in ['what', 'how', 'why', 'when', 'where']):
                user_state[phone] = "question_mode"
                # Process the question immediately
                answer = process_question(user_msg)
                response_text = f"{answer}\n\n💡 You're now in Q&A mode. Ask another question or type 'back' for main menu."
            else:
                response_text = (
                    "❌ I didn't understand that. Please choose:\n"
                    "1️⃣ Enroll in a course\n"
                    "2️⃣ View available courses\n" 
                    "3️⃣ Ask Questions\n"
                    "4️⃣ Exit"
                )
        
        escaped_text = escape_xml(response_text)
        raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
        return Response(content=raw_xml, media_type="application/xml")

    # Step 3: Choose Course
    if user_state[phone] == "choose_course":
        if user_msg in courses.keys():
            user_state[phone] = f"course_{user_msg}"
            response_text = (
                f"✅ You selected *{courses[user_msg]['name']}*\n\n"
                "Choose content format:\n"
                "1️⃣ PDF\n"
                "2️⃣ Video\n"
                "3️⃣ Ask Questions about this course"
            )
        else:
            response_text = "❌ Invalid course number. Please try again."
        
        escaped_text = escape_xml(response_text)
        raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
        return Response(content=raw_xml, media_type="application/xml")
    
    # Step 4: Course-specific actions
    for course_id in courses.keys():
        if user_state[phone] == f"course_{course_id}":
            if user_msg == "1":
                pdf_links = "\n".join(courses[course_id]["pdfs"])
                response_text = f"📘 PDF Resources:\n{pdf_links}"
                user_state[phone] = "main_menu"
            elif user_msg == "2":
                video_urls = courses[course_id]["videos"]
                course_name = courses[course_id]["name"]                
                raw_xml = create_smart_video_response(video_urls, course_name)
                user_state[phone] = "main_menu"
                return Response(content=raw_xml, media_type="application/xml")
            elif user_msg == "3":
                # Course-specific Q&A
                user_state[phone] = f"course_qa_{course_id}"
                print(f"data-{user_state}")
                course_name = courses[course_id]["name"]
                print(f"course_name-{course_name}")
                response_text = (
                    f"🤖 {course_name} - Question Mode\n\n"
                    f"You can now ask specific questions about {course_name}.\n"
                    "Examples:\n"
                    f"• 'What are the key concepts in {course_name.lower()}?'\n"
                    f"• 'Explain the main procedures for {course_name.lower()}'\n"
                    f"• 'Summarize the important guidelines'\n\n"
                    "Type your question or 'back' to return to course menu."
                )
            else:
                response_text = "❌ Invalid option. Reply 1 for PDF, 2 for Video, or 3 for Q&A"
            
            escaped_text = escape_xml(response_text)
            raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
            return Response(content=raw_xml, media_type="application/xml")

    # Step 5: Question Mode (General Q&A)
    if user_state[phone] == "question_mode":
        if user_msg in ['back', 'menu', 'main menu', '0']:
            user_state[phone] = "main_menu"
            response_text = "↩️ Returning to main menu..."
        else:
            answer = process_question(user_msg)
            response_text = f"{answer}\n\n💡 Ask another question or type 'back' for main menu."
        
        escaped_text = escape_xml(response_text)
        raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
        return Response(content=raw_xml, media_type="application/xml")

    # Step 6: Course-specific Question Mode
    for course_id in courses.keys():
        if user_state[phone] == f"course_qa_{course_id}":
            if user_msg in ['back', 'menu', 'main menu', '0']:
                user_state[phone] = f"course_{course_id}"
                course_name = courses[course_id]["name"]
                response_text = f"↩️ Returning to {course_name} menu..."
            else:
                course_name = courses[course_id]["name"]
                answer = process_question(user_msg, course_name)
                response_text = f"📖 {course_name}\n\n{answer}\n\n💡 Ask another question about this course or type 'back'."
            
            escaped_text = escape_xml(response_text)
            raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
            return Response(content=raw_xml, media_type="application/xml")
    
    # Fallback
    response_text = "❓ I didn't understand that. Please reply with a valid option or 'back' to return to main menu."
    escaped_text = escape_xml(response_text)
    raw_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
    return Response(content=raw_xml, media_type="application/xml")

