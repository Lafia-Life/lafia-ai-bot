
import os
from pathlib import Path
import requests
import threading
import time
import urllib.parse
import json
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

def get_moodle_courses():
    """Fetch courses from Moodle API"""
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
            module_name = module.get("name", "Untitled")
            module_type = module.get("modname")
            module_cmid = module.get("id")

            for content in module.get("contents", []):
                file_url = content.get("fileurl")
                mimetype = content.get("mimetype")
                filename = content.get("filename")

                if not file_url or not mimetype:
                    continue

                working_url = file_url

                file_obj = {
                    "title": module_name,
                    "filename": filename,
                    "url": working_url,
                    "mimetype": mimetype,
                    "cmid": module_cmid,
                    "course_id": course_id,
                }

                if mimetype.startswith("video/"):
                    section_obj["videos"].append(file_obj)
                elif mimetype == "application/pdf":
                    section_obj["pdfs"].append(file_obj)
                elif mimetype in (
                    "application/vnd.ms-powerpoint",
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                ):
                    section_obj["powerpoints"].append(file_obj)

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
    
    if not contents:
        return {'pdfs': pdfs, 'videos': videos}
    
    for section in contents:
        for module in section.get('modules', []):
            for content in module.get('contents', []):
                if content.get('type') == 'file':
                    fileurl = content.get('fileurl', '')
                    filename = content.get('filename', 'file')
                    mimetype = content.get('mimetype', '')
                    
                    if not fileurl:
                        continue
                    
                    # Add token to URL for direct access
                    parsed = urlparse(fileurl)
                    query_params = parse_qs(parsed.query)
                    query_params['token'] = [token]
                    query_params['forcedownload'] = ['1']
                    
                    new_query = urlencode(query_params, doseq=True)
                    accessible_url = parsed._replace(query=new_query).geturl()
                    
                    file_info = {
                        'title': filename,
                        'url': accessible_url,
                        'original_url': fileurl,
                        'size': content.get('filesize', 0),
                        'type': mimetype
                    }
                    
                    # Categorize
                    if '.pdf' in filename.lower() or 'pdf' in mimetype:
                        pdfs.append(file_info)
                    elif any(ext in filename.lower() for ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm']) or 'video' in mimetype:
                        videos.append(file_info)
                    elif 'video' in filename.lower():
                        videos.append(file_info)
    
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
