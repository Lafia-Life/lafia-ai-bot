from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache
from typing import List, Sequence


from app.config import Settings, get_openai_client, get_settings

HASH_EMBEDDING_DIMENSIONS = 384

_STOPWORDS = {
    "a", "about", "after", "all", "also", "am", "an", "and", "any", "are", "as",
    "at", "be", "because", "been", "before", "being", "but", "by", "can", "could",
    "did", "do", "does", "doing", "done", "for", "from", "had", "has", "have",
    "having", "he", "her", "here", "hers", "him", "his", "how", "i", "if", "in",
    "into", "is", "it", "its", "itself", "just", "me", "more", "most", "my", "no",
    "nor", "not", "of", "on", "once", "only", "or", "other", "our", "ours", "out",
    "over", "own", "same", "she", "should", "so", "some", "such", "than", "that",
    "the", "their", "theirs", "them", "then", "there", "these", "they", "this",
    "those", "through", "to", "too", "under", "until", "up", "very", "was", "we",
    "were", "what", "when", "where", "which", "while", "who", "whom", "why",
    "will", "with", "would", "you", "your", "yours", "tell", "know", "please",
}


def _stem(token: str) -> str:
    for suffix in ("ization", "isation", "ations", "ation", "ments", "ment", "ingly", "ions", "ion", "ing", "edly", "ed", "ies", "es", "ly", "s"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [_stem(token) for token in tokens if token not in _STOPWORDS and len(token) > 1]


def _hash_token(token: str, dimensions: int) -> tuple[int, float]:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    sign = 1.0 if (value >> 63) & 1 else -1.0
    return value % dimensions, sign


def embed_with_hash(texts: Sequence[str], dimensions: int = HASH_EMBEDDING_DIMENSIONS) -> List[List[float]]:
    """Lightweight, dependency-free embedding back-end.

    Uses hashed bag-of-words plus bigrams, normalised for cosine/L2 search.
    It is not as strong as a neural model, but it keeps Lafia usable on small
    servers and fully offline while still matching keywords and phrases well.
    """
    vectors: List[List[float]] = []
    for text in texts:
        vector = [0.0] * dimensions
        tokens = _tokenize(text)
        for token in tokens:
            index, sign = _hash_token(token, dimensions)
            vector[index] += sign
        for left, right in zip(tokens, tokens[1:]):
            index, sign = _hash_token(f"{left}_{right}", dimensions)
            vector[index] += 0.75 * sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        vectors.append([value / norm for value in vector])
    return vectors


@lru_cache()
def _load_local_model(model_name: str):
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Local embeddings require 'sentence-transformers'. "
            "Install it or set EMBEDDING_BACKEND=openai."
        ) from exc
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

    if backend == "local":
        return embed_with_local_model(texts, settings.local_embedding_model)

    return embed_with_hash(texts)


def embed_query(text: str) -> List[float]:
    vectors = embed_texts([text])
    return vectors[0]
