from dotenv import load_dotenv
import os
from pathlib import Path
import requests
import threading
import time
from datetime import datetime
import asyncio
import httpx
import urllib.parse
import json
from urllib.parse import urlparse, parse_qs, urlencode
import urllib3
load_dotenv()
# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_last_course_sync_error = None


cache_lock = threading.Lock()
courses_cache = {}   
CACHE_DURATION = 300 
courses_cache_timestamp = 0
MOODLE_BASE_URL = os.getenv("MOODLE_BASE_URL")
MOODLE_TOKEN = os.getenv("MOODLE_TOKEN")
MOODLE_HTTP_MAX_CONN = int(os.getenv("MOODLE_HTTP_MAX_CONN", "100"))
MOODLE_HTTP_KEEPALIVE = int(os.getenv("MOODLE_HTTP_KEEPALIVE", "20"))
MOODLE_HTTP_TIMEOUT = float(os.getenv("MOODLE_HTTP_TIMEOUT", "15"))

_async_client = None
_async_client_lock = asyncio.Lock()


async def _get_async_client() -> httpx.AsyncClient:
    global _async_client
    if _async_client is None:
        async with _async_client_lock:
            if _async_client is None:
                limits = httpx.Limits(
                    max_connections=MOODLE_HTTP_MAX_CONN,
                    max_keepalive_connections=MOODLE_HTTP_KEEPALIVE,
                )
                _async_client = httpx.AsyncClient(
                    verify=False,
                    timeout=MOODLE_HTTP_TIMEOUT,
                    limits=limits,
                )
    return _async_client


async def close_async_client():
    global _async_client
    if _async_client is not None:
        await _async_client.aclose()
        _async_client = None


def _set_last_course_sync_error(code: str, message: str):
    global _last_course_sync_error
    with cache_lock:
        _last_course_sync_error = {
            "code": code,
            "message": message,
            "timestamp": time.time(),
        }


def _clear_last_course_sync_error():
    global _last_course_sync_error
    with cache_lock:
        _last_course_sync_error = None


def get_last_course_sync_error():
    with cache_lock:
        if not _last_course_sync_error:
            return None
        return _last_course_sync_error.copy()

def get_moodle_courses():
    """Fetch courses from Moodle API"""
    url = f"{MOODLE_BASE_URL}/webservice/rest/server.php"
    # print("fetching courses from:", url)
    parameters = {
        "wstoken": MOODLE_TOKEN,
        "wsfunction": "core_course_get_courses",
        "moodlewsrestformat": "json"
    }
    try:
        response = requests.get(url, params=parameters)
        response.raise_for_status()
        courses = response.json()
        
        if isinstance(courses, dict) and courses.get('exception'):
            print(f"Moodle API error: {courses.get('message', 'Unknown error')}")
            return {}
        
        courses_dict = {}
        for course in courses:
            course_id = str(course.get('id'))
            courses_dict[course_id] = {
                'id': course_id,
                'name': course.get('fullname', 'Unnamed Course'),
                'shortname': course.get('shortname', ''),
                'summary': course.get('summary', ''),
                'categoryid': course.get('categoryid', ''),
            }
        
        return courses_dict  
    
    except requests.exceptions.RequestException as e:
        _set_last_course_sync_error("network_error", str(e))
        print(f"❌ Network error fetching Moodle courses: {e}")
        return {}
    except ValueError as e:
        _set_last_course_sync_error("json_error", str(e))
        print(f"❌ JSON parsing error from Moodle API: {e}")
        return {}
    except Exception as e:
        _set_last_course_sync_error("unexpected_error", str(e))
        print(f"❌ Unexpected error fetching Moodle courses: {e}")
        return {}


async def get_moodle_courses_async():
    """Fetch courses from Moodle API (async)."""
    url = f"{MOODLE_BASE_URL}/webservice/rest/server.php"
    parameters = {
        "wstoken": MOODLE_TOKEN,
        "wsfunction": "core_course_get_courses",
        "moodlewsrestformat": "json"
    }
    try:
        client = await _get_async_client()
        response = await client.get(url, params=parameters)
        response.raise_for_status()
        courses = response.json()

        if isinstance(courses, dict) and courses.get('exception'):
            print(f"Moodle API error: {courses.get('message', 'Unknown error')}")
            return {}

        courses_dict = {}
        for course in courses:
            course_id = str(course.get('id'))
            courses_dict[course_id] = {
                'id': course_id,
                'name': course.get('fullname', 'Unnamed Course'),
                'shortname': course.get('shortname', ''),
                'summary': course.get('summary', ''),
                'categoryid': course.get('categoryid', ''),
            }

        return courses_dict

    except httpx.RequestError as e:
        _set_last_course_sync_error("network_error", str(e))
        print(f"❌ Network error fetching Moodle courses: {e}")
        return {}
    except ValueError as e:
        _set_last_course_sync_error("json_error", str(e))
        print(f"❌ JSON parsing error from Moodle API: {e}")
        return {}
    except Exception as e:
        _set_last_course_sync_error("unexpected_error", str(e))
        print(f"❌ Unexpected error fetching Moodle courses: {e}")
        return {}

