import uuid
from pathlib import Path
from typing import List, Tuple

import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse

from pypdf import PdfReader

from app.config import Settings, get_settings
from app.schemas import DocumentSummary, UploadResponse
from app.services.document_store import DocumentStore
from app.services.embeddings import embed_texts
from app.services.vectorstore import get_collection, upsert_documents


def _sanitize_filename(filename: str) -> str:
    return filename.replace("/", "_").replace("\\", "_")


def _save_upload(upload_bytes: bytes, filename: str, uploads_path: Path, document_id: str) -> Path:
    safe_name = _sanitize_filename(filename)
    destination = uploads_path / f"{document_id}_{safe_name}"
    destination.write_bytes(upload_bytes)
    return destination


def _extract_pages(pdf_path: Path) -> List[Tuple[int, str]]:
    reader = PdfReader(str(pdf_path))
    pages: List[Tuple[int, str]] = []
    for index, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        cleaned = " ".join(text.split())
        if cleaned:
            pages.append((index + 1, cleaned))
    return pages


def _chunk_text(
    page_text: str,
    chunk_size: int,
    chunk_overlap: int,
) -> List[str]:
    if not page_text or not page_text.strip():
        return []
    page_text = page_text.strip()
    if len(page_text) <= chunk_size:
        return [page_text]
    chunks: List[str] = []
    start = 0
    while start < len(page_text):
        end = start + chunk_size
        chunk = page_text[start:end]
        chunks.append(chunk)
        if end >= len(page_text):
            break
        start += max(chunk_size - chunk_overlap, 1)
    return chunks


def _build_chunk_payload(
    document_id: str,
    filename: str,
    pages: List[Tuple[int, str]],
    chunk_size: int,
    chunk_overlap: int,
) -> Tuple[List[str], List[dict], List[str]]:
    texts: List[str] = []
    metadatas: List[dict] = []
    ids: List[str] = []

    for page_number, text in pages:
        page_chunks = _chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        for local_index, chunk in enumerate(page_chunks):
            chunk_id = f"{document_id}_{page_number}_{local_index}"
            texts.append(chunk)
            metadatas.append(
                {
                    "document_id": document_id,
                    "filename": filename,
                    "page_start": page_number,
                    "page_end": page_number,
                    "chunk": local_index,
                    "url": "",
                    "source_type": "pdf",
                }
            )
            ids.append(chunk_id)
    return texts, metadatas, ids


def _fetch_web_content(url: str) -> Tuple[str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PDFChatBot/1.0; +https://github.com/egesamichael/chatlearning)",
    }
    with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()
        html = response.text

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "canvas", "iframe"]):
        tag.decompose()

    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    if not title:
        parsed = urlparse(url)
        title = parsed.netloc or url

    text_chunks = list(soup.stripped_strings)
    text = " ".join(text_chunks)
    text = " ".join(text.split())
    if len(text) > 50000:
        text = text[:50000]

    return title, text


def _save_web_snapshot(content: str, uploads_path: Path, document_id: str) -> Path:
    destination = uploads_path / f"{document_id}.txt"
    destination.write_text(content, encoding="utf-8")
    return destination


def _build_web_chunk_payload(
    document_id: str,
    title: str,
    url: str,
    text: str,
    chunk_size: int,
    chunk_overlap: int,
) -> Tuple[List[str], List[dict], List[str]]:
    chunks = _chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    texts: List[str] = []
    metadatas: List[dict] = []
    ids: List[str] = []

    for index, chunk in enumerate(chunks):
        chunk_id = f"{document_id}_web_{index}"
        texts.append(chunk)
        metadatas.append(
            {
                "document_id": document_id,
                "filename": title,
                "page_start": index + 1,
                "page_end": index + 1,
                "chunk": index,
                "url": url,
                "source_type": "web",
            }
        )
        ids.append(chunk_id)

    return texts, metadatas, ids


def ingest_document(upload_bytes: bytes, filename: str) -> UploadResponse:
    settings: Settings = get_settings()
    document_store = DocumentStore(settings.chroma_path)
    collection = get_collection()

    document_id = str(uuid.uuid4())
    saved_path = _save_upload(upload_bytes, filename, settings.uploads_path, document_id)

    pages = _extract_pages(saved_path)
    texts, metadatas, ids = _build_chunk_payload(
        document_id=document_id,
        filename=filename,
        pages=pages,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    if not texts:
        raise ValueError("Unable to extract text from the uploaded PDF.")

    embeddings = embed_texts(texts)
    upsert_documents(
        collection=collection,
        document_id=document_id,
        texts=texts,
        embeddings=embeddings,
        metadatas=metadatas,
        ids=ids,
    )

    summary = DocumentSummary(
        document_id=document_id,
        filename=filename,
        page_count=len(pages),
        source_type="pdf",
        url=None,
    )
    document_store.upsert(summary)

    return UploadResponse(document=summary, chunks_indexed=len(texts))


def ingest_web_page(url: str) -> UploadResponse:
    settings: Settings = get_settings()
    document_store = DocumentStore(settings.chroma_path)
    collection = get_collection()

    document_id = str(uuid.uuid4())
    try:
        title, text = _fetch_web_content(url)
    except httpx.HTTPError as exc:
        raise ValueError(f"Failed to fetch content from URL: {exc}") from exc

    if not text:
        raise ValueError("Unable to extract meaningful text from the provided URL.")

    _save_web_snapshot(text, settings.uploads_path, document_id)

    texts, metadatas, ids = _build_web_chunk_payload(
        document_id=document_id,
        title=title,
        url=url,
        text=text,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    if not texts:
        raise ValueError("No textual content found on the provided web page.")

    embeddings = embed_texts(texts)
    upsert_documents(
        collection=collection,
        document_id=document_id,
        texts=texts,
        embeddings=embeddings,
        metadatas=metadatas,
        ids=ids,
    )

    summary = DocumentSummary(
        document_id=document_id,
        filename=title,
        page_count=len(texts),
        source_type="web",
        url=url,
    )
    document_store.upsert(summary)

    return UploadResponse(document=summary, chunks_indexed=len(texts))
