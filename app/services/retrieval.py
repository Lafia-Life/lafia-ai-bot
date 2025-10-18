import json
from collections import OrderedDict
from threading import Lock
from typing import Generator, List, Optional, Tuple

from fastapi.encoders import jsonable_encoder

from app.config import Settings, get_openai_client, get_settings
from app.schemas import ChatRequest, ChatResponse, Citation
from app.services.embeddings import embed_query
from app.services.vectorstore import get_collection, query_collection


class AnswerCache:
    def __init__(self, max_items: int = 32) -> None:
        self.max_items = max_items
        self._entries: "OrderedDict[str, dict]" = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> Optional[dict]:
        with self._lock:
            if key not in self._entries:
                return None
            value = self._entries.pop(key)
            self._entries[key] = value
            return value

    def set(self, key: str, value: dict) -> None:
        with self._lock:
            if key in self._entries:
                self._entries.pop(key)
            self._entries[key] = value
            while len(self._entries) > self.max_items:
                self._entries.popitem(last=False)


def _normalize_question(question: str) -> str:
    return question.strip().lower()


_answer_cache = AnswerCache()

_NO_CONTEXT_MESSAGE = "I could not find the answer in the uploaded documents."


def _format_context(results: List[dict]) -> str:
    context_blocks = []
    for item in results:
        metadata = item["metadata"]
        text = item["text"]
        source_type = metadata.get("source_type", "pdf")
        location: str
        if source_type == "web":
            location = f"section {metadata.get('page_start', 1)}"
        else:
            location = f"pages {metadata.get('page_start', 1)}-{metadata.get('page_end', metadata.get('page_start', 1))}"
        source_name = metadata.get("url") or metadata.get("filename", "Unknown source")
        context_blocks.append(
            f"Source: {source_name} ({location})\n{text}"
        )
    return "\n\n".join(context_blocks)


def _build_prompt(question: str, context: str) -> List[dict]:
    system = (
        "You are a helpful assistant answering questions about a collection of PDF documents. "
        "Use only the provided context to answer. Quote relevant portions when useful. "
        "List citations in square brackets referencing the source filename and page numbers, "
        "for example [Report.pdf p.3]. If the answer cannot be derived from the context, "
        "respond with 'I could not find the answer in the uploaded documents.'"
    )
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": (
                "Context:\n" + context + "\n\n" + "Question: " + question
            ),
        },
    ]


def _to_citations(results: List[dict]) -> List[Citation]:
    citations: List[Citation] = []
    for item in results:
        metadata = item["metadata"]
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
            )
        )
    return citations


def answer_question(payload: ChatRequest) -> ChatResponse:
    settings: Settings = get_settings()
    client = get_openai_client(settings)
    collection = get_collection()

    embedding = embed_query(payload.question)

    raw_results = query_collection(collection=collection, embedding=embedding, n_results=4)

    if not raw_results:
        return ChatResponse(
            answer="I could not find the answer in the uploaded documents.",
            citations=[],
        )

    context = _format_context(raw_results)
    messages = _build_prompt(payload.question, context)
    chat_completion = client.chat.completions.create(
        model=settings.chat_model,
        messages=messages,
        temperature=0.2,
    )

    answer_text = chat_completion.choices[0].message.content.strip()

    return ChatResponse(
        answer=answer_text,
        citations=_to_citations(raw_results),
    )


def _encode_event(payload: dict) -> bytes:
    return (json.dumps(jsonable_encoder(payload), separators=(",", ":")) + "\n").encode("utf-8")


def stream_answer(payload: ChatRequest) -> Generator[bytes, None, None]:
    question_key = _normalize_question(payload.question)
    cached = _answer_cache.get(question_key)

    if cached is not None:
        citations = cached.get("citations", [])
        if citations:
            yield _encode_event({"type": "references", "citations": citations})

        answer_chunks: Tuple[str, ...] = tuple(cached.get("answer_chunks", ()))
        emitted_delta = False
        for chunk in answer_chunks:
            if not chunk:
                continue
            emitted_delta = True
            yield _encode_event({"type": "delta", "content": chunk})

        cached_answer: str = cached.get("answer", "")
        if not emitted_delta and cached_answer:
            yield _encode_event({"type": "delta", "content": cached_answer})

        yield _encode_event(
            {
                "type": "done",
                "answer": cached_answer,
                "citations": citations,
            }
        )
        return

    settings: Settings = get_settings()
    client = get_openai_client(settings)
    collection = get_collection()

    embedding = embed_query(payload.question)
    raw_results = query_collection(collection=collection, embedding=embedding, n_results=4)

    if not raw_results:
        _answer_cache.set(
            question_key,
            {
                "answer": _NO_CONTEXT_MESSAGE,
                "answer_chunks": (_NO_CONTEXT_MESSAGE,),
                "citations": [],
            },
        )
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
    messages = _build_prompt(payload.question, context)

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
                if not delta:
                    continue
                content = getattr(delta, "content", None)
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

    _answer_cache.set(
        question_key,
        {
            "answer": answer_text,
            "answer_chunks": tuple(answer_parts),
            "citations": citations,
        },
    )
