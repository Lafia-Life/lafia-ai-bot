# PDF Chat Assistant MVP

Minimal FastAPI application that lets you upload PDF documents (and now images with OCR), index them with OpenAI-compatible (or local) embeddings + Chroma, and ask streaming questions with source citations.

---

## Prerequisites

- Python 3.11+
- `git`
- An OpenAI-compatible API key (OpenAI, DeepSeek, etc.) if you want cloud completions. Without a key, the server can still ingest PDFs but cannot generate answers.
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed locally if you plan to ingest images outside Docker.

---

## Step-by-Step: Run the Server Locally

1. **Clone the repository**

   ```bash
   git clone https://github.com/egesamichael/chatlearning.git
   cd chatlearning
   ```

2. **Create a virtual environment**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**

   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Configure environment variables**

   ```bash
   cp .env.example .env
   # open .env in your editor and set OPENAI_API_KEY (or DEEPSEEK_API_KEY),
   # OPENAI_BASE_URL, CHAT_MODEL, etc.
   ```

5. **(Optional) Verify the code compiles**

   ```bash
   python -m compileall app
   ```

6. **Launch the FastAPI dev server**

   ```bash
   uvicorn app.main:app --reload
   ```

   A VS Code task named “Run FastAPI dev server” is already configured if you prefer running through the editor.

