import json
from typing import Generator, Iterable, List, Optional, Tuple

from fastapi.encoders import jsonable_encoder

from app.config import Settings, get_openai_client, get_openai_async_client, get_settings
import asyncio
from app.schemas import ChatRequest, ChatResponse, Citation
from app.services.embeddings import embed_query
from app.services.vectorstore import get_collection, query_collection


LANGUAGE_NAMES = {
    "en": "English",
    "sw": "Kiswahili",
    "lg": "Luganda",
    "ach": "Acholi",
    "teo": "Ateso",
    "xog": "Lusoga",
}

_NO_CONTEXT_MESSAGE = (
    "I could not find that in the uploaded documents or the WHO knowledge base. "
    "Try rephrasing your question, uploading a relevant document from the Knowledge Base, "
    "or ask about a general health topic such as malaria, immunization, maternal health or TB."
)
_RETRIEVAL_CANDIDATES = 30


def _retrieval_error_message(exc: Exception) -> str:
    detail = str(exc).strip()
    if "sentence-transformers" in detail:
        return (
            "Embeddings backend is not ready on this server. "
            "Install 'sentence-transformers' or set EMBEDDING_BACKEND=openai "
            "with a valid embedding model."
        )
    if detail:
        return f"Unable to search indexed documents: {detail}"
    return "Unable to search indexed documents due to a server configuration error."


def _fetch_retrieval_results(collection, payload: ChatRequest) -> List[dict]:
    embedding = embed_query(payload.question)
    raw_results = query_collection(
        collection=collection,
        embedding=embedding,
        n_results=_RETRIEVAL_CANDIDATES,
    )
    filtered = _filter_results(raw_results, payload, limit=6)

    # The lightweight hash back-end produces broad distances. Keep only passages
    # that are close to the best match so irrelevant sources are not cited.
    if filtered and get_settings().embedding_backend == "hash":
        best = min(float(item.get("distance", 0.0)) for item in filtered)
        cutoff = best * 1.16
        filtered = [
            item for item in filtered if float(item.get("distance", 0.0)) <= cutoff
        ][:5]

    return filtered


def _coerce_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8")
        except Exception:  # noqa: BLE001
            return ""
    if hasattr(value, "model_dump"):
        try:
            value = value.model_dump()
        except Exception:  # noqa: BLE001
            pass
    if isinstance(value, dict):
        for key in ("content", "text", "message"):
            if key in value and value[key] is not None:
                coerced = _coerce_text(value[key])
                if coerced:
                    return coerced
        parts = []
        for key, item in value.items():
            if key in {"role", "index", "finish_reason"}:
                continue
            coerced = _coerce_text(item)
            if coerced:
                parts.append(coerced)
        return "".join(parts)
    content_attr = getattr(value, "content", None)
    if content_attr is not None:
        return _coerce_text(content_attr)
    text_attr = getattr(value, "text", None)
    if text_attr is not None:
        return _coerce_text(text_attr)
    if isinstance(value, Iterable):
        parts = [_coerce_text(item) for item in value if item is not None]
        return "".join(part for part in parts if part)
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _format_context(results: List[dict]) -> str:
    context_blocks = []
    for item in results:
        metadata = item["metadata"]
        text = item["text"]
        source_type = metadata.get("source_type", "pdf")
        location: str
        if source_type in {"web", "who"}:
            location = f"section {metadata.get('page_start', 1)}"
        else:
            location = f"pages {metadata.get('page_start', 1)}-{metadata.get('page_end', metadata.get('page_start', 1))}"
        source_name = metadata.get("url") or metadata.get("filename", "Unknown source")
        context_blocks.append(
            f"Source: {source_name} ({location})\n{text}"
        )
    return "\n\n".join(context_blocks)


