import json
from typing import Generator, List

from fastapi.encoders import jsonable_encoder

from app.config import Settings, get_openai_client, get_settings
from app.schemas import ChatRequest, ChatResponse, Citation
from app.services.embeddings import embed_query
from app.services.vectorstore import get_collection, query_collection


def _format_context(results: List[dict]) -> str:
    context_blocks = []
    for item in results:
        metadata = item["metadata"]
        text = item["text"]
        context_blocks.append(
            f"Source: {metadata['filename']} (pages {metadata['page_start']}-{metadata['page_end']})\n{text}"
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
        citations.append(
            Citation(
                document_id=metadata["document_id"],
                filename=metadata["filename"],
                page_start=metadata["page_start"],
                page_end=metadata["page_end"],
                score=round(similarity, 4),
                excerpt=excerpt,
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
    settings: Settings = get_settings()
    client = get_openai_client(settings)
    collection = get_collection()

    embedding = embed_query(payload.question)
    raw_results = query_collection(collection=collection, embedding=embedding, n_results=4)

    if not raw_results:
        yield _encode_event(
            {
                "type": "done",
                "answer": "I could not find the answer in the uploaded documents.",
                "citations": [],
            }
        )
        return

    citations = _to_citations(raw_results)
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
