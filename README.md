# PDF Chat Assistant MVP

Minimal FastAPI application that lets you upload PDF documents, indexes them with OpenAI (or local) embeddings + Chroma, and answer questions with citations referencing the original pages.

## Prerequisites

- Python 3.11+
- An LLM API key (OpenAI compatible, e.g. OpenAI or DeepSeek) if you want cloud completions. Without a key, the app still works with local embeddings but cannot generate answers.

## Quickstart

1. Create and activate a virtual environment.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy the environment template and add your API/base URL settings:

   ```bash
   cp .env.example .env
   # edit .env and set OPENAI_API_KEY (or DEEPSEEK_API_KEY), OPENAI_BASE_URL, CHAT_MODEL, etc.
   ```

4. Launch the API:

   ```bash
   uvicorn app.main:app --reload
   ```

5. Visit `http://127.0.0.1:8000` to upload PDFs and chat.

## How It Works

- **Upload**: PDFs are stored under `storage/uploads/`, parsed with `pypdf`, chunked into overlapping windows, and embedded via OpenAI or a local sentence-transformer model.
- **Index**: Embeddings and metadata (document id, filename, page numbers) are persisted in a local Chroma collection under `storage/chroma/`.
- **Chat**: A question is embedded, relevant chunks are retrieved, and the response is generated with the chosen chat model, returning citations for transparency.

## Environment Variables

| Name | Description |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI-compatible key (DeepSeek, etc). Leave empty to force local embeddings and disable remote chat. |
| `DEEPSEEK_API_KEY` | Optional alias for `OPENAI_API_KEY`. If set, overrides the value above. |
| `OPENAI_BASE_URL` | Optional. Set to `https://api.deepseek.com` (or another OpenAI-compatible endpoint). |
| `DEEPSEEK_BASE_URL` | Optional alias for `OPENAI_BASE_URL`. |
| `CHAT_MODEL` | Chat completion model (e.g. `gpt-4o-mini`, `deepseek-chat`). |
| `EMBEDDING_BACKEND` | `auto`, `openai`, or `local`. `auto` picks `openai` when a key is present, otherwise `local`. |
| `EMBEDDING_MODEL` | Used when `EMBEDDING_BACKEND=openai`. Defaults to `text-embedding-3-small`. |
| `LOCAL_EMBEDDING_MODEL` | Sentence Transformers model name (defaults to `all-MiniLM-L6-v2`). |

## DeepSeek Setup

To run with DeepSeek:

1. Set either `OPENAI_API_KEY` or `DEEPSEEK_API_KEY` in `.env` to your DeepSeek key (e.g. `sk-...`).
2. Set `OPENAI_BASE_URL=https://api.deepseek.com` (or `DEEPSEEK_BASE_URL` if you prefer the alias).
3. Set `CHAT_MODEL=deepseek-chat` (or `deepseek-coder`).
4. Set `EMBEDDING_BACKEND=local` so embeddings run locally (DeepSeek does not currently expose an embedding endpoint).

## Notes

- Delete `storage/chroma/` and `storage/uploads/` to reset the index.
- Adjust chunk size, overlap, or model names via `app/config.py`.
- When using local embeddings for the first time, the model download can take a minute.
