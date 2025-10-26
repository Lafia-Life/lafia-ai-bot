const state = {
  documents: [],
  activePreview: null,
};

const THINKING_FRAMES = ["Thinking", "Thinking.", "Thinking..", "Thinking..."];

function $(selector) {
  return document.querySelector(selector);
}

function startThinkingAnimation(bubble) {
  stopThinkingAnimation(bubble);
  let frameIndex = 0;
  bubble.textContent = THINKING_FRAMES[frameIndex];
  const timerId = window.setInterval(() => {
    frameIndex = (frameIndex + 1) % THINKING_FRAMES.length;
    bubble.textContent = THINKING_FRAMES[frameIndex];
  }, 450);
  bubble.dataset.thinkingTimer = String(timerId);
}

function stopThinkingAnimation(bubble) {
  const timerId = bubble.dataset.thinkingTimer;
  if (timerId) {
    window.clearInterval(Number(timerId));
    delete bubble.dataset.thinkingTimer;
  }
}

function setModalOpen(isOpen) {
  document.body.classList.toggle("modal-open", Boolean(isOpen));
}

function clearPreviewUI() {
  const modal = $("#reference-modal");
  const frame = $("#reference-modal-frame");
  const title = $("#reference-modal-title");
  const action = $("#reference-modal-open");

  if (frame) {
    frame.src = "";
  }
  if (title) {
    title.textContent = "Document preview";
  }
  if (action) {
    action.classList.add("hidden");
    action.removeAttribute("href");
  }
  if (modal) {
    modal.classList.add("hidden");
  }
  setModalOpen(false);
  document.querySelectorAll(".reference-card.active").forEach((node) => {
    node.classList.remove("active");
  });
}

function showPdfPreview(citation, card) {
  const modal = $("#reference-modal");
  const frame = $("#reference-modal-frame");
  const title = $("#reference-modal-title");
  const action = $("#reference-modal-open");

  if (!modal || !frame || !title) {
    return;
  }

  document.querySelectorAll(".reference-card.active").forEach((node) => {
    node.classList.remove("active");
  });
  card.classList.add("active");

  const inlineUrl = `/documents/${citation.document_id}/inline#page=${citation.page_start}`;
  frame.src = inlineUrl;
  title.textContent = `${citation.filename} · page ${citation.page_start}`;
  if (action) {
    action.href = `/documents/${citation.document_id}/download`;
    action.classList.remove("hidden");
  }
  modal.classList.remove("hidden");
  setModalOpen(true);
  const closeButton = $("#reference-modal-close");
  closeButton?.focus();
  state.activePreview = {
    documentId: citation.document_id,
    pageStart: citation.page_start,
  };
}

function closePreviewModal() {
  clearPreviewUI();
  state.activePreview = null;
}

