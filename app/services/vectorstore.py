from typing import Iterable, List, Sequence

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings as ChromaSettings

from app.config import get_settings


def get_collection() -> Collection:
    settings = get_settings()
    client = chromadb.PersistentClient(
        path=str(settings.chroma_path),
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    collection = client.get_or_create_collection(name="documents")
    return collection


def upsert_documents(
    collection: Collection,
    document_id: str,
    texts: Sequence[str],
    embeddings: Sequence[Sequence[float]],
    metadatas: Sequence[dict],
    ids: Sequence[str],
) -> None:
    if not texts:
        return
    collection.delete(where={"document_id": document_id})
    collection.add(
        documents=list(texts),
        embeddings=list(embeddings),
        metadatas=list(metadatas),
        ids=list(ids),
    )


def query_collection(
    collection: Collection,
    embedding: Sequence[float],
    n_results: int = 4,
) -> List[dict]:
    results = collection.query(
        query_embeddings=[list(embedding)],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )
    metadatas = results.get("metadatas", [[]])[0]
    documents = results.get("documents", [[]])[0]
    distances = results.get("distances", [[]])[0]
    combined = []
    for metadata, document, distance in zip(metadatas, documents, distances):
        if metadata is None:
            continue
        combined.append({
            "text": document,
            "metadata": metadata,
            "distance": float(distance) if distance is not None else 0.0,
        })
    return combined
