"""WHO knowledge source for Lafia Chat AI.

IMPORTANT LICENSING NOTE
========================
WHO content is not ours to relicense. This module therefore commits ONLY
topic identifiers, short titles and canonical URLs. Page text is fetched at
runtime from who.int and cached under ``storage/who_cache`` (gitignored); no
WHO article text is stored in this repository. See ``NOTICE`` for attribution
and the WHO reuse terms.

The bundled knowledge is general health information, not a diagnosis. Every
source is credited and linked in the chat UI.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings
from app.schemas import DocumentSummary
from app.services.document_store import DocumentStore
from app.services.embeddings import embed_texts
from app.services.vectorstore import get_collection, upsert_documents

WHO_CONTENT_VERSION = "runtime-v2"
WHO_REUSE_TERMS = "https://www.who.int/about/policies/publishing/copyright"

# Metadata only. Do not add article text here; it violates WHO's reuse terms.
WHO_TOPICS: List[dict] = [
    {"id": "malaria", "title": "Malaria", "url": "https://www.who.int/news-room/fact-sheets/detail/malaria"},
    {"id": "maternal-health", "title": "Maternal and newborn health", "url": "https://www.who.int/health-topics/maternal-health"},
    {"id": "maternal-mortality", "title": "Maternal mortality and pregnancy complications", "url": "https://www.who.int/news-room/fact-sheets/detail/maternal-mortality"},
    {"id": "immunization", "title": "Childhood immunization", "url": "https://www.who.int/health-topics/vaccines-and-immunization"},
    {"id": "tuberculosis", "title": "Tuberculosis (TB)", "url": "https://www.who.int/news-room/fact-sheets/detail/tuberculosis"},
    {"id": "hiv", "title": "HIV and AIDS", "url": "https://www.who.int/news-room/fact-sheets/detail/hiv-aids"},
    {"id": "hypertension", "title": "Hypertension (high blood pressure)", "url": "https://www.who.int/news-room/fact-sheets/detail/hypertension"},
    {"id": "diabetes", "title": "Diabetes", "url": "https://www.who.int/news-room/fact-sheets/detail/diabetes"},
    {"id": "nutrition", "title": "Nutrition and malnutrition", "url": "https://www.who.int/health-topics/nutrition"},
    {"id": "cholera", "title": "Cholera and diarrhoeal disease", "url": "https://www.who.int/news-room/fact-sheets/detail/cholera"},
    {"id": "wash", "title": "Water, sanitation and hygiene (WASH)", "url": "https://www.who.int/news-room/fact-sheets/detail/drinking-water"},
    {"id": "mental-health", "title": "Mental health", "url": "https://www.who.int/health-topics/mental-health"},
    {"id": "adolescent-health", "title": "Adolescent and sexual health", "url": "https://www.who.int/health-topics/adolescent-health"},
    {"id": "outbreaks", "title": "Ebola and outbreak response", "url": "https://www.who.int/news-room/fact-sheets/detail/ebola-disease"},
    {"id": "contraception", "title": "Contraception and family planning", "url": "https://www.who.int/news-room/fact-sheets/detail/family-planning-contraception"},
    {"id": "menstrual-health", "title": "Menstrual health", "url": "https://www.who.int/news-room/fact-sheets/detail/menstrual-health"},
    {"id": "oral-health", "title": "Oral health", "url": "https://www.who.int/health-topics/oral-health"},
]

# UI suggestions. These are Lafia copy, not WHO article text.
SUGGESTED_QUESTIONS = [
    "What are the danger signs in pregnancy?",
    "What contraception options are available to me?",
    "How can I manage period pain?",
    "What is WHO guidance on HIV testing in pregnancy?",
    "I feel anxious — where can I get support?",
    "How can I prevent malaria in my family?",
]


def who_document_id(topic_id: str) -> str:
    return f"who-{topic_id}"


def _cache_dir() -> Path:
    settings = get_settings()
    path = Path(settings.chroma_path).parent / "who_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _chunk_text(text: str, size: int = 900, overlap: int = 150) -> List[str]:
    text = " ".join((text or "").split())
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start += max(size - overlap, 1)
    return chunks


def _extract_sections(html: str) -> List[dict]:
    """Split a WHO page into heading-based sections for better retrieval."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(
        ["script", "style", "noscript", "svg", "canvas", "iframe", "form", "nav", "header", "footer", "aside"]
    ):
        tag.decompose()
    root = soup.select_one("main") or soup.select_one("article") or soup.body or soup

    sections: List[dict] = []
    heading = ""
    parts: List[str] = []

    def flush() -> None:
        text = " ".join(" ".join(parts).split())
        if text:
            sections.append({"heading": heading, "text": text[:12000]})

    for element in root.find_all(["h2", "h3", "h4", "p", "li"]):
        if element.name == "li" and element.find("p"):
            continue
        text = " ".join(element.get_text(" ", strip=True).split())
        if not text:
            continue
        if element.name in {"h2", "h3", "h4"}:
            flush()
            heading = text
            parts = []
        else:
            parts.append(text)
    flush()

    if not sections:
        text = " ".join(root.stripped_strings)
        text = " ".join(text.split())
        if text:
            sections.append({"heading": "", "text": text[:12000]})
    return [section for section in sections if len(section["text"]) >= 40][:40]