function renderDocuments(documents) {
  const list = $("#document-list");
  if (!list) {
    return;
  }
  list.innerHTML = "";

  if (documents.length === 0) {
    const empty = document.createElement("li");
    empty.textContent = "No documents indexed yet.";
    list.appendChild(empty);
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
    } else if (doc.source_type === "image") {
      const frameLabel = doc.page_count > 1 ? `${doc.page_count} frames` : "1 frame";
      meta.textContent = `Image · OCR extracted (${frameLabel})`;
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
  if (!status) {
    return;
  }
  status.style.color = "";
  status.textContent = "Uploading...";

  const formData = new FormData(form);
  try {
    const response = await fetch("/api/documents", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      const bodyText = await response.text();
      let message = `Upload failed (${response.status})`;
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
  if (!container) {
    throw new Error("Chat container not found");
  }
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${role}`;
  bubble.textContent = content;
  container.appendChild(bubble);
  container.scrollTop = container.scrollHeight;
  return bubble;
}

function renderReferences(citations) {
  const list = $("#reference-list");
  if (!list) {
    return;
  }
  const previousPreview = state.activePreview;
  clearPreviewUI();
  list.innerHTML = "";

  if (!citations || citations.length === 0) {
    const empty = document.createElement("p");
    empty.className = "reference-placeholder";
    empty.textContent = "No supporting references found yet.";
    list.appendChild(empty);
    state.activePreview = null;
    return;
  }

  const pdfEntries = new Map();

  for (const citation of citations) {
    const card = document.createElement("article");
    card.className = "reference-card";
    card.dataset.type = citation.source_type;

    const title = document.createElement("h4");
    title.textContent = citation.filename;

    const meta = document.createElement("p");
    meta.className = "reference-meta";
    const score = typeof citation.score === "number" ? citation.score.toFixed(2) : "n/a";
    let location;
    if (citation.source_type === "web") {
      location = `Section ${citation.page_start}`;
    } else if (citation.source_type === "image") {
      location = citation.page_start === citation.page_end
        ? `Image segment ${citation.page_start}`
        : `Image segments ${citation.page_start}-${citation.page_end}`;
    } else {
      location = `Pages ${citation.page_start}-${citation.page_end}`;
    }
    meta.textContent = `${location} · score ${score}`;

    const excerpt = document.createElement("p");
    excerpt.className = "reference-excerpt";
    excerpt.textContent = citation.excerpt || "No excerpt available.";

    card.append(title, meta, excerpt);

  if (citation.source_type === "pdf") {
      card.setAttribute("role", "button");
      card.tabIndex = 0;
      card.setAttribute(
        "aria-label",
        `Preview ${citation.filename} page ${citation.page_start}`,
      );

      const hint = document.createElement("p");
      hint.className = "reference-hint";
      hint.textContent = "Click to preview this PDF section.";
      card.appendChild(hint);

      const select = () => showPdfPreview(citation, card);
      card.addEventListener("click", select);
      card.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          select();
        }
      });

      const key = `${citation.document_id}:${citation.page_start}`;
      if (!pdfEntries.has(key)) {
        pdfEntries.set(key, select);
      }
    } else if (citation.source_type === "image") {
      const hint = document.createElement("p");
      hint.className = "reference-hint";
      hint.textContent = "OCR text extracted from uploaded image.";
      card.appendChild(hint);
    } else if (citation.url) {
      const link = document.createElement("a");
      link.className = "reference-link";
      link.href = citation.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "Open source";
      card.appendChild(link);
    }

    list.appendChild(card);
  }

  if (previousPreview) {
    const key = `${previousPreview.documentId}:${previousPreview.pageStart}`;
    const select = pdfEntries.get(key);
    if (select) {
      select();
    } else {
      state.activePreview = null;
    }
  }
}

async function handleScrape(event) {
  event.preventDefault();
  const form = event.target;
  const status = $("#scrape-status");
  if (!status) {
    return;
  }
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
  const textarea = form.querySelector("textarea[name='question']");
  const sendButton = form.querySelector("button[type='submit']");
  const chatStatus = $("#chat-status");
  const question = textarea?.value.trim() || "";

  if (!question) {
    return;
  }

  appendMessage("user", question);
  state.activePreview = null;
  clearPreviewUI();
  const referenceList = $("#reference-list");
  if (referenceList) {
    referenceList.innerHTML = "";
    const loading = document.createElement("p");
    loading.className = "reference-placeholder";
    loading.textContent = "Searching supporting passages...";
    referenceList.appendChild(loading);
  }

  const assistantBubble = appendMessage("assistant", "Thinking...");
  assistantBubble.dataset.placeholder = "true";
  startThinkingAnimation(assistantBubble);

  if (textarea) {
    textarea.value = "";
  }
  if (chatStatus) {
    chatStatus.style.color = "";
    chatStatus.textContent = "";
  }
  if (sendButton) {
    sendButton.disabled = true;
  }

  const clearPlaceholder = () => {
    stopThinkingAnimation(assistantBubble);
    if (assistantBubble.dataset.placeholder === "true") {
      assistantBubble.textContent = "";
      delete assistantBubble.dataset.placeholder;
    }
  };

  const decoder = new TextDecoder();
  let buffer = "";
  let isDone = false;

  const handleEvent = (payload) => {
    switch (payload.type) {
      case "delta": {
        if (payload.content) {
          clearPlaceholder();
          assistantBubble.textContent += payload.content;
          const container = $("#chat-messages");
          if (container) {
            container.scrollTop = container.scrollHeight;
          }
        }
        break;
      }
      case "references": {
        renderReferences(payload.citations);
        break;
      }
      case "done": {
        if (payload.answer) {
          clearPlaceholder();
          assistantBubble.textContent = payload.answer;
        } else {
          clearPlaceholder();
        }
        if (payload.citations) {
          renderReferences(payload.citations);
        }
        isDone = true;
        break;
      }
      case "error": {
        clearPlaceholder();
        const message = payload.message || "An error occurred while streaming the answer.";
        assistantBubble.textContent = message;
        if (chatStatus) {
          chatStatus.style.color = "#dc2626";
          chatStatus.textContent = message;
        }
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
    clearPlaceholder();
    const message = err instanceof Error ? err.message : "Chat request failed.";
    assistantBubble.textContent = message;
    if (chatStatus) {
      chatStatus.style.color = "#dc2626";
      chatStatus.textContent = message;
    }
  } finally {
    if (sendButton) {
      sendButton.disabled = false;
    }
    stopThinkingAnimation(assistantBubble);
    if (assistantBubble.dataset.placeholder === "true") {
      assistantBubble.textContent = "";
      delete assistantBubble.dataset.placeholder;
    }
  }
}

function setupVoiceRecognition() {
  
  const voiceBtn = document.getElementById('voice-btn');
  const questionInput = document.getElementById('question');
  const chatStatus = document.getElementById('chat-status');
  
  if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
    console.log("Speech recognition not supported");
    voiceBtn.disabled = true;
    return;
  }
  
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recognition = new SpeechRecognition();
  
  // IMPROVED ACCURACY SETTINGS
  recognition.continuous = false;
  recognition.lang = "en-US";
   // Enable real-time results
  recognition.interimResults = true;
   // Get more alternatives
  recognition.maxAlternatives = 5;
  
  let finalTranscript = '';
  let timeoutId;

  // Add ALL event listeners for debugging
  recognition.onstart = function() {
    if (chatStatus) chatStatus.textContent = "Listening... Speak clearly now 🎤";
     // Reset on start
    finalTranscript = '';
  };
  
  recognition.onresult = function(event) {    
    // Clear any existing timeout
    clearTimeout(timeoutId); 
    
    let interimTranscript = '';
    
    // Process all results
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];      
      
      if (result.isFinal) {
        // This is a final result
        const bestAlternative = getBestAlternative(result);
        finalTranscript = cleanTranscript(bestAlternative.transcript);
        console.log("Final transcript:", finalTranscript, "Confidence:", bestAlternative.confidence);
        
        if (questionInput) {
          questionInput.value = finalTranscript;
        }
        if (chatStatus) {
          const confidenceText = bestAlternative.confidence > 0.7 ? "High confidence" : 
                               bestAlternative.confidence > 0.4 ? "Medium confidence" : "Low confidence";
          chatStatus.textContent = `You said: "${finalTranscript}" (${confidenceText})`;
        }
        
        // Auto-submit only for high confidence
        if (bestAlternative.confidence > 0.6) {
          timeoutId = setTimeout(() => {
            console.log("🎤 Auto-submitting form...");
            const chatForm = document.getElementById('chat-form');
            if (chatForm) {
              const submitEvent = new Event('submit', { 
                bubbles: true, 
                cancelable: true 
              });
              chatForm.dispatchEvent(submitEvent);
              console.log("Submit event dispatched");
            }
          }, 1000);
        } else {
          // Low confidence - let user edit manually
          if (chatStatus) {
            chatStatus.textContent = `I heard: "${finalTranscript}" - Click Send if correct, or edit the text.`;
          }
          if (questionInput) {
            questionInput.focus();
          }
        }
        
      } else {
        // This is an interim result - show real-time feedback
        interimTranscript += result[0].transcript;
        if (chatStatus) {
          chatStatus.textContent = `Listening: ${interimTranscript}`;
        }
      }
    }
  };
  
  recognition.onerror = function(event) {
    console.error("🎤 Speech recognition error:", event.error);
    
    if (chatStatus) {
      const errorMessages = {
        'no-speech': 'No speech detected. Please try again.',
        'audio-capture': 'No microphone found. Please check your microphone.',
        'not-allowed': 'Microphone access denied. Please allow microphone access.',
        'network': 'Network error occurred. Please check your connection.'
      };
      chatStatus.textContent = errorMessages[event.error] || `Error: ${event.error}`;
    }
    voiceBtn.classList.remove('listening');
  };
  
  recognition.onend = function() {
    console.log("🎤 Speech recognition ENDED");
    voiceBtn.classList.remove('listening');
    
    // If no final transcript was captured but we have interim, use it
    if (!finalTranscript && questionInput.value) {
      finalTranscript = cleanTranscript(questionInput.value);
      questionInput.value = finalTranscript;
      if (chatStatus && !chatStatus.textContent.includes("You said:")) {
        chatStatus.textContent = `You said: "${finalTranscript}" - Click Send if correct.`;
      }
    }
  };
  
  voiceBtn.addEventListener('click', function(e) {
    e.preventDefault();
    e.stopPropagation();
    console.log("🎤 Voice button clicked!");
    
    if (voiceBtn.classList.contains('listening')) {
      console.log("🎤 Stopping recognition...");
      recognition.stop();
      voiceBtn.classList.remove('listening');
      if (chatStatus) chatStatus.textContent = "Stopped listening.";
    } else {
      console.log("🎤 Starting recognition...");
      // Clear previous input
      if (questionInput) questionInput.value = '';
      finalTranscript = '';
      
      try {
        recognition.start();
        voiceBtn.classList.add('listening');
        if (chatStatus) chatStatus.textContent = "Starting... Speak clearly 🎤";
      } catch (error) {
        console.error("🎤 Error starting recognition:", error);
        if (chatStatus) chatStatus.textContent = "Error starting voice recognition";
      }
    }
  });
  
  console.log("Voice recognition setup complete");
}

// HELPER FUNCTIONS FOR IMPROVED ACCURACY

function getBestAlternative(result) {
  // Return the alternative with highest confidence
  let best = result[0];
  for (let i = 1; i < result.length; i++) {
    if (result[i].confidence > best.confidence) {
      best = result[i];
    }
  }
  return best;
}

function cleanTranscript(transcript) {
  if (!transcript) return '';
  
  let cleaned = transcript;
  
  // Remove extra whitespace
  cleaned = cleaned.replace(/\s+/g, ' ').trim();
  
  // Common speech recognition corrections
  const corrections = {
    'whats': 'what is',
    'wheres': 'where is',
    'hows': 'how is',
    'whys': 'why is',
    'whens': 'when is',
    'whos': 'who is',
    'pdfs': 'PDFs',
    'ais': 'AIs',
    'llms': 'LLMs',
    'chat gpt': 'ChatGPT',
    'open ai': 'OpenAI',
    'google': 'Google',
    'amazon': 'Amazon',
    'microsoft': 'Microsoft'
  };
  
  // Apply corrections (case insensitive)
  Object.keys(corrections).forEach(wrong => {
    const regex = new RegExp('\\b' + wrong + '\\b', 'gi');
    cleaned = cleaned.replace(regex, corrections[wrong]);
  });
  
  // Capitalize first letter
  cleaned = cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
  
  // Smart punctuation
  const isQuestion = cleaned.toLowerCase().match(/^(what|how|why|when|where|who|can|could|would|should|is|are|does|do|will|may)\b/);
  const hasPunctuation = /[.?!]$/.test(cleaned);
  
  if (isQuestion && !hasPunctuation) {
    cleaned += '?';
  } else if (!hasPunctuation && cleaned.length > 10) {
    cleaned += '.';
  }
  
  console.log("Cleaned transcript:", cleaned);
  return cleaned;
}


window.addEventListener("DOMContentLoaded", () => {
  const uploadForm = $("#upload-form");
  const chatForm = $("#chat-form");
  const referenceList = $("#reference-list");
  const scrapeForm = $("#scrape-form");
  const referenceModal = $("#reference-modal");
  const modalClose = $("#reference-modal-close");  

  if (uploadForm) {
    uploadForm.addEventListener("submit", handleUpload);
  }

  if (scrapeForm) {
    scrapeForm.addEventListener("submit", handleScrape);
  }

  if (chatForm) {
    chatForm.addEventListener("submit", handleChat);
  }

  if (modalClose) {
    modalClose.addEventListener("click", closePreviewModal);
  }

  if (referenceModal) {
    referenceModal.addEventListener("click", (event) => {
      if (event.target === referenceModal) {
        closePreviewModal();
      }
    });
    window.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !referenceModal.classList.contains("hidden")) {
        closePreviewModal();
      }
    });
  }

  if (referenceList) {
    const placeholder = document.createElement("p");
    placeholder.className = "reference-placeholder";
    placeholder.textContent = "Ask a question to see supporting passages here.";
    referenceList.appendChild(placeholder);
  }
   // Setup voice recognition
  setupVoiceRecognition();

  fetchDocuments().catch((err) => console.error(err));
});
