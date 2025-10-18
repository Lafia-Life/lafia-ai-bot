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
    const pages = document.createElement("span");
    pages.textContent = `${doc.page_count} pages`;
    item.append(name, pages);
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
    meta.textContent = `Pages ${citation.page_start}-${citation.page_end} · score ${score}`;

    const excerpt = document.createElement("p");
    excerpt.className = "reference-excerpt";
    excerpt.textContent = citation.excerpt || "No excerpt available.";

    card.append(title, meta, excerpt);
    list.appendChild(card);
  }
}

async function handleChat(event) {
  event.preventDefault();
  const form = event.target;
  const chatStatus = $("#chat-status");
  const textarea = form.querySelector("textarea[name='question']");
  const question = textarea.value.trim();

  if (!question) {
    return;
  }

  appendMessage("user", question);
  textarea.value = "";
  chatStatus.style.color = "";
  chatStatus.textContent = "Thinking...";

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Chat request failed");
    }
    const payload = await response.json();
    appendMessage("assistant", payload.answer || "No answer provided.");
    renderReferences(payload.citations);
    chatStatus.textContent = "";
  } catch (err) {
    chatStatus.style.color = "#dc2626";
    chatStatus.textContent = err.message;
  }
}

window.addEventListener("DOMContentLoaded", () => {
  const uploadForm = $("#upload-form");
  const chatForm = $("#chat-form");
  const navUpload = $("#nav-upload");
  const navChat = $("#nav-chat");
  const startChatButton = $("#start-chat");
  const referenceList = $("#reference-list");

  uploadForm.addEventListener("submit", handleUpload);
  chatForm.addEventListener("submit", handleChat);
  navUpload.addEventListener("click", () => showView("upload"));
  navChat.addEventListener("click", () => showView("chat"));
  startChatButton.addEventListener("click", () => showView("chat"));

  showView("upload");
  const placeholder = document.createElement("p");
  placeholder.className = "reference-placeholder";
  placeholder.textContent = "Ask a question to see supporting passages here.";
  referenceList.appendChild(placeholder);
  fetchDocuments().catch((err) => console.error(err));
});
