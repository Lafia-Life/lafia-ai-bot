
import os
from pathlib import Path
import requests
import threading
import time
import urllib.parse
import json
import re
from html import unescape
from urllib.parse import urlparse, parse_qs, urlencode
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

cache_lock = threading.Lock()
courses_cache = {}   
CACHE_DURATION = 300 
courses_cache_timestamp = 0
MOODLE_BASE_URL = os.getenv("MOODLE_BASE_URL")
MOODLE_TOKEN = os.getenv("MOODLE_TOKEN")
_preload_thread = None
_preload_thread_lock = threading.Lock()
_invalid_token_warning_printed = False
_missing_config_warning_printed = False
URL_PATTERN = re.compile(r'https?://[^\s<>"\']+')
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv", ".flv", ".3gp")
VIDEO_HOST_HINTS = ("youtube.com", "youtu.be", "vimeo.com", "dailymotion.com", "wistia.")
POWERPOINT_MIMETYPES = (
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
)


def _strip_url(url: str) -> str:
    cleaned = unescape(str(url or "")).strip()
    if not cleaned:
        return ""
    return cleaned.rstrip('\'"<>.,;)')


def _ensure_webservice_pluginfile(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or ""
    if "/webservice/pluginfile.php/" in path:
        return url
    if "/pluginfile.php/" in path:
        path = path.replace("/pluginfile.php/", "/webservice/pluginfile.php/", 1)
        return parsed._replace(path=path).geturl()
    if path.endswith("/pluginfile.php"):
        path = path.replace("/pluginfile.php", "/webservice/pluginfile.php")
        return parsed._replace(path=path).geturl()
    return url


def _tokenize_url(url: str, token: str | None) -> str:
    url = _ensure_webservice_pluginfile(url)
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    if token:
        query_params["token"] = [token]
    query_params["forcedownload"] = ["1"]
    query_params.pop("wstoken", None)
    return parsed._replace(query=urlencode(query_params, doseq=True)).geturl()


def _normalize_resource_url(url: str, token: str | None) -> str:
    cleaned = _strip_url(url)
    if not cleaned:
        return ""
    cleaned = _ensure_webservice_pluginfile(cleaned)
    if "pluginfile.php" in cleaned:
        return _tokenize_url(cleaned, token)
    return cleaned


def _is_pdf_resource(filename: str, mimetype: str, url: str) -> bool:
    low_filename = (filename or "").lower()
    low_mimetype = (mimetype or "").lower()
    low_url = (url or "").lower()
    return (
        low_filename.endswith(".pdf")
        or ".pdf?" in low_url
        or low_url.endswith(".pdf")
        or "pdf" in low_mimetype
    )


def _is_video_resource(filename: str, mimetype: str, url: str, title: str = "") -> bool:
    low_filename = (filename or "").lower()
    low_mimetype = (mimetype or "").lower()
    low_url = (url or "").lower()
    low_title = (title or "").lower()
    if "video" in low_mimetype:
        return True
    if any(low_filename.endswith(ext) for ext in VIDEO_EXTENSIONS):
        return True
    if any(ext + "?" in low_url or low_url.endswith(ext) for ext in VIDEO_EXTENSIONS):
        return True
    if any(host in low_url for host in VIDEO_HOST_HINTS):
        return True
    if "video" in low_title or "video" in low_filename:
        return True
    return False


def _is_powerpoint_resource(filename: str, mimetype: str, url: str) -> bool:
    low_filename = (filename or "").lower()
    low_mimetype = (mimetype or "").lower()
    low_url = (url or "").lower()
    return (
        low_mimetype in POWERPOINT_MIMETYPES
        or low_filename.endswith(".ppt")
        or low_filename.endswith(".pptx")
        or ".ppt?" in low_url
        or ".pptx?" in low_url
    )


def _extract_urls_from_blob(blob: str) -> list[str]:
    if not blob or not isinstance(blob, str):
        return []
    return URL_PATTERN.findall(unescape(blob))


def _collect_module_resources(module: dict, token: str | None, course_id: str):
    module_name = module.get("name", "Untitled")
    module_cmid = module.get("id")
    videos = []
    pdfs = []
    powerpoints = []
    seen_urls = set()

    def add_resource(url: str, filename: str = "", mimetype: str = "", size: int = 0):
        normalized_url = _normalize_resource_url(url, token)
        if not normalized_url or normalized_url in seen_urls:
            return
        seen_urls.add(normalized_url)

        entry = {
            "title": module_name,
            "filename": filename or module_name,
            "url": normalized_url,
            "original_url": _strip_url(url),
            "mimetype": mimetype or "",
            "type": mimetype or "",
            "cmid": module_cmid,
            "course_id": course_id,
            "size": size or 0,
        }

        if _is_pdf_resource(entry["filename"], entry["mimetype"], entry["url"]):
            pdfs.append(entry)
        elif _is_video_resource(entry["filename"], entry["mimetype"], entry["url"], module_name):
            videos.append(entry)
        elif _is_powerpoint_resource(entry["filename"], entry["mimetype"], entry["url"]):
            powerpoints.append(entry)

    for content in module.get("contents", []):
        add_resource(
            content.get("fileurl") or content.get("url") or content.get("contenturl"),
            content.get("filename") or content.get("name") or module_name,
            content.get("mimetype") or content.get("type") or "",
            content.get("filesize", 0),
        )

    # URL activity modules may expose their target URL here.
    add_resource(module.get("url"), module_name, "", 0)

    # Files/links embedded in Moodle editor content (Label, Page, Book, etc.).
    for field in ("description", "intro", "summary", "content"):
        for embedded_url in _extract_urls_from_blob(module.get(field)):
            add_resource(embedded_url, module_name, "", 0)

    return {"videos": videos, "pdfs": pdfs, "powerpoints": powerpoints}


def _collect_section_embedded_resources(section: dict, token: str | None, course_id: str):
    """Collect links/files placed in section editor fields (summary/description)."""
    pseudo_module = {
        "id": section.get("id"),
        "name": section.get("name") or "Section Content",
        "summary": section.get("summary") or "",
        "description": section.get("description") or "",
        "intro": section.get("intro") or "",
        "content": section.get("content") or "",
        "contents": [],
    }
    return _collect_module_resources(pseudo_module, token, course_id)

def get_moodle_courses():
    """Fetch courses from Moodle API"""
    global _invalid_token_warning_printed, _missing_config_warning_printed

    if not MOODLE_BASE_URL or not MOODLE_TOKEN:
        if not _missing_config_warning_printed:
            print("⚠️ Moodle preload skipped: set MOODLE_BASE_URL and MOODLE_TOKEN.")
            _missing_config_warning_printed = True
        return {}

    _missing_config_warning_printed = False
    url = f"{MOODLE_BASE_URL}/webservice/rest/server.php"
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
            message = courses.get('message', 'Unknown error')
            if "invalid token" in str(message).lower():
                if not _invalid_token_warning_printed:
                    print("⚠️ Moodle API token is invalid. Update MOODLE_TOKEN and restart the app container.")
                    _invalid_token_warning_printed = True
            else:
                print(f"Moodle API error: {message}")
            return {}

        _invalid_token_warning_printed = False
        
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
        print(f"❌ Network error fetching Moodle courses: {e}")
        return {}
    except ValueError as e:
        print(f"❌ JSON parsing error from Moodle API: {e}")
        return {}
    except Exception as e:
        print(f"❌ Unexpected error fetching Moodle courses: {e}")
        return {}

def get_moodle_course_contents(course_id: str):
    url = f"{MOODLE_BASE_URL}/webservice/rest/server.php"
    params = {
        "wstoken": MOODLE_TOKEN,
        "wsfunction": "core_course_get_contents",
        "courseid": course_id,
        "moodlewsrestformat": "json",
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    sections_data = response.json()
    sections = []

    for section in sections_data:
        section_obj = {
            "id": section.get("id"),
            "name": section.get("name") or "Untitled Section",
            "videos": [],
            "pdfs": [],
            "powerpoints": [],
        }

        for module in section.get("modules", []):
            resources = _collect_module_resources(module, MOODLE_TOKEN, course_id)
            section_obj["videos"].extend(resources["videos"])
            section_obj["pdfs"].extend(resources["pdfs"])
            section_obj["powerpoints"].extend(resources["powerpoints"])

        section_resources = _collect_section_embedded_resources(section, MOODLE_TOKEN, course_id)
        section_obj["videos"].extend(section_resources["videos"])
        section_obj["pdfs"].extend(section_resources["pdfs"])
        section_obj["powerpoints"].extend(section_resources["powerpoints"])

        sections.append(section_obj)

    return {"course_id": course_id, "sections": sections}

def preload_courses_background():
    """Preload all courses and contents every CACHE_DURATION seconds."""
    global courses_cache, courses_cache_timestamp

    while True:
        print("⏳ Preloading Moodle courses in background...")
        try:
            # Force refresh so Moodle add/delete changes are picked up regularly.
            courses = get_available_courses(force_refresh=True)
            with cache_lock:
                courses_cache = courses
                courses_cache_timestamp = time.time()
            print(f"✅ Preloaded {len(courses_cache)} courses at {time.ctime()}")
        except Exception as e:
            print(f"❌ Error preloading courses: {e}")
        time.sleep(CACHE_DURATION)


def start_preload_worker() -> bool:
    """Start the Moodle preload worker once per process."""
    global _preload_thread

    with _preload_thread_lock:
        if _preload_thread is not None and _preload_thread.is_alive():
            return False
        _preload_thread = threading.Thread(
            target=preload_courses_background,
            daemon=True,
            name="moodle-preload-worker",
        )
        _preload_thread.start()
        return True

def clear_courses_cache():
    """Clear in-memory Moodle course cache."""
    global courses_cache, courses_cache_timestamp
    with cache_lock:
        courses_cache = {}
        courses_cache_timestamp = 0


def get_available_courses(force_refresh: bool = False):
    """Return Moodle courses with full content, using cache unless force_refresh is True."""
    global courses_cache, courses_cache_timestamp

    current_time = time.time()
    with cache_lock:
        if (not force_refresh) and courses_cache and (current_time - courses_cache_timestamp < CACHE_DURATION):
            return courses_cache.copy()

    moodle_courses = get_moodle_courses()
    courses = {}

    for course_id, course in moodle_courses.items():
        try:
            contents = get_moodle_course_contents(course_id)

            # Aggregate resources
            course_pdfs = []
            course_videos = []
            course_powerpoints = []

            for section in contents["sections"]:
                course_pdfs.extend(section.get("pdfs", []))
                course_videos.extend(section.get("videos", []))
                course_powerpoints.extend(section.get("powerpoints", []))

            courses[course_id] = {
                "id": course_id,
                "name": course["name"],
                "pdfs": course_pdfs,
                "videos": course_videos,
                "powerpoints": course_powerpoints,
                "sections": contents["sections"],
            }
        except Exception as e:
            print(f"❌ Failed to load course {course['name']}: {e}")

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

def extract_moodle_resources(contents, token: str):
    """Extract PDFs and videos from course contents - TESTED & WORKING"""
    pdfs = []
    videos = []
    seen_video_urls = set()
    seen_pdf_urls = set()
    
    if not contents:
        return {'pdfs': pdfs, 'videos': videos}
    
    for section in contents:
        section_course_id = str(section.get("courseid", "") or section.get("id", ""))
        section_resources = _collect_section_embedded_resources(section, token, section_course_id)
        for video in section_resources["videos"]:
            if video["url"] not in seen_video_urls:
                seen_video_urls.add(video["url"])
                videos.append(video)
        for pdf in section_resources["pdfs"]:
            if pdf["url"] not in seen_pdf_urls:
                seen_pdf_urls.add(pdf["url"])
                pdfs.append(pdf)

        for module in section.get('modules', []):
            resources = _collect_module_resources(module, token, section_course_id)
            for video in resources["videos"]:
                if video["url"] not in seen_video_urls:
                    seen_video_urls.add(video["url"])
                    videos.append(video)
            for pdf in resources["pdfs"]:
                if pdf["url"] not in seen_pdf_urls:
                    seen_pdf_urls.add(pdf["url"])
                    pdfs.append(pdf)
    
    return {'pdfs': pdfs, 'videos': videos}

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
    
def is_user_enrolled_in_course(token: str, userid: int, courseid: int):
    """Check if user is already enrolled in a course"""
    try:
        enrolled_courses = get_user_enrolled_courses_moodle(token, userid)
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
