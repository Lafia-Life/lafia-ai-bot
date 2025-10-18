const state = {
  documents: [],
};

function $(selector) {
  return document.querySelector(selector);
}

function showView(key) {
  const uploadView = $("#upload-view");
  const chatView = $("#chat-view");
  const navUpload = $("#nav-upload");
  const navChat = $("#nav-chat");

  if (key === "upload") {
    uploadView.classList.remove("hidden");
    chatView.classList.add("hidden");
    navUpload.classList.add("active");
    navChat.classList.remove("active");
  } else {
    uploadView.classList.add("hidden");
    chatView.classList.remove("hidden");
    navUpload.classList.remove("active");
    navChat.classList.add("active");
  }
}

function renderDocuments(documents) {
  const list = $("#document-list");
  list.innerHTML = "";

  if (documents.length === 0) {
    const empty = document.createElement("li");
    empty.textContent = "No documents indexed yet.";
    list.appendChild(empty);
    showView("upload");
    return;
  }

  for (const doc of documents) {
    const item = document.createElement("li");
    const name = document.createElement("span");
    name.textContent = doc.filename;
    const meta = document.createElement("span");
    meta.className = "document-meta";
    if (doc.source_type === "web") {
      meta.textContent = "Web source";
      if (doc.url) {
        try {
          const urlObj = new URL(doc.url);
          meta.textContent = `Web · ${urlObj.hostname}`;
        } catch (err) {
          meta.textContent = `Web · ${doc.url}`;
        }
      }
    } else {
      meta.textContent = `PDF · ${doc.page_count} pages`;
    }
    item.append(name, meta);
    list.appendChild(item);
  }
}

async function fetchDocuments() {
  try {
    const response = await fetch("/api/documents");
    if (!response.ok) {
      throw new Error("Failed to load documents");
    }
    const documents = await response.json();
    state.documents = documents;
    renderDocuments(documents);
  } catch (err) {
    console.error(err);
  }
}

async function handleUpload(event) {
  event.preventDefault();
  const form = event.target;
  const status = $("#upload-status");
  status.style.color = "";
  status.textContent = "Uploading...";

  const formData = new FormData(form);
  try {
    const response = await fetch("/api/documents", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Upload failed");
    }
    const payload = await response.json();
    status.textContent = `Uploaded ${payload.document.filename} (${payload.chunks_indexed} chunks).`;
    form.reset();
    await fetchDocuments();
  } catch (err) {
    status.textContent = err.message;
    status.style.color = "#dc2626";
  }
}

