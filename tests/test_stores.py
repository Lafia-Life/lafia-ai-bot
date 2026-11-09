from app.services.course_store import CourseStore
from app.services.document_store import DocumentStore
from app.services.video_store import VideoStore


def test_stores_create_missing_directories(tmp_path):
    data_dir = tmp_path / "storage" / "data"
    chroma_dir = tmp_path / "storage" / "chroma"

    course_store = CourseStore(data_dir)
    document_store = DocumentStore(chroma_dir)
    video_store = VideoStore(chroma_dir)

    assert (data_dir / "courses.json").is_file()
    assert (chroma_dir / "documents.json").is_file()
    assert (chroma_dir / "videos.json").is_file()
    assert course_store.list() == []
    assert document_store.list() == []
    assert video_store.list() == []
