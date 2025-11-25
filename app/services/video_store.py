import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import os

from app.schemas import VideoSummary


class VideoStore:
    def __init__(self, base_path: Path):
        self._file_path = base_path / "videos.json"
        # Store videos in the SAME location as documents (same level as chroma)
        self._storage_path = base_path.parent  # Go up one level to get storage directory
        self._uploads_path = self._storage_path / "uploads"  # Same as documents uploads
        self._uploads_path.mkdir(parents=True, exist_ok=True)
        
        if not self._file_path.exists():
            self._write({})

    def _read(self) -> Dict[str, dict]:
        with self._file_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, data: Dict[str, dict]) -> None:
        with self._file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def save_video_file(self, video_bytes: bytes, filename: str, video_id: str) -> Path:
        """Save video file to disk in the SAME uploads folder as documents"""
        safe_name = filename.replace("/", "_").replace("\\", "_")
        
        # Store in the uploads folder (same level as chroma)
        destination = self._uploads_path / f"{video_id}_{safe_name}"
        destination.write_bytes(video_bytes)
        
        return destination


    def upsert(self, summary: VideoSummary) -> None:
        data = self._read()
        data[summary.video_id] = summary.model_dump()
        self._write(data)

    def list(self) -> List[VideoSummary]:
        data = self._read()
        return [VideoSummary(**item) for item in data.values()]

    def get(self, video_id: str) -> Optional[VideoSummary]:
        data = self._read()
        record = data.get(video_id)
        return VideoSummary(**record) if record else None

    def delete(self, video_id: str) -> bool:
        data = self._read()
        if video_id in data:
            # Also delete the actual video file
            video_info = data[video_id]
            file_path = video_info.get('file_path')
            if file_path and os.path.exists(file_path):
                os.unlink(file_path)
            
            del data[video_id]
            self._write(data)
            return True
        return False