function appendMessage(role, content) {
  const container = $("#chat-messages");
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${role}`;
  bubble.textContent = content;
  container.appendChild(bubble);
  container.scrollTop = container.scrollHeight;
  return bubble;
}

function renderReferences(citations) {
  const list = $("#reference-list");
  list.innerHTML = "";

  if (!citations || citations.length === 0) {
    const empty = document.createElement("p");
    empty.className = "reference-placeholder";
    empty.textContent = "No supporting references found yet.";
    list.appendChild(empty);
    return;
  }

  for (const citation of citations) {
    const card = document.createElement("article");
    card.className = "reference-card";

    const title = document.createElement("h4");
    title.textContent = citation.filename;

    const meta = document.createElement("p");
    meta.className = "reference-meta";
    const score = typeof citation.score === "number" ? citation.score.toFixed(2) : "n/a";
    const location = citation.source_type === "web"
      ? `Section ${citation.page_start}`
      : `Pages ${citation.page_start}-${citation.page_end}`;
    meta.textContent = `${location} · score ${score}`;

    const excerpt = document.createElement("p");
    excerpt.className = "reference-excerpt";
    excerpt.textContent = citation.excerpt || "No excerpt available.";

    card.append(title, meta, excerpt);

    if (citation.url) {
      const link = document.createElement("a");
      link.className = "reference-link";
      link.href = citation.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = citation.url;
      card.appendChild(link);
    }

    list.appendChild(card);
  }
}

async function handleScrape(event) {
  event.preventDefault();
  const form = event.target;
  const status = $("#scrape-status");
  const input = form.querySelector("input[name='url']");
  const url = input.value.trim();
  if (!url) {
    return;
  }

  status.style.color = "";
  status.textContent = "Scraping...";

  try {
    const response = await fetch("/api/scrape", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (!response.ok) {
      const bodyText = await response.text();
      let message = "Scrape request failed";
      if (bodyText) {
        try {
          const errorPayload = JSON.parse(bodyText);
          message = errorPayload?.detail || message;
        } catch (parseErr) {
          message = bodyText;
        }
      }
      throw new Error(message);
    }
    const payload = await response.json();
    status.textContent = `Scraped and indexed "${payload.document.filename}".`;
    form.reset();
    await fetchDocuments();
  } catch (err) {
    status.style.color = "#dc2626";
    status.textContent = err instanceof Error ? err.message : "Scrape request failed.";
  }
}

async function handleChat(event) {
  event.preventDefault();
  const form = event.target;
  const chatStatus = $("#chat-status");
  const textarea = form.querySelector("textarea[name='question']");
  const sendButton = form.querySelector("button[type='submit']");
  const question = textarea.value.trim();

  if (!question) {
    return;
  }

  appendMessage("user", question);
  const assistantBubble = appendMessage("assistant", "");
  textarea.value = "";
  chatStatus.style.color = "";
  chatStatus.textContent = "Thinking...";
  sendButton.disabled = true;

  const decoder = new TextDecoder();
  let buffer = "";
  let isDone = false;

  const handleEvent = (payload) => {
    switch (payload.type) {
      case "delta": {
        if (payload.content) {
          assistantBubble.textContent += payload.content;
          const container = $("#chat-messages");
          container.scrollTop = container.scrollHeight;
        }
        break;
      }
      case "references": {
        renderReferences(payload.citations);
        break;
      }
      case "done": {
        if (payload.answer) {
          assistantBubble.textContent = payload.answer;
        }
        if (payload.citations) {
          renderReferences(payload.citations);
        }
        chatStatus.textContent = "";
        isDone = true;
        break;
      }
      case "error": {
        chatStatus.style.color = "#dc2626";
        chatStatus.textContent = payload.message || "An error occurred while streaming the answer.";
        isDone = true;
        break;
      }
      default:
        break;
    }
  };

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!response.ok) {
      const bodyText = await response.text();
      let message = "Chat request failed";
      if (bodyText) {
        try {
          const errorPayload = JSON.parse(bodyText);
          message = errorPayload?.detail || message;
        } catch (parseErr) {
          message = bodyText;
        }
      }
      throw new Error(message);
    }
    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error("Streaming not supported in this browser.");
    }

    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.trim()) {
          continue;
        }
        try {
          const payload = JSON.parse(line);
          handleEvent(payload);
        } catch (parseError) {
          console.error("Failed to parse stream chunk", parseError);
        }
      }
      if (isDone) {
        await reader.cancel();
        break;
      }
    }
    if (buffer.trim()) {
      try {
        const payload = JSON.parse(buffer.trim());
        handleEvent(payload);
      } catch (parseError) {
        console.error("Failed to parse trailing stream chunk", parseError);
      }
    }
  } catch (err) {
    chatStatus.style.color = "#dc2626";
    chatStatus.textContent = err instanceof Error ? err.message : "Chat request failed.";
  } finally {
    sendButton.disabled = false;
    if (!isDone && chatStatus.textContent === "Thinking...") {
      chatStatus.textContent = "";
    }
  }
}

window.addEventListener("DOMContentLoaded", () => {
  const uploadForm = $("#upload-form");
  const chatForm = $("#chat-form");
  const navUpload = $("#nav-upload");
  const navChat = $("#nav-chat");
  const startChatButton = $("#start-chat");
  const referenceList = $("#reference-list");
  const scrapeForm = $("#scrape-form");

  uploadForm.addEventListener("submit", handleUpload);
  chatForm.addEventListener("submit", handleChat);
  navUpload.addEventListener("click", () => showView("upload"));
  navChat.addEventListener("click", () => showView("chat"));
  startChatButton.addEventListener("click", () => showView("chat"));
  scrapeForm?.addEventListener("submit", handleScrape);

  showView("upload");
  const placeholder = document.createElement("p");
  placeholder.className = "reference-placeholder";
  placeholder.textContent = "Ask a question to see supporting passages here.";
  referenceList.appendChild(placeholder);
  fetchDocuments().catch((err) => console.error(err));
});
