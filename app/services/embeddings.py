from __future__ import annotations

from functools import lru_cache
from typing import Iterable, List, Sequence

from sentence_transformers import SentenceTransformer

from app.config import Settings, get_openai_client, get_settings


@lru_cache()
def _load_local_model(model_name: str) -> SentenceTransformer:
    # Normalize embeddings to improve cosine similarity behaviour inside Chroma.
    return SentenceTransformer(model_name, trust_remote_code=True, device="cpu")


def embed_with_local_model(texts: Sequence[str], model_name: str) -> List[List[float]]:
    model = _load_local_model(model_name)
    vectors = model.encode(list(texts), normalize_embeddings=True)
    return [vector.tolist() for vector in vectors]


def embed_with_openai(texts: Sequence[str], settings: Settings) -> List[List[float]]:
    client = get_openai_client(settings)
    response = client.embeddings.create(model=settings.embedding_model, input=list(texts))
    return [item.embedding for item in response.data]


def embed_texts(texts: Sequence[str]) -> List[List[float]]:
    if not texts:
        return []

    settings = get_settings()
    backend = settings.embedding_backend

    if backend == "openai":
        return embed_with_openai(texts, settings)

    return embed_with_local_model(texts, settings.local_embedding_model)


def embed_query(text: str) -> List[float]:
    vectors = embed_texts([text])
    return vectors[0]
