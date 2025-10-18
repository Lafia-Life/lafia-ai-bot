from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.config import Settings, get_openai_api_key, get_settings
from app.schemas import ChatRequest, DocumentSummary, ScrapeRequest, UploadResponse
from app.services.document_store import DocumentStore
from app.services.ingestion import ingest_document, ingest_web_page
from app.services.retrieval import stream_answer

app = FastAPI(title="PDF Chat Assistant")

settings = get_settings()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def get_document_store() -> DocumentStore:
    return DocumentStore(settings.chroma_path)


def _resolve_document_path(document_id: str, store: DocumentStore) -> tuple[DocumentSummary, Path]:
    summary = store.get(document_id)
    if summary is None or summary.source_type != "pdf":
        raise HTTPException(status_code=404, detail="Document not found.")

    matches = sorted(settings.uploads_path.glob(f"{document_id}_*"))
    if not matches:
        raise HTTPException(status_code=404, detail="Stored PDF could not be located.")

    return summary, matches[0]


@app.get("/", response_class=HTMLResponse)
@app.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("chat.html", {"request": request})


@app.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("upload.html", {"request": request})


@app.get("/api/documents", response_model=list[DocumentSummary])
def list_documents(store: DocumentStore = Depends(get_document_store)) -> list[DocumentSummary]:
    return store.list()


@app.post("/api/documents", response_model=UploadResponse)
def upload_document(
    file: UploadFile = File(...),
) -> UploadResponse:
    contents = file.file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    response = ingest_document(upload_bytes=contents, filename=file.filename)
    return response


@app.post("/api/scrape", response_model=UploadResponse)
def scrape_document(payload: ScrapeRequest) -> UploadResponse:
    try:
        return ingest_web_page(str(payload.url))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/chat")
def chat(payload: ChatRequest) -> StreamingResponse:
    if not get_openai_api_key():
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is required for chat responses. Configure a key or set OPENAI_BASE_URL for your provider.",
        )
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question is required.")
    return StreamingResponse(stream_answer(payload), media_type="application/x-ndjson")


@app.get("/documents/{document_id}/download")
def download_document(document_id: str, store: DocumentStore = Depends(get_document_store)) -> FileResponse:
    summary, file_path = _resolve_document_path(document_id, store)
    return FileResponse(file_path, media_type="application/pdf", filename=summary.filename)


@app.get("/documents/{document_id}/inline")
def inline_document(document_id: str, store: DocumentStore = Depends(get_document_store)) -> FileResponse:
    summary, file_path = _resolve_document_path(document_id, store)
    headers = {"Content-Disposition": f'inline; filename="{summary.filename}"'}
    return FileResponse(file_path, media_type="application/pdf", headers=headers)
