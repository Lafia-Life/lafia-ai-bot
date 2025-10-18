from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
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


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


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