def _build_prompt(
    question: str,
    context: str,
    context_prompt: Optional[str] = None,
    history: Optional[List] = None,
    language: Optional[str] = None,
) -> List[dict]:
    system = (
        "You are Lafia Chat AI, a friendly and trustworthy health information assistant. "
        "You answer questions using ONLY the provided context, which comes from documents the "
        "user uploaded and from official WHO (World Health Organization) health guidance. "
        "Be warm, clear and practical. Prefer short paragraphs and bullet points. "
        "Quote relevant facts when useful and cite each source in square brackets using the "
        "source filename and section/page, for example [WHO - Malaria section 2] or "
        "[Report.pdf p.3]. "
        "If the context does not contain the answer, say you could not find it in the available "
        "sources and suggest what document or WHO topic could help. Never invent facts, numbers "
        "or citations. "
        "You are not a doctor: do not diagnose, prescribe, or give personalised dosage advice. "
        "For red-flag or emergency symptoms, clearly advise the user to contact a qualified "
        "health worker or go to the nearest health facility immediately. "
        "Use the conversation history to understand follow-up questions."
    )
    language_name = LANGUAGE_NAMES.get((language or "en").strip().lower(), "English")
    if language_name != "English":
        system += (
            f"\nReply in {language_name}. Write naturally and clearly for a low-literacy "
            f"reader. If a medical term has no reliable translation, keep the English term "
            f"in parentheses. Do not switch to English for the whole answer."
        )
    if context_prompt and context_prompt.strip():
        system = system + "\n\nAdditional instructions:\n" + context_prompt.strip()

    messages: List[dict] = [{"role": "system", "content": system}]
    for turn in history or []:
        role = str(getattr(turn, "role", "")).strip().lower()
        content = str(getattr(turn, "content", "")).strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content[:4000]})

    messages.append(
        {
            "role": "user",
            "content": (
                "Context:\n" + context + "\n\n" + "Question: " + question
            ),
        }
    )
    return messages


def _normalize_str_list(values: Optional[List[str]]) -> set[str]:
    if not values:
        return set()
    return {str(item).strip().lower() for item in values if str(item).strip()}


def _normalize_course_list(values: Optional[List[str]]) -> set[str]:
    if not values:
        return set()
    return {str(item).strip() for item in values if str(item).strip()}


def _filter_results(raw_results: List[dict], payload: ChatRequest, limit: int = 6) -> List[dict]:
    allowed_source_types = _normalize_str_list(payload.allowed_source_types)
    allowed_course_ids = _normalize_course_list(payload.allowed_course_ids)
    include_global_docs = bool(payload.include_global_docs)
    document_scope = str(payload.document_scope or "").strip().lower()
    scoped_moodle_cmid = str(payload.moodle_cmid or "").strip()

    filtered: List[dict] = []
    for result in raw_results:
        metadata = result.get("metadata") or {}
        source_type = str(metadata.get("source_type", "pdf")).strip().lower()
        if allowed_source_types and source_type not in allowed_source_types:
            continue

        if document_scope == "currentcourse" and scoped_moodle_cmid:
            metadata_cmid = str(metadata.get("moodle_cmid") or "").strip()
            if metadata_cmid != scoped_moodle_cmid:
                continue

        course_id = metadata.get("course_id")
        if allowed_course_ids:
            if course_id in (None, "") and not include_global_docs:
                continue
            if course_id not in (None, "") and str(course_id).strip() not in allowed_course_ids:
                continue

        filtered.append(result)
        if len(filtered) >= limit:
            break

    return filtered


def _to_citations(results: List[dict]) -> List[Citation]:
    citations: List[Citation] = []
    seen: set[tuple[str, int]] = set()
    for item in results:
        metadata = item["metadata"]
        citation_key = (
            str(metadata.get("document_id", "")),
            int(metadata.get("page_start", 0) or 0),
        )
        if citation_key in seen:
            continue
        seen.add(citation_key)
        distance = float(item.get("distance", 0.0))
        similarity = max(0.0, 1.0 - distance)
        excerpt = item.get("text", "").strip()
        if excerpt and len(excerpt) > 400:
            excerpt = excerpt[:397].rstrip() + "..."
        source_type = metadata.get("source_type", "pdf")
        url = metadata.get("url")
        page_start = int(metadata.get("page_start", 0) or 0)
        page_end = int(metadata.get("page_end", page_start) or page_start)
        citations.append(
            Citation(
                document_id=metadata["document_id"],
                filename=metadata["filename"],
                page_start=page_start,
                page_end=page_end,
                score=round(similarity, 4),
                excerpt=excerpt,
                source_type=source_type,
                url=url,
                course_id=metadata.get("course_id"),
            )
        )
    return citations


