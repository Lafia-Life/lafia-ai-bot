async function fetchDocuments() {
  const response = await fetch("/api/documents");
  if (!response.ok) {
    console.error("Failed to load documents");
    return;
  }
  const documents = await response.json();
  const list = document.getElementById("document-list");
  list.innerHTML = "";
  if (documents.length === 0) {
    const empty = document.createElement("li");
    empty.textContent = "No documents indexed yet.";
    list.appendChild(empty);
    return;
  }
  for (const doc of documents) {
    const item = document.createElement("li");
    item.textContent = `${doc.filename} – ${doc.page_count} pages`;
    list.appendChild(item);
  }
}

async function handleUpload(event) {
  event.preventDefault();
  const form = event.target;
  const status = document.getElementById("upload-status");
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

function formatCitations(citations) {
  if (!citations || citations.length === 0) {
    return "No supporting passages were found.";
  }
  return citations
    .map(
      (citation) =>
        `${citation.filename} (pages ${citation.page_start}-${citation.page_end}) · score ${citation.score}`,
    )
    .join("\n");
}

async function handleChat(event) {
  event.preventDefault();
  const responseContainer = document.getElementById("chat-response");
  responseContainer.textContent = "Thinking...";

  const formData = new FormData(event.target);
  const question = formData.get("question");

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
    const answer = payload.answer || "No answer provided.";
    const citations = formatCitations(payload.citations);
    responseContainer.textContent = `${answer}\n\nCitations:\n${citations}`;
  } catch (err) {
    responseContainer.textContent = err.message;
  }
}

window.addEventListener("DOMContentLoaded", () => {
  fetchDocuments().catch((err) => console.error(err));
  document.getElementById("upload-form").addEventListener("submit", handleUpload);
  document.getElementById("chat-form").addEventListener("submit", handleChat);
});