def get_moodle_course_contents(course_id: str):
    """Fetch course contents from Moodle API with proper error handling"""
    url = f"{MOODLE_BASE_URL}/webservice/rest/server.php"
    params = {
        "wstoken": MOODLE_TOKEN,
        "wsfunction": "core_course_get_contents",
        "courseid": course_id,
        "moodlewsrestformat": "json",
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        
        # Check if request was successful
        if response.status_code != 200:
            error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
            print(f"❌ API error: {error_msg}")
            return {"course_id": course_id, "sections": [], "error": error_msg}
        
        # Try to parse JSON
        try:
            sections_data = response.json()
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON response: {str(e)}"
            print(f"❌ {error_msg}")
            print(f"Response text: {response.text[:200]}")
            return {"course_id": course_id, "sections": [], "error": error_msg}
        
        # Check if we got an error from Moodle
        if isinstance(sections_data, dict) and sections_data.get('exception'):
            error_msg = f"Moodle API error: {sections_data.get('message', 'Unknown error')}"
            print(f"❌ {error_msg}")
            return {"course_id": course_id, "sections": [], "error": error_msg}
        
        # Process the data
        sections = []
        for section in sections_data:
            section_obj = {
                "id": section.get("id"),
                "name": section.get("name") or "Untitled Section",
                "videos": [],
                "pdfs": [],
                "powerpoints": [],
                "quizzes": [],
            }

            for module in section.get("modules", []):
                module_name = module.get("name", "Untitled")
                module_type = module.get("modname")
                module_cmid = module.get("id")

                if module_type == "quiz":
                    quiz_obj = {
                        "title": module_name,
                        "cmid": module_cmid,
                        "course_id": course_id,
                        "instance": module.get("instance"),
                        "url": module.get("url")
                    }
                    section_obj["quizzes"].append(quiz_obj)

                for content in module.get("contents", []):
                    file_url = content.get("fileurl")
                    mimetype = content.get("mimetype")
                    filename = content.get("filename")

                    if not file_url or not mimetype:
                        continue

                    file_obj = {
                        "title": module_name,
                        "filename": filename,
                        "url": file_url,
                        "mimetype": mimetype,
                        "cmid": module_cmid,
                        "course_id": course_id,
                    }

                    if mimetype.startswith("video/"):
                        section_obj["videos"].append(file_obj)
                    elif mimetype == "application/pdf":
                        section_obj["pdfs"].append(file_obj)
                    elif any(ppt in mimetype for ppt in [
                        "powerpoint", 
                        "presentation",
                        "vnd.ms-powerpoint",
                        "vnd.openxmlformats-officedocument.presentationml"
                    ]):
                        section_obj["powerpoints"].append(file_obj)

            sections.append(section_obj)

        return {"course_id": course_id, "sections": sections}

    except requests.exceptions.RequestException as e:
        error_msg = f"Network error: {str(e)}"
        print(f"❌ {error_msg}")
        return {"course_id": course_id, "sections": [], "error": error_msg}
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        return {"course_id": course_id, "sections": [], "error": error_msg}


async def get_moodle_course_contents_async(course_id: str):
    """Fetch course contents from Moodle API with proper error handling (async)."""
    url = f"{MOODLE_BASE_URL}/webservice/rest/server.php"
    params = {
        "wstoken": MOODLE_TOKEN,
        "wsfunction": "core_course_get_contents",
        "courseid": course_id,
        "moodlewsrestformat": "json",
    }

    try:
        client = await _get_async_client()
        response = await client.get(url, params=params, timeout=30)

        if response.status_code != 200:
            error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
            print(f"❌ API error: {error_msg}")
            return {"course_id": course_id, "sections": [], "error": error_msg}

        try:
            sections_data = response.json()
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON response: {str(e)}"
            print(f"❌ {error_msg}")
            print(f"Response text: {response.text[:200]}")
            return {"course_id": course_id, "sections": [], "error": error_msg}

        if isinstance(sections_data, dict) and sections_data.get('exception'):
            error_msg = f"Moodle API error: {sections_data.get('message', 'Unknown error')}"
            print(f"❌ {error_msg}")
            return {"course_id": course_id, "sections": [], "error": error_msg}

        sections = []
        for section in sections_data:
            section_obj = {
                "id": section.get("id"),
                "name": section.get("name") or "Untitled Section",
                "videos": [],
                "pdfs": [],
                "powerpoints": [],
                "quizzes": [],
            }

            for module in section.get("modules", []):
                module_name = module.get("name", "Untitled")
                module_type = module.get("modname")
                module_cmid = module.get("id")

                if module_type == "quiz":
                    quiz_obj = {
                        "title": module_name,
                        "cmid": module_cmid,
                        "course_id": course_id,
                        "instance": module.get("instance"),
                        "url": module.get("url")
                    }
                    section_obj["quizzes"].append(quiz_obj)

                for content in module.get("contents", []):
                    file_url = content.get("fileurl")
                    mimetype = content.get("mimetype")
                    filename = content.get("filename")

                    if not file_url or not mimetype:
                        continue

                    file_obj = {
                        "title": module_name,
                        "filename": filename,
                        "url": file_url,
                        "mimetype": mimetype,
                        "cmid": module_cmid,
                        "course_id": course_id,
                    }

                    if mimetype.startswith("video/"):
                        section_obj["videos"].append(file_obj)
                    elif mimetype == "application/pdf":
                        section_obj["pdfs"].append(file_obj)
                    elif any(ppt in mimetype for ppt in [
                        "powerpoint",
                        "presentation",
                        "vnd.ms-powerpoint",
                        "vnd.openxmlformats-officedocument.presentationml"
                    ]):
                        section_obj["powerpoints"].append(file_obj)

            sections.append(section_obj)

        return {"course_id": course_id, "sections": sections}

    except httpx.RequestError as e:
        error_msg = f"Network error: {str(e)}"
        print(f"❌ {error_msg}")
        return {"course_id": course_id, "sections": [], "error": error_msg}
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        return {"course_id": course_id, "sections": [], "error": error_msg}

def preload_courses_background():
    """Preload all courses and contents every CACHE_DURATION seconds."""
    global courses_cache, courses_cache_timestamp

    while True:
        print("⏳ Preloading Moodle courses in background...")
        try:
            courses = get_available_courses()  # fetch full courses with contents
            with cache_lock:
                courses_cache = courses
                courses_cache_timestamp = time.time()
            print(f"✅ Preloaded {len(courses_cache)} courses at {time.ctime()}")
        except Exception as e:
            print(f"❌ Error preloading courses: {e}")
        time.sleep(CACHE_DURATION)

def get_available_courses(force_refresh=False):
    """Return Moodle courses with full content, using cache if available.
    
    Args:
        force_refresh: If True, bypass cache and fetch fresh data from Moodle
    """
    global courses_cache, courses_cache_timestamp

    current_time = time.time()
    
    # Check cache if not forcing refresh
    if not force_refresh:
        with cache_lock:
            if courses_cache and (current_time - courses_cache_timestamp < CACHE_DURATION):
                return courses_cache.copy()

    # Force refresh or cache expired - fetch from Moodle
    moodle_courses = get_moodle_courses()
    courses = {}
    for course_id, course in moodle_courses.items():
        try:
            contents = get_moodle_course_contents(course_id)
            # Aggregate resources
            course_pdfs = []
            course_videos = []
            course_powerpoints = []
            course_quizzes = []

            for section in contents["sections"]:
                course_pdfs.extend(section.get("pdfs", []))
                course_videos.extend(section.get("videos", []))
                course_powerpoints.extend(section.get("powerpoints", []))
                course_quizzes.extend(section.get("quizzes", []))

            courses[course_id] = {
                "id": course_id,
                "name": course["name"],
                "pdfs": course_pdfs,
                "videos": course_videos,
                "powerpoints": course_powerpoints,
                "sections": contents["sections"],
                "quizzes": course_quizzes,

            }
        except Exception as e:
            print(f"❌ Failed to load course {course['name']}: {e}")

    # Update cache
    with cache_lock:
        courses_cache = courses
        courses_cache_timestamp = current_time

    return courses


async def get_available_courses_async(force_refresh: bool = False):
    """Return Moodle courses with full content, using cache if available (async)."""
    global courses_cache, courses_cache_timestamp

    current_time = time.time()

    if not force_refresh:
        with cache_lock:
            if courses_cache and (current_time - courses_cache_timestamp < CACHE_DURATION):
                return courses_cache.copy()

    moodle_courses = await get_moodle_courses_async()
    courses: dict = {}

    concurrency = int(os.getenv("MOODLE_CONTENTS_CONCURRENCY", "5"))
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def build_course(course_id, course):
        async with semaphore:
            try:
                contents = await get_moodle_course_contents_async(course_id)
                course_pdfs = []
                course_videos = []
                course_powerpoints = []
                course_quizzes = []

                for section in contents.get("sections", []):
                    course_pdfs.extend(section.get("pdfs", []))
                    course_videos.extend(section.get("videos", []))
                    course_powerpoints.extend(section.get("powerpoints", []))
                    course_quizzes.extend(section.get("quizzes", []))

                return course_id, {
                    "id": course_id,
                    "name": course["name"],
                    "pdfs": course_pdfs,
                    "videos": course_videos,
                    "powerpoints": course_powerpoints,
                    "sections": contents.get("sections", []),
                    "quizzes": course_quizzes,
                }
            except Exception as e:
                print(f"❌ Failed to load course {course.get('name', course_id)}: {e}")
                return None

    tasks = [build_course(course_id, course) for course_id, course in moodle_courses.items()]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    for item in results:
        if not item:
            continue
        course_id, course_data = item
        courses[course_id] = course_data

    with cache_lock:
        courses_cache = courses
        courses_cache_timestamp = current_time

    return courses

def ensure_course_videos_downloaded(course_id):
    """Download all videos for a course and return local paths"""
    courses = get_available_courses()
    course = courses.get(str(course_id))
    if not course:
        return []
    
    local_videos = []
    for video in course['videos']:
        # Only download videos that have a URL
        if video.get('url'):
            local_path = download_video_to_server(video, course_id)
            if local_path:
                # Add local path to video data
                video['local_path'] = local_path
                local_videos.append(video)
    
    return local_videos

def download_video_to_server(video_data, course_id):
    """
    Download Moodle video using webservice/pluginfile.php (CORRECT & FINAL)
    """
    try:
        videos_dir = Path("storage/uploads/videos")
        videos_dir.mkdir(parents=True, exist_ok=True)

        # ✅ NORMALIZE URL (THIS WAS MISSING)
        file_url = normalize_moodle_file_url(video_data["url"])
        filename = video_data["filename"]
        module_cmid = video_data["cmid"]

        safe_filename = f"{course_id}_{module_cmid}_{filename}"
        local_path = videos_dir / safe_filename

        if local_path.exists() and local_path.stat().st_size > 1_000_000:
            print("✅ Already downloaded:", local_path)
            return str(local_path)

        response = requests.get(
            file_url,
            stream=True,
            timeout=60,
            verify=False
        )

        if response.status_code != 200:
            print("❌ HTTP error:", response.status_code)
            return None

        content_type = response.headers.get("content-type", "")
        if "video" not in content_type:
            response.content[:200]
            return None

        size = 0
        with open(local_path, "wb") as f:
            for chunk in response.iter_content(8192):
                if chunk:
                    f.write(chunk)
                    size += len(chunk)

        if size < 1_000_000:
            local_path.unlink(missing_ok=True)
            return None
        return str(local_path)

    except Exception as e:
        print("❌ Download failed:", e)
        return None

def normalize_moodle_file_url(file_url: str) -> str:
    """
    Convert any Moodle file URL into a WORKING webservice download URL
    """
    from urllib.parse import urlparse, urlencode, parse_qs
    
    parsed = urlparse(file_url)
    
    # Parse existing query parameters
    query_params = parse_qs(parsed.query)
    
    # For Moodle file downloads through pluginfile.php, the parameter should be "token" NOT "wstoken"
    # Add or replace token parameter
    query_params['token'] = [MOODLE_TOKEN]
    
    # Ensure forcedownload is set
    query_params['forcedownload'] = ['1']
    
    # Remove wstoken if it exists (it's wrong for this endpoint)
    query_params.pop('wstoken', None)
    
    # Rebuild the URL
    new_query = urlencode(query_params, doseq=True)
    normalized_url = parsed._replace(query=new_query).geturl()
    return normalized_url

# ====== NEW USER AUTHENTICATION FUNCTIONS ======
def get_moodle_user_id(token: str, username: str):
    """Get Moodle user ID - TESTED & WORKING"""
    try:
        ws_url = f"{MOODLE_BASE_URL}/webservice/rest/server.php"
        params = {
            'wstoken': token,
            'wsfunction': 'core_user_get_users_by_field',
            'field': 'username',
            'values[0]': username,
            'moodlewsrestformat': 'json'
        }
        
        response = requests.post(ws_url, data=params, verify=False, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                return data[0].get('id')
    except Exception as e:
        print(f"❌ Error getting user ID: {e}")
    return None

def get_user_enrolled_courses_moodle(token: str, userid: int):
    """Get user's enrolled courses - MORE ROBUST VERSION"""
    try:
        ws_url = f"{MOODLE_BASE_URL}/webservice/rest/server.php"
        params = {
            'wstoken': token,
            'wsfunction': 'core_enrol_get_users_courses',
            'userid': userid,
            'moodlewsrestformat': 'json'
        }
        
        response = requests.post(ws_url, data=params, verify=False, timeout=15)
        
        if response.status_code == 200:
            courses = response.json()
            
            # Handle different response formats
            if isinstance(courses, list):
                # Simplify course data
                simplified = []
                for course in courses:
                    if isinstance(course, dict):
                        simplified.append({
                            'id': course.get('id'),
                            'name': course.get('fullname', 'Unnamed Course'),
                            'shortname': course.get('shortname', ''),
                            'summary': course.get('summary', '')[:200]
                        })
                return simplified
            elif isinstance(courses, dict) and courses.get('exception'):
                print(f"⚠️ Moodle API error: {courses.get('message')}")
                return []
            else:
                print(f"⚠️ Unexpected response format: {type(courses)}")
                return []
        else:
            print(f"❌ HTTP error: {response.status_code}")
            return []
            
    except Exception as e:
        print(f"❌ Error getting enrolled courses: {e}")
        return []


async def get_user_enrolled_courses_moodle_async(token: str, userid: int):
    """Get user's enrolled courses (async)."""
    try:
        ws_url = f"{MOODLE_BASE_URL}/webservice/rest/server.php"
        params = {
            'wstoken': token,
            'wsfunction': 'core_enrol_get_users_courses',
            'userid': userid,
            'moodlewsrestformat': 'json'
        }

        client = await _get_async_client()
        response = await client.post(ws_url, data=params, timeout=15)

        if response.status_code == 200:
            courses = response.json()
            if isinstance(courses, list):
                simplified = []
                for course in courses:
                    if isinstance(course, dict):
                        simplified.append({
                            'id': course.get('id'),
                            'name': course.get('fullname', 'Unnamed Course'),
                            'shortname': course.get('shortname', ''),
                            'summary': course.get('summary', '')[:200]
                        })
                return simplified
            if isinstance(courses, dict) and courses.get('exception'):
                print(f"⚠️ Moodle API error: {courses.get('message')}")
                return []
            print(f"⚠️ Unexpected response format: {type(courses)}")
            return []

        print(f"❌ HTTP error: {response.status_code}")
        return []

    except Exception as e:
        print(f"❌ Error getting enrolled courses: {e}")
        return []

def get_user_not_enrolled_courses(token: str, userid: int):
    """Get courses user is NOT enrolled in"""
    try:
        # Get all courses
        ws_url = f"{MOODLE_BASE_URL}/webservice/rest/server.php"
        params_all = {
            'wstoken': token,
            'wsfunction': 'core_course_get_courses',
            'moodlewsrestformat': 'json'
        }
        
        response_all = requests.post(ws_url, data=params_all, verify=False, timeout=10)
        if response_all.status_code == 200:
            all_courses = response_all.json()
            
            # Get enrolled courses
            enrolled_courses = get_user_enrolled_courses_moodle(token, userid)
            enrolled_ids = {course['id'] for course in enrolled_courses}
            
            # Filter out enrolled courses
            not_enrolled = []
            for course in all_courses:
                if isinstance(course, dict) and course.get('id') not in enrolled_ids:
                    not_enrolled.append({
                        'id': course.get('id'),
                        'name': course.get('fullname', 'Unnamed Course'),
                        'shortname': course.get('shortname', ''),
                        'summary': course.get('summary', '')[:200]
                    })
            
            return not_enrolled
            
    except Exception as e:
        print(f"❌ Error getting not enrolled courses: {e}")
    return []

def get_course_contents_moodle(token: str, course_id: int):
    """Get all contents from a course - TESTED & WORKING"""
    try:
        ws_url = f"{MOODLE_BASE_URL}/webservice/rest/server.php"
        params = {
            'wstoken': token,
            'wsfunction': 'core_course_get_contents',
            'courseid': course_id,
            'moodlewsrestformat': 'json'
        }
        
        response = requests.post(ws_url, data=params, verify=False, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"❌ Error getting course contents: {e}")
    return []


async def get_course_contents_moodle_async(token: str, course_id: int):
    """Get all contents from a course (async)."""
    try:
        ws_url = f"{MOODLE_BASE_URL}/webservice/rest/server.php"
        params = {
            'wstoken': token,
            'wsfunction': 'core_course_get_contents',
            'courseid': course_id,
            'moodlewsrestformat': 'json'
        }
        client = await _get_async_client()
        response = await client.post(ws_url, data=params, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"❌ Error getting course contents: {e}")
    return []


def extract_moodle_resources(contents, token: str):
    """Extract ALL resources from course contents dynamically"""
    print(f"\n🔍 EXTRACT_MOODLE_RESOURCES - Contents type: {type(contents)}")
    
    resources = {
        'documents': [],  # PDFs, Word docs, etc.
        'presentations': [],  # PowerPoints, Keynote, etc.
        'spreadsheets': [],  # Excel, CSV, etc.
        'images': [],  # JPG, PNG, GIF, etc.
        'audio': [],  # MP3, WAV, etc.
        'videos': [],  # MP4, MOV, etc.
        'archives': [],  # ZIP, RAR, etc.
        'other': []  # Everything else
    }
    
    if not contents:
        print("❌ No contents provided")
        return resources
    
    if not isinstance(contents, list):
        print(f"❌ Contents is not a list: {type(contents)}")
        return resources
    
    print(f"Processing {len(contents)} sections")
    
    for section_idx, section in enumerate(contents):
        print(f"\nSection {section_idx}: {section.get('name', 'Unnamed')}")
        modules = section.get('modules', [])
        print(f"  Modules: {len(modules)}")
        
        for module in modules:
            module_name = module.get('name', 'Unnamed Module')
            contents_list = module.get('contents', [])
            
            for content in contents_list:
                if content.get('type') == 'file':
                    filename = content.get('filename', '')
                    mimetype = content.get('mimetype', '')
                    
                    # Your existing code...
                    # Add token to URL for direct access
                    fileurl = content.get('fileurl', '')
                    if not fileurl:
                        continue
                    
                    parsed = urlparse(fileurl)
                    query_params = parse_qs(parsed.query)
                    query_params['token'] = [token]
                    query_params['forcedownload'] = ['1']
                    
                    new_query = urlencode(query_params, doseq=True)
                    accessible_url = parsed._replace(query=new_query).geturl()
                    
                    # Get file extension
                    file_ext = Path(filename).suffix.lower()
                    
                    # Create file info object
                    file_info = {
                        'title': module_name,
                        'filename': filename,
                        'extension': file_ext,
                        'url': accessible_url,
                        'original_url': fileurl,
                        'size': content.get('filesize', 0),
                        'size_formatted': format_file_size(content.get('filesize', 0)),
                        'type': mimetype,
                        'module_name': module_name,
                        'section_name': section.get('name', 'Unknown Section'),
                        'section_id': section.get('id'),
                        'module_id': module.get('id'),
                        'downloadable': True
                    }
                    
                    # Dynamically categorize based on mimetype and extension
                    category = categorize_file(mimetype, file_ext, filename)
                    
                    # DEBUG: Print when we find a PowerPoint
                    if category == 'presentations':
                        print(f"  ✅ Found presentation: {filename}")
                        print(f"     Module: {module_name}")
                        print(f"     Section: {section.get('name')}")
                    
                    resources[category].append(file_info)
    
    # Final summary
    print(f"\n📊 EXTRACTION SUMMARY:")
    for cat, items in resources.items():
        if items:
            print(f"  {cat}: {len(items)} items")
    
    return resources

def format_file_size(size_bytes):
    """Format file size in human-readable format"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

def categorize_file(mimetype, extension, filename):
    """Dynamically categorize files based on mimetype and extension"""
    filename_lower = filename.lower()
    mimetype_lower = mimetype.lower() if mimetype else ''
    
    # Documents
    if any(ext in filename_lower for ext in ['.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt']) or \
       any(keyword in mimetype_lower for keyword in ['pdf', 'document', 'text']):
        return 'documents'
    
    # Presentations
    if any(ext in filename_lower for ext in ['.ppt', '.pptx', '.key', '.odp']) or \
       any(keyword in mimetype_lower for keyword in ['presentation', 'powerpoint']):
        return 'presentations'
    
    # Spreadsheets
    if any(ext in filename_lower for ext in ['.xls', '.xlsx', '.csv', '.ods']) or \
       any(keyword in mimetype_lower for keyword in ['spreadsheet', 'excel', 'csv']):
        return 'spreadsheets'
    
    # Images
    if any(ext in filename_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp']) or \
       'image' in mimetype_lower:
        return 'images'
    
    # Audio
    if any(ext in filename_lower for ext in ['.mp3', '.wav', '.ogg', '.m4a', '.flac']) or \
       'audio' in mimetype_lower:
        return 'audio'
    
    # Videos
    if any(ext in filename_lower for ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv']) or \
       'video' in mimetype_lower:
        return 'videos'
    
    # Archives
    if any(ext in filename_lower for ext in ['.zip', '.rar', '.7z', '.tar', '.gz']) or \
       any(keyword in mimetype_lower for keyword in ['zip', 'compressed', 'archive']):
        return 'archives'
    
    # Default
    return 'other'

def escape_xml(text: str) -> str:
    """Escape XML special characters for WhatsApp messages"""
    if text is None:
        return ""
    return (str(text).replace('&', '&amp;')
               .replace('<', '&lt;')
               .replace('>', '&gt;')
               .replace('"', '&quot;')
               .replace("'", '&apos;'))

def create_generic_content_response(resources, course_name, category):
    """Create a dynamic response for any content category"""
    
    category_icons = {
        'documents': '📄',
        'presentations': '📊',
        'spreadsheets': '📈',
        'images': '🖼️',
        'audio': '🎵',
        'videos': '🎥',
        'archives': '📦',
        'other': '📁'
    }
    
    category_names = {
        'documents': 'Documents',
        'presentations': 'Presentations',
        'spreadsheets': 'Spreadsheets',
        'images': 'Images',
        'audio': 'Audio Files',
        'videos': 'Videos',
        'archives': 'Archives',
        'other': 'Other Files'
    }
    
    items = resources.get(category, [])
    icon = category_icons.get(category, '📄')
    category_name = category_names.get(category, category.capitalize())
    
    if not items:
        response_text = f"{icon} No {category_name} available for {course_name}"
        escaped_text = escape_xml(response_text)
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped_text}</Message></Response>'
    
    messages_xml = []
    
    # Header
    header = f'''<Message>
        <Body>{icon} *{escape_xml(course_name)} - {category_name}* ({len(items)} total)</Body>
    </Message>'''
    messages_xml.append(header)
    
    # Instructions - ALL files are downloadable
    if category in ['images', 'videos', 'audio']:
        instructions = f'''<Message>
            <Body>💡 Tap any file to play it in WhatsApp. Tap the download icon to save it.</Body>
        </Message>'''
    else:
        instructions = f'''<Message>
            <Body>💡 Tap any file to download it. You'll need a compatible app to open it.</Body>
        </Message>'''
    messages_xml.append(instructions)
    
    # Group by section/module if there are multiple sections
    items_by_section = {}
    for item in items:
        section = item.get('section_name', 'General')
        if section not in items_by_section:
            items_by_section[section] = []
        items_by_section[section].append(item)
    
    # Display items grouped by section
    for section_name, section_items in items_by_section.items():
        if len(items_by_section) > 1:  # Only show section header if multiple sections
            section_header = f'''<Message>
                <Body>📌 *{escape_xml(section_name)}*</Body>
            </Message>'''
            messages_xml.append(section_header)
        
        for i, item in enumerate(section_items[:5], 1):  # Limit to 5 per section
            title = item.get('title', item.get('filename', 'File'))
            size = item.get('size_formatted', '')
            url = item.get('url', '')
            
            # Use Media tag for ALL file types to make them downloadable/playable
            item_message = f'''<Message>
                <Body>{i}. {escape_xml(title)} ({size})</Body>
                <Media>{escape_xml(url)}</Media>
            </Message>'''
            messages_xml.append(item_message)
        
        if len(section_items) > 5:
            more = f'''<Message>
                <Body>... and {len(section_items) - 5} more files in {escape_xml(section_name)}</Body>
            </Message>'''
            messages_xml.append(more)
    
    # Navigation
    nav_message = f'''<Message>
        <Body>💡 *Navigation:*\n9️⃣ Back to Course • 0️⃣ Main Menu</Body>
    </Message>'''
    messages_xml.append(nav_message)
    
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
{"".join(messages_xml)}
</Response>'''

def create_course_overview(resources, course_name, quiz_count=0):
    """Create a dynamic course overview showing all content types"""
    
    # Define categories to display
    categories = [
        ('documents', '📄', 'Documents'),
        ('presentations', '📊', 'Presentations'),
        ('spreadsheets', '📈', 'Spreadsheets'),
        ('images', '🖼️', 'Images'),
        ('audio', '🎵', 'Audio'),
        ('videos', '🎥', 'Videos'),
        ('archives', '📦', 'Archives'),
        ('other', '📁', 'Other')
    ]
    
    overview = f"📋 *{escape_xml(course_name)} - Course Overview*\n\n"
    overview += "📊 *Available Resources:*\n"
    
    total_files = 0
    option_number = 1
    options_text = ""
    
    for category_key, icon, display_name in categories:
        count = len(resources.get(category_key, []))
        if count > 0:
            overview += f"{icon} {display_name}: {count}\n"
            options_text += f"{option_number}️⃣ {display_name}\n"
            option_number += 1
            total_files += count
    
    if quiz_count > 0:
        overview += f"📝 Quizzes: {quiz_count}\n"
    
    overview += f"\n📁 Total Resources: {total_files}\n\n"
    
    if options_text:
        overview += "What would you like to access?\n"
        overview += options_text
    
    if quiz_count > 0:
        overview += f"{option_number}️⃣ Take Quizzes\n"
    
    overview += "\n💡 *Navigation:*\n0️⃣ Main Menu • 9️⃣ Back to My Courses • #️⃣ Exit"
    
    return overview

def enroll_user_in_course(token: str, userid: int, courseid: int):
    """
    Enroll a user in a Moodle course - IMPROVED VERSION
    """
    try:
        # First check if already enrolled
        if is_user_enrolled_in_course(token, userid, courseid):
            return True
        
        # METHOD 1: Try self-enrollment first
        ws_url = f"{MOODLE_BASE_URL}/webservice/rest/server.php"
        params = {
            'wstoken': token,
            'wsfunction': 'enrol_self_enrol_user',
            'moodlewsrestformat': 'json',
            'courseid': courseid,
        }
        
        try:
            response = requests.post(ws_url, data=params, verify=False, timeout=10)            
            if response.status_code == 200:
                data = response.json()
                
                if data is True:
                    return True
                else:
                    # Check error message
                    if isinstance(data, dict) and data.get('warnings'):
                        for warning in data.get('warnings', []):
                            if 'Enrolment is disabled or inactive' in warning.get('message', ''):
                                print(f"   ℹ️ Self-enrollment is disabled for this course")
        except requests.exceptions.Timeout:
            print(f"   ⏱️ Self-enrollment timeout")
        except Exception as e:
            print(f"   ⚠️ Self-enrollment error: {e}")
        
        # METHOD 2: Use admin token for manual enrollment
        success = enroll_user_in_course_admin(userid, courseid)
        
        if success:            
            # Double-check enrollment
            time.sleep(2)
            if is_user_enrolled_in_course(token, userid, courseid):
                print(f"   ✅ VERIFIED: User is now enrolled in course {courseid}")
            else:
                print(f"   ⚠️ Enrollment might need time to propagate in Moodle")
            
            return True
        else:
            print(f"   ❌ Admin enrollment also failed")
            return False
            
    except Exception as e:
        print(f"   ❌ EXCEPTION in enrollment: {e}")
        import traceback
        traceback.print_exc()
        return False


async def enroll_user_in_course_async(token: str, userid: int, courseid: int):
    """
    Enroll a user in a Moodle course (async).
    """
    try:
        if await is_user_enrolled_in_course_async(token, userid, courseid):
            return True

        ws_url = f"{MOODLE_BASE_URL}/webservice/rest/server.php"
        params = {
            'wstoken': token,
            'wsfunction': 'enrol_self_enrol_user',
            'moodlewsrestformat': 'json',
            'courseid': courseid,
        }

        try:
            client = await _get_async_client()
            response = await client.post(ws_url, data=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data is True:
                    return True
                if isinstance(data, dict) and data.get('warnings'):
                    for warning in data.get('warnings', []):
                        if 'Enrolment is disabled or inactive' in warning.get('message', ''):
                            print("   ℹ️ Self-enrollment is disabled for this course")
        except httpx.ReadTimeout:
            print("   ⏱️ Self-enrollment timeout")
        except Exception as e:
            print(f"   ⚠️ Self-enrollment error: {e}")

        # METHOD 2: Use admin token for manual enrollment
        success = await enroll_user_in_course_admin_async(userid, courseid)
        if success:
            await asyncio.sleep(2)
            if await is_user_enrolled_in_course_async(token, userid, courseid):
                print(f"   ✅ VERIFIED: User is now enrolled in course {courseid}")
            else:
                print("   ⚠️ Enrollment might need time to propagate in Moodle")
            return True

        print("   ❌ Admin enrollment also failed")
        return False

    except Exception as e:
        print(f"   ❌ EXCEPTION in enrollment: {e}")
        import traceback
        traceback.print_exc()
        return False


async def enroll_user_in_course_admin_async(userid: int, courseid: int, roleid: int = 5):
    """Enroll a user using ADMIN TOKEN (async)."""
    try:
        ws_url = f"{MOODLE_BASE_URL}/webservice/rest/server.php"
        params = {
            'wstoken': MOODLE_TOKEN,
            'wsfunction': 'enrol_manual_enrol_users',
            'moodlewsrestformat': 'json',
            'enrolments[0][roleid]': roleid,
            'enrolments[0][userid]': userid,
            'enrolments[0][courseid]': courseid,
        }

        client = await _get_async_client()
        response = await client.post(ws_url, data=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data is True or data == []:
                return True
            if isinstance(data, dict) and data.get('exception'):
                print(f"   ❌ Admin enrollment error: {data.get('message')}")
                return False
            return True
        print(f"   ❌ Admin enrollment HTTP error: {response.status_code}")
        return False
    except Exception as e:
        print(f"   ❌ Admin enrollment error: {e}")
        return False

def enroll_user_in_course_admin(userid: int, courseid: int, roleid: int = 5):
    """
    Enroll a user using ADMIN TOKEN (manual enrollment)
    This requires admin privileges and should always work
    """
    try:
        ws_url = f"{MOODLE_BASE_URL}/webservice/rest/server.php"
        params = {
            'wstoken': MOODLE_TOKEN,  # Use the admin token
            'wsfunction': 'enrol_manual_enrol_users',
            'moodlewsrestformat': 'json',
            'enrolments[0][roleid]': roleid,
            'enrolments[0][userid]': userid,
            'enrolments[0][courseid]': courseid,
            'enrolments[0][suspend]': 0,
            'enrolments[0][timestart]': int(time.time()),
            'enrolments[0][timeend]': 0
        }
        
        response = requests.post(ws_url, data=params, verify=False, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            
            # Some Moodle installations return null instead of empty array
            if data == [] or data is None:  # <-- FIXED HERE                
                # Verify enrollment immediately
                time.sleep(1)  # Wait a bit for Moodle to process
                try:
                    enrolled_courses = get_user_enrolled_courses_moodle(MOODLE_TOKEN, userid)
                    course_ids = [course['id'] for course in enrolled_courses]
                    
                    if courseid in course_ids:
                        print(f"      ✅ VERIFIED: User {userid} is enrolled in course {courseid}")
                    else:
                        print(f"      ⚠️ WARNING: Course {courseid} not in enrolled list")
                        print(f"      Enrolled courses: {course_ids}")
                except Exception as e:
                    print(f"      ⚠️ Could not verify enrollment: {e}")
                
                return True
            else:
                print(f"      ❌ ERROR: Moodle returned unexpected data: {data}")
                return False
        else:
            print(f"      ❌ HTTP ERROR: {response.status_code}")
            print(f"      Response text: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"      ❌ ADMIN ENROLLMENT EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return False
    
def clear_courses_cache():
    """Clear the courses cache to force a refresh"""
    global courses_cache, courses_cache_timestamp
    with cache_lock:
        courses_cache = {}
        courses_cache_timestamp = 0
    print("✅ Courses cache cleared")

def start_preload_worker():
    """Start the background preload worker thread"""
    # Check if worker already running
    for thread in threading.enumerate():
        if thread.name == "moodle_preload_worker":
            print("⚠️ Preload worker already running")
            return
    
    # Start new worker thread
    worker_thread = threading.Thread(
        target=preload_courses_background,
        name="moodle_preload_worker",
        daemon=True
    )
    worker_thread.start()
    print("✅ Preload worker started") 
    
def is_user_enrolled_in_course(token: str, userid: int, courseid: int):
    """Check if user is already enrolled in a course"""
    try:
        enrolled_courses = get_user_enrolled_courses_moodle(token, userid)
        course_ids = [course['id'] for course in enrolled_courses]
        return courseid in course_ids
    except Exception as e:
        print(f"❌ Error checking enrollment: {e}")
        return False


async def is_user_enrolled_in_course_async(token: str, userid: int, courseid: int):
    """Check if user is already enrolled in a course (async)."""
    try:
        enrolled_courses = await get_user_enrolled_courses_moodle_async(token, userid)
        course_ids = [course['id'] for course in enrolled_courses]
        return courseid in course_ids
    except Exception as e:
        print(f"❌ Error checking enrollment: {e}")
        return False

def get_course_enrollment_methods(token: str, courseid: int):
    """Get available enrollment methods for a course"""
    try:
        ws_url = f"{MOODLE_BASE_URL}/webservice/rest/server.php"
        params = {
            'wstoken': token,
            'wsfunction': 'core_enrol_get_course_enrolment_methods',
            'courseid': courseid,
            'moodlewsrestformat': 'json'
        }
        
        response = requests.post(ws_url, data=params, verify=False, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"❌ Error getting enrollment methods: {e}")
    return []


def authenticate_moodle_user(username: str, password: str):
    """Authenticate user - SIMPLE & RELIABLE VERSION"""    
    try:
        # 1. Get token
        login_url = f"{MOODLE_BASE_URL}/login/token.php"        
        response = requests.post(
            login_url,
            data={
                'username': username,
                'password': password,
                'service': 'moodle_mobile_app'
            },
            verify=False,  # IMPORTANT: Disable SSL verify
            timeout=15
        )
                
        if response.status_code != 200:
            print(f"   ❌ HTTP error: {response.text[:200]}")
            return None
        
        data = response.json()        
        token = data.get('token')
        if not token:
            print(f"   ❌ No token returned: {data}")
            return None
                
        # 2. Get user ID
        ws_url = f"{MOODLE_BASE_URL}/webservice/rest/server.php"
        params = {
            'wstoken': token,
            'wsfunction': 'core_user_get_users_by_field',
            'field': 'username',
            'values[0]': username,
            'moodlewsrestformat': 'json'
        }
        
        user_response = requests.post(ws_url, data=params, verify=False, timeout=15)
        
        if user_response.status_code == 200:
            user_data = user_response.json()
            
            if isinstance(user_data, list) and len(user_data) > 0:
                user = user_data[0]
                userid = user.get('id')
                
                if not userid:
                    print(f"   ❌ No user ID")
                    return None
                                
                return {
                    'token': token,
                    'userid': userid,
                    'username': username,
                    'fullname': f"{user.get('firstname', '')} {user.get('lastname', '')}".strip(),
                    'email': user.get('email', ''),
                    'authenticated_at': time.time()
                }
        
        print(f"   ❌ Failed to get user info")
        return None
        
    except requests.exceptions.Timeout:
        print(f"   ❌ Timeout connecting to Moodle")
        return None
    except requests.exceptions.ConnectionError:
        print(f"   ❌ Connection error to Moodle")
        return None
    except Exception as e:
        print(f"   ❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return None


async def authenticate_moodle_user_async(username: str, password: str):
    """Authenticate user (async)."""
    try:
        login_url = f"{MOODLE_BASE_URL}/login/token.php"
        client = await _get_async_client()
        response = await client.post(
            login_url,
            data={
                'username': username,
                'password': password,
                'service': 'moodle_mobile_app'
            },
            timeout=15
        )

        if response.status_code != 200:
            print(f"   ❌ HTTP error: {response.text[:200]}")
            return None

        data = response.json()
        token = data.get('token')
        if not token:
            print(f"   ❌ No token returned: {data}")
            return None

        ws_url = f"{MOODLE_BASE_URL}/webservice/rest/server.php"
        params = {
            'wstoken': token,
            'wsfunction': 'core_user_get_users_by_field',
            'field': 'username',
            'values[0]': username,
            'moodlewsrestformat': 'json'
        }

        user_response = await client.post(ws_url, data=params, timeout=15)
        if user_response.status_code == 200:
            user_data = user_response.json()
            if isinstance(user_data, list) and len(user_data) > 0:
                user = user_data[0]
                userid = user.get('id')
                if not userid:
                    print("   ❌ No user ID")
                    return None
                return {
                    'token': token,
                    'userid': userid,
                    'username': username,
                    'fullname': f"{user.get('firstname', '')} {user.get('lastname', '')}".strip(),
                    'email': user.get('email', ''),
                    'authenticated_at': time.time()
                }

        print("   ❌ Failed to get user info")
        return None

    except httpx.ReadTimeout:
        print("   ❌ Timeout connecting to Moodle")
        return None
    except httpx.ConnectError:
        print("   ❌ Connection error to Moodle")
        return None
    except Exception as e:
        print(f"   ❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_course_quizzes(course_id: int):
    """Fetch quizzes for a course"""
    try:
        ws_url = f"{MOODLE_BASE_URL}/webservice/rest/server.php"

        params = {
            "wstoken": MOODLE_TOKEN,
            "wsfunction": "mod_quiz_get_quizzes_by_courses",
            "courseids[0]": course_id,
            "moodlewsrestformat": "json"
        }

        response = requests.post(ws_url, data=params, verify=False, timeout=15)

        if response.status_code == 200:
            data = response.json()

            if isinstance(data, dict) and data.get("quizzes"):
                return data["quizzes"]

        return []

    except Exception as e:
        print(f"❌ Error getting quizzes: {e}")
        return []
    

# Add these imports at the top if not already there

# ====== TEACHER/TRAINER FUNCTIONS ======

async def get_course_teachers_comprehensive_async(token: str, course_id: int) -> list:
    """
    Get all users with ANY teaching-related capability in a course.
    This captures editing teachers, non-editing teachers, and managers.
    """
    # Teaching-related capabilities to check
    teaching_capabilities = [
        'moodle/course:manageactivities',   # Editing teacher
        'moodle/course:update',              # Can update course
        'moodle/grade:manage',               # Can manage grades
        'mod/assign:grade',                  # Can grade assignments
        'moodle/course:viewparticipants',    # Can see participants
        'moodle/course:enrolreview',         # Can review enrolments
    ]
    
    all_teachers = {}
    
    for capability in teaching_capabilities:
        params = {
            'wstoken': token,
            'wsfunction': 'core_enrol_get_enrolled_users',
            'moodlewsrestformat': 'json',
            'courseid': course_id,
            'options[0][name]': 'withcapability',
            'options[0][value]': capability
        }
        
        try:
            client = await _get_async_client()
            response = await client.get(
                f"{MOODLE_BASE_URL}/webservice/rest/server.php",  # ✅ FIXED: Use MOODLE_BASE_URL
                params=params
            )
            
            if response.status_code == 200:
                users = response.json()
                # Handle case where response might be a dict with exception
                if isinstance(users, dict) and users.get('exception'):
                    print(f"⚠️ Moodle API error: {users.get('message')}")
                    continue
                    
                if isinstance(users, list):
                    for user in users:
                        if user.get('id') not in all_teachers:
                            phone = user.get('phone1', '') or user.get('phone2', '')
                            all_teachers[user['id']] = {
                                'id': user['id'],
                                'fullname': user.get('fullname', ''),
                                'firstname': user.get('firstname', ''),
                                'lastname': user.get('lastname', ''),
                                'email': user.get('email', ''),
                                'phone': phone,
                                'contact_method': 'whatsapp' if phone else 'email',
                                'capabilities': [capability]
                            }
                        else:
                            all_teachers[user['id']]['capabilities'].append(capability)
        except Exception as e:
            print(f"Error checking capability {capability}: {e}")
            continue
    
    return list(all_teachers.values())


async def get_course_teachers_by_role_async(token: str, course_id: int, role_shortname: str = 'editingteacher') -> list:
    """
    Fallback: Get users by specific role shortname.
    Note: This requires the role shortname to be known and consistent.
    """
    try:
        # First, get the role ID for the shortname
        params_roles = {
            'wstoken': token,
            'wsfunction': 'core_role_get_roles',
            'moodlewsrestformat': 'json',
        }
        
        client = await _get_async_client()
        response = await client.get(
            f"{MOODLE_BASE_URL}/webservice/rest/server.php",  # ✅ FIXED: Use MOODLE_BASE_URL
            params=params_roles
        )
        
        if response.status_code == 200:
            all_roles = response.json()
            target_role_id = None
            for role in all_roles:
                if role.get('shortname') == role_shortname:
                    target_role_id = role.get('id')
                    break
            
            if target_role_id:
                # Get users with this role in the course
                params_users = {
                    'wstoken': token,
                    'wsfunction': 'core_role_assign_get_users_by_roleid',
                    'moodlewsrestformat': 'json',
                    'roleid': target_role_id,
                    'contextid': course_id,  # Course context
                }
                
                response2 = await client.get(
                    f"{MOODLE_BASE_URL}/webservice/rest/server.php",  # ✅ FIXED
                    params=params_users
                )
                
                if response2.status_code == 200:
                    users = response2.json()
                    print("users",users)
                    # Format users similarly to the comprehensive function
                    formatted_users = []
                    for user in users:
                        if isinstance(user, dict):
                            phone = user.get('phone1', '') or user.get('phone2', '')
                            formatted_users.append({
                                'id': user.get('id'),
                                'fullname': user.get('fullname', ''),
                                'firstname': user.get('firstname', ''),
                                'lastname': user.get('lastname', ''),
                                'email': user.get('email', ''),
                                'phone': phone,
                                'contact_method': 'whatsapp' if phone else 'email',
                                'capabilities': [role_shortname]
                            })
                    print("formatted_users",formatted_users)
                    return formatted_users

        
        return []
        
    except Exception as e:
        print(f"Error getting users by role: {e}")
        return []


# Note: send_to_course_teachers should be in your MAIN whatsapp.py file
# because it uses _send_whatsapp_message and user_moodle_data
# But you can define it there, or pass these as parameters

# If you want to keep it in moodle_service.py, you need to pass the send function:
async def send_to_course_teachers(
    learner_phone: str, 
    course_name: str, 
    course_id: int, 
    question: str,
    user_moodle_data: dict,  # Pass this from main file
    send_whatsapp_func,      # Pass the send function
    get_fullname_func=None    # Optional function to get learner name
):
    """Send learner question to all users with teaching capabilities in the course"""
    
    token = user_moodle_data.get(learner_phone, {}).get('token')
    if not token:
        print(f"No token for learner {learner_phone}")
        return None
    
    # Get teachers using capability-based filtering
    teachers = await get_course_teachers_comprehensive_async(token, course_id)
    
    if not teachers:
        # Fallback: try to get users with 'editingteacher' role
        teachers = await get_course_teachers_by_role_async(token, course_id, 'editingteacher')
    
    if not teachers:
        print(f"No teachers found for course {course_id}")
        return None
    
    # Get learner name
    learner_name = user_moodle_data.get(learner_phone, {}).get('fullname', 'A learner')
    if get_fullname_func:
        learner_name = await get_fullname_func(learner_phone) or learner_name
    
    # Generate unique question ID
    question_id = f"Q{int(time.time())}_{learner_phone[-6:]}"
    
    # Store question (you might want to store this in user_moodle_data or a separate dict)
    if 'pending_questions' not in user_moodle_data:
        user_moodle_data['pending_questions'] = {}
    
    user_moodle_data['pending_questions'][question_id] = {
        'learner_phone': learner_phone,
        'course_id': course_id,
        'course_name': course_name,
        'question': question,
        'timestamp': datetime.now().isoformat(),
        'status': 'pending'
    }
    
    # Send to each teacher
    notified_count = 0
    for teacher in teachers:
        if teacher.get('contact_method') == 'whatsapp' and teacher.get('phone'):
            message = (
                f"👨‍🏫 *New Question from Learner*\n\n"
                f"📚 Course: {course_name}\n"
                f"👤 Learner: {learner_name}\n"
                f"❓ Question: {question}\n\n"
                f"💡 Reply: /reply {question_id} [your answer]\n\n"
                f"Example: /reply {question_id} Thank you for your question..."
            )
            
            teacher_whatsapp = teacher['phone']
            if not teacher_whatsapp.startswith('whatsapp:'):
                teacher_whatsapp = f"whatsapp:{teacher_whatsapp}"
            
            # Use the passed send function
            await send_whatsapp_func(teacher_whatsapp, message)
            notified_count += 1
            print(f"Notified teacher {teacher['fullname']} at {teacher_whatsapp}")
    
    print(f"Notified {notified_count} teachers for course {course_id}")
    return question_id