7. **Open the UI**

   - End users: [http://127.0.0.1:8000](http://127.0.0.1:8000) or `/chat` for the read-only chat experience.
   - Curators: [http://127.0.0.1:8000/upload](http://127.0.0.1:8000/upload) to manage PDFs or scrape web pages.

   Chat responses stream token-by-token, and supporting passages appear in the left panel. Use **Scrape URL** on the upload route when the content is not available as a PDF; the app will cite the source link in answers.

8. **Stop the server**

   Press `Ctrl+C` in the terminal (or stop the VS Code task) when you are finished.

---

## Run with Docker

1. **Build the image**

   ```bash
   docker build -t chatlearning:latest .
   ```

2. **Copy and edit environment file**

   ```bash
   cp .env.example .env
   # edit .env with your API key and preferred models
   ```

3. **Start the container**

   ```bash
   docker run --rm \
     --env-file .env \
     -p 8000:8000 \
     -v chatlearning_data:/app/storage \
     chatlearning:latest
   ```

   - `--env-file .env` passes your API key and configuration.
   - `-v chatlearning_data:/app/storage` keeps ingested documents and embeddings between runs (Docker named volume).

4. **Open the app**

   Browse to [http://127.0.0.1:8000](http://127.0.0.1:8000) just as with local development.

5. **Shutdown**

   Press `Ctrl+C` in the Docker terminal or run `docker stop <container-id>` from another shell.

---

## Run App + Ollama with Docker Compose

The included `docker-compose.yml` supports both remote and local LLM setups:

- **Remote (default)** – skips Ollama entirely and uses whatever API settings you supply in `.env`.
- **Local** – runs Ollama via a compose profile so the app can stay offline.

1. **Set up environment**

   ```bash
   cp .env.example .env
    # edit .env with the provider you want to use
   ```

2. **Choose a mode**

   - Remote (e.g. OpenAI/DeepSeek):

     ```bash
     docker compose up --build
     ```

   - Local Ollama:

     ```bash
       export OLLAMA_MODEL=llama3        # or phi3, mistral, etc.
       # ensure .env points OPENAI_BASE_URL to http://ollama:11434/v1 and sets CHAT_MODEL/EMBEDDING_BACKEND
     docker compose --profile local-llm up --build
     ```

     The first run pulls the selected Ollama model (several GB). Subsequent runs reuse the retained `ollama_data` volume.

3. **Access the UI**

   - Chat: [http://127.0.0.1:8000](http://127.0.0.1:8000)
   - Upload management: [http://127.0.0.1:8000/upload](http://127.0.0.1:8000/upload)

4. **Stop the stack**

   Use `Ctrl+C`, or run `docker compose down`. Append `--profile local-llm` if you started Ollama and want to stop just that profile. Add `--volumes` to remove stored embeddings/uploads/models.

---

## How It Works

- **Upload**: PDFs are stored under `storage/uploads/`, parsed with `pypdf`, chunked into overlapping windows, and embedded via OpenAI or a local SentenceTransformers model. Image uploads (`.png`, `.jpg`, `.jpeg`, `.tiff`, `.bmp`, `.webp`) are OCR’d with Tesseract before chunking so scans and screenshots are searchable too.
- **Web Scrape**: Fetches HTML with httpx + BeautifulSoup, strips boilerplate, chunks the cleaned article text, and stores citations with the original URL.
- **Index**: Embeddings and metadata (document id, filename, page numbers) are persisted in a local Chroma collection under `storage/chroma/`.
- **Chat**: A question is embedded, relevant chunks are retrieved, and the response is generated with the configured chat model. Answers stream back in real time, and citations include excerpts for quick preview.
- **Caching**: Recently asked questions are cached so repeated prompts return instantly without re-hitting the model.

---

## Environment Variables

| Name | Description |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI-compatible key (DeepSeek, etc.). Leave empty to disable remote chat. |
| `DEEPSEEK_API_KEY` | Optional alias for `OPENAI_API_KEY`. If set, overrides the value above. |
| `OPENAI_BASE_URL` | Optional. Set to `https://api.deepseek.com` (or any OpenAI-compatible endpoint). |
| `DEEPSEEK_BASE_URL` | Optional alias for `OPENAI_BASE_URL`. |
| `CHAT_MODEL` | Chat completion model (e.g. `gpt-4o-mini`, `deepseek-chat`). |
| `EMBEDDING_BACKEND` | `auto`, `openai`, or `local`. `auto` picks `openai` when a key is present. |
| `EMBEDDING_MODEL` | Used when `EMBEDDING_BACKEND=openai`. Defaults to `text-embedding-3-small`. |
| `LOCAL_EMBEDDING_MODEL` | SentenceTransformers model name (defaults to `all-MiniLM-L6-v2`). |

---

## DeepSeek Setup

1. Set either `OPENAI_API_KEY` or `DEEPSEEK_API_KEY` in `.env` to your DeepSeek key (e.g. `sk-...`).
2. Set `OPENAI_BASE_URL=https://api.deepseek.com` (or use the `DEEPSEEK_BASE_URL` alias).
3. Set `CHAT_MODEL=deepseek-chat` (or any other DeepSeek-compatible chat model).
4. Set `EMBEDDING_BACKEND=local` so embeddings run on the bundled SentenceTransformers model.

---

## Offline LLM Option (Ollama)

If you want the whole stack to run without internet access, you can host a local LLM that speaks the OpenAI API using [Ollama](https://ollama.com/):

1. **Install Ollama**

   - macOS / Linux: follow the instructions at [ollama.com/download](https://ollama.com/download).
   - Windows: use the official preview installer or run inside WSL.

2. **Pull a compatible model**

   ```bash
   ollama pull llama3
   ```

   Any OpenAI-compatible Ollama model works (e.g. `phi3`, `mistral`). Larger models need more RAM/VRAM.

3. **Start Ollama’s OpenAI bridge**

   Ollama exposes an OpenAI-style endpoint at `http://127.0.0.1:11434/v1` as soon as it’s running. Keep the Ollama service alive (e.g. `ollama serve`).

4. **Configure the app to use Ollama**

   Update `.env`:

   ```env
   OPENAI_API_KEY=dummy-key          # any non-empty string
   OPENAI_BASE_URL=http://127.0.0.1:11434/v1
   CHAT_MODEL=llama3
   EMBEDDING_BACKEND=local           # keeps embeddings offline
   ```

   Since Ollama does not require an API key, any placeholder value is fine.

5. **Run the app as usual**

   Launch `uvicorn` (or the Docker container with `--env-file .env`). The chat endpoint now streams responses from the local LLM, fully offline.

> **Note:** Ollama models can be several GB; download them once while you have connectivity. Performance depends on your CPU/GPU—the smaller models (`phi3:mini`, `llama3:instruct` 8B) offer a good balance for laptops.

---

## Maintenance Tips

- Delete `storage/chroma/` and `storage/uploads/` to reset the index.
- Adjust chunk size, overlap, or model names via `app/config.py`.
- Local embeddings download the first time you run them; allow a minute for the initial model pull.
- Clear the cache by restarting the server (cached answers are in-memory only).