def _fetch_topic_sections(topic: dict) -> tuple[Optional[List[dict]], Optional[str]]:
    settings = get_settings()
    cache_file = _cache_dir() / f"{topic['id']}.json"
    headers = {
        "User-Agent": settings.scraper_user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        with httpx.Client(
            timeout=settings.scraper_timeout,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = client.get(topic["url"])
            response.raise_for_status()
        sections = _extract_sections(response.text)
        if sections:
            cache_file.write_text(json.dumps(sections, ensure_ascii=False), encoding="utf-8")
            return sections, None
        return None, "No readable sections extracted."
    except Exception as exc:  # noqa: BLE001
        # A previously fetched runtime cache keeps the app useful offline.
        if cache_file.exists():
            try:
                return json.loads(cache_file.read_text(encoding="utf-8")), f"Using cached copy: {exc}"
            except Exception:
                pass
        return None, str(exc)


def sync_who_knowledge(force: bool = False) -> dict:
    """Fetch WHO pages at runtime and index them into the local vector store."""
    settings = get_settings()
    store = DocumentStore(settings.chroma_path)
    collection = get_collection()

    pending: List[dict] = []
    skipped = 0
    for topic in WHO_TOPICS:
        document_id = who_document_id(topic["id"])
        existing = store.get(document_id)
        expected_ref = f"who:{topic['id']}:{WHO_CONTENT_VERSION}"
        if existing and existing.external_ref == expected_ref and not force:
            skipped += 1
            continue
        pending.append(topic)

    fetched: dict[str, tuple[Optional[List[dict]], Optional[str]]] = {}
    if pending:
        with ThreadPoolExecutor(max_workers=min(6, len(pending))) as pool:
            results = pool.map(_fetch_topic_sections, pending)
            for topic, result in zip(pending, results):
                fetched[topic["id"]] = result

    indexed = 0
    chunks = 0
    errors: List[dict] = []

    for topic in pending:
        sections, error = fetched.get(topic["id"], (None, "not fetched"))
        if error:
            errors.append({"topic": topic["id"], "error": error})
        if not sections:
            continue

        document_id = who_document_id(topic["id"])
        texts: List[str] = []
        metadatas: List[dict] = []
        ids: List[str] = []
        section_count = 0

        for section_index, section in enumerate(sections, start=1):
            heading = section.get("heading") or ""
            body = section.get("text") or ""
            section_text = f"{heading}. {body}" if heading else body
            section_chunks = _chunk_text(section_text)
            if not section_chunks:
                continue
            section_count += 1
            for local_index, chunk in enumerate(section_chunks):
                texts.append(chunk)
                metadatas.append(
                    {
                        "document_id": document_id,
                        "filename": f"WHO - {topic['title']}",
                        "page_start": section_index,
                        "page_end": section_index,
                        "chunk": local_index,
                        "section": heading,
                        "url": topic["url"],
                        "source_type": "who",
                        "content_version": WHO_CONTENT_VERSION,
                    }
                )
                ids.append(f"{document_id}_{section_index}_{local_index}")

        if not texts:
            errors.append({"topic": topic["id"], "error": "No text chunks."})
            continue

        embeddings = embed_texts(texts)
        upsert_documents(
            collection=collection,
            document_id=document_id,
            texts=texts,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids,
        )
        store.upsert(
            DocumentSummary(
                document_id=document_id,
                filename=f"WHO - {topic['title']}",
                page_count=section_count,
                source_type="who",
                url=topic["url"],
                external_ref=f"who:{topic['id']}:{WHO_CONTENT_VERSION}",
            )
        )
        indexed += 1
        chunks += len(texts)

    return {
        "indexed": indexed,
        "skipped": skipped,
        "chunks": chunks,
        "total_topics": len(WHO_TOPICS),
        "errors": errors,
        "content_version": WHO_CONTENT_VERSION,
        "notice": "WHO text is fetched at runtime. See NOTICE and WHO reuse terms.",
        "topics": [
            {"id": t["id"], "title": t["title"], "url": t["url"]} for t in WHO_TOPICS
        ],
    }
