import os

# Keep tests offline and independent of local WHO caches or real provider keys.
os.environ.setdefault("WHO_SYNC_ON_STARTUP", "false")
os.environ.setdefault("EMBEDDING_BACKEND", "hash")
os.environ.setdefault("AUTH_REQUIRED", "false")
os.environ.setdefault("LLM_API_KEY", "test-key")
