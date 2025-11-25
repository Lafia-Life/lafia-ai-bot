import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import os

from app.schemas import Course, CourseCreate, CourseUpdate

class CourseStore:
    def __init__(self, base_path: Path):
        self._file_path = base_path / "courses.json"
        if self._file_path.exists():        
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._file_path.exists():
            self._write({})
        else:
            # If file exists but might be empty/corrupted, validate it
            self._validate_json_file()

    def _validate_json_file(self) -> None:
        """Ensure the JSON file is valid, recreate if corrupted"""
        try:
            # Try to read the file to check if it's valid JSON
            with self._file_path.open("r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:  # Empty file
                    print("File is empty, recreating...")
                    self._write({})
                else:
                    json.loads(content)  # This will raise JSONDecodeError if invalid
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"JSON file is corrupted: {e}. Recreating...")
            # Backup the corrupted file
            backup_path = self._file_path.with_suffix('.json.bak')
            try:
                self._file_path.rename(backup_path)
                print(f"Backed up corrupted file to: {backup_path}")
            except:
                pass  # If backup fails, continue anyway
            self._write({})

    def _read(self) -> Dict[str, dict]:
        """Read data from JSON file with proper error handling"""
        try:
            with self._file_path.open("r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:  # Handle empty file
                    return {}
                return json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"Error reading JSON file: {e}. Returning empty data.")
            return {}
        except FileNotFoundError:
            print("JSON file not found. Returning empty data.")
            return {}

    def _write(self, data: Dict[str, dict]) -> None:
        """Write data to JSON file"""
        try:
            with self._file_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error writing to JSON file: {e}")
            raise

    def upsert(self, course: Course) -> None:
        """Create or update a course"""
        data = self._read()
        # Convert Course object to dict and handle datetime serialization
        course_dict = course.dict()
        course_dict['created_at'] = course.created_at.isoformat()
        course_dict['updated_at'] = course.updated_at.isoformat()
        data[course.id] = course_dict
        self._write(data)

    def create(self, course_create: CourseCreate, created_by: Optional[str] = None) -> Course:
        """Create a new course"""
        course_id = str(uuid.uuid4())
        now = datetime.now()
        
        course = Course(
            id=course_id,
            title=course_create.title,
            description=course_create.description,
            code=course_create.code,
            is_active=course_create.is_active,
            created_by=created_by,
            created_at=now,
            updated_at=now
        )
        
        self.upsert(course)
        return course

    def list(self, active_only: bool = True, category: Optional[str] = None) -> List[Course]:
        """List all courses with optional filters"""
        data = self._read()
        courses = []
        
        for course_data in data.values():
            try:
                # Convert string dates back to datetime objects
                course_data['created_at'] = datetime.fromisoformat(course_data['created_at'])
                course_data['updated_at'] = datetime.fromisoformat(course_data['updated_at'])
                course = Course(**course_data)
                
                # Apply filters
                if active_only and not course.is_active:
                    continue
                if category and course.category != category:
                    continue
                    
                courses.append(course)
            except (KeyError, ValueError) as e:
                print(f"Skipping invalid course data: {e}")
                continue
        
        return sorted(courses, key=lambda c: c.created_at, reverse=True)

    def get(self, course_id: str) -> Optional[Course]:
        """Get a course by ID"""
        data = self._read()
        record = data.get(course_id)
        if record:
            try:
                # Convert string dates back to datetime objects
                record['created_at'] = datetime.fromisoformat(record['created_at'])
                record['updated_at'] = datetime.fromisoformat(record['updated_at'])
                return Course(**record)
            except (KeyError, ValueError) as e:
                print(f"Invalid course data for {course_id}: {e}")
                return None
        return None

    # ... rest of your methods remain the same ...
    def update(self, course_id: str, course_update: CourseUpdate) -> Optional[Course]:
        """Update a course"""
        existing_course = self.get(course_id)
        if not existing_course:
            return None
        
        # Get update data, excluding unset fields
        update_data = course_update.dict(exclude_unset=True)
        
        # Apply updates
        for field, value in update_data.items():
            setattr(existing_course, field, value)
        
        # Update timestamp
        existing_course.updated_at = datetime.now()
        
        # Save updated course
        self.upsert(existing_course)
        return existing_course

    def delete(self, course_id: str) -> bool:
        """Soft delete a course (set is_active to False)"""
        course = self.get(course_id)
        if course:
            course.is_active = False
            course.updated_at = datetime.now()
            self.upsert(course)
            return True
        return False

    def get_categories(self) -> List[str]:
        """Get all unique categories from existing courses"""
        courses = self.list(active_only=True)
        categories = list(set([course.category for course in courses if course.category]))
        return sorted(categories)