def answer_question(payload: ChatRequest) -> ChatResponse:
    settings: Settings = get_settings()
    client = get_openai_client(settings)
    collection = get_collection()

    try:
        raw_results = _fetch_retrieval_results(collection, payload)
    except Exception as exc:  # noqa: BLE001
        return ChatResponse(
            answer=_retrieval_error_message(exc),
            citations=[],
        )

    if not raw_results:
        return ChatResponse(
            answer="I could not find the answer in the uploaded documents.",
            citations=[],
        )

    context = _format_context(raw_results)
    messages = _build_prompt(payload.question, context, payload.context_prompt, payload.history, payload.language)
    chat_completion = client.chat.completions.create(
        model=settings.chat_model,
        messages=messages,
        temperature=0.2,
    )

    answer_text = _coerce_text(chat_completion.choices[0].message.content).strip()

    return ChatResponse(
        answer=answer_text,
        citations=_to_citations(raw_results),
    )


async def answer_question_async(payload: ChatRequest) -> ChatResponse:
    settings: Settings = get_settings()
    client = get_openai_async_client(settings)
    collection = get_collection()

    try:
        raw_results = await asyncio.to_thread(_fetch_retrieval_results, collection, payload)
    except Exception as exc:  # noqa: BLE001
        return ChatResponse(
            answer=_retrieval_error_message(exc),
            citations=[],
        )

    if not raw_results:
        return ChatResponse(
            answer="I could not find the answer in the uploaded documents.",
            citations=[],
        )

    context = _format_context(raw_results)
    messages = _build_prompt(payload.question, context, payload.context_prompt, payload.history, payload.language)
    chat_completion = await client.chat.completions.create(
        model=settings.chat_model,
        messages=messages,
        temperature=0.2,
    )

    answer_text = _coerce_text(chat_completion.choices[0].message.content).strip()

    return ChatResponse(
        answer=answer_text,
        citations=_to_citations(raw_results),
    )


def _encode_event(payload: dict) -> bytes:
    return (json.dumps(jsonable_encoder(payload), separators=(",", ":")) + "\n").encode("utf-8")


def stream_answer(payload: ChatRequest) -> Generator[bytes, None, None]:
    settings: Settings = get_settings()
    client = get_openai_client(settings)
    collection = get_collection()

    try:
        raw_results = _fetch_retrieval_results(collection, payload)
    except Exception as exc:  # noqa: BLE001
        yield _encode_event({"type": "error", "message": _retrieval_error_message(exc)})
        return

    if not raw_results:
        yield _encode_event(
            {
                "type": "done",
                "answer": _NO_CONTEXT_MESSAGE,
                "citations": [],
            }
        )
        return

    citations = _to_citations(raw_results)
    if citations:
        yield _encode_event({"type": "references", "citations": citations})

    context = _format_context(raw_results)
    messages = _build_prompt(payload.question, context, payload.context_prompt, payload.history, payload.language)

    answer_parts: List[str] = []

    try:
        stream = client.chat.completions.create(
            model=settings.chat_model,
            messages=messages,
            temperature=0.2,
            stream=True,
        )

        for chunk in stream:
            for choice in chunk.choices:
                delta = getattr(choice, "delta", None)
                if delta is None:
                    continue
                content = _coerce_text(delta)
                if not content:
                    continue
                answer_parts.append(content)
                yield _encode_event({"type": "delta", "content": content})
    except Exception as exc:  # noqa: BLE001
        yield _encode_event({"type": "error", "message": str(exc)})
        return

    answer_text = "".join(answer_parts).strip()

    yield _encode_event(
        {
            "type": "done",
            "answer": answer_text,
            "citations": citations,
        }
    )
