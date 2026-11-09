/* Lafia Chat AI — responsive three-screen client */
(function () {
  "use strict";

  const LANGUAGES = [
    { code: "en", key: "language.en", recognition: "en-US", speech: "en" },
    { code: "sw", key: "language.sw", recognition: "sw-KE", speech: "sw" },
    { code: "lg", key: "language.lg", recognition: "lg-UG", speech: "lg" },
    { code: "ach", key: "language.ach", recognition: "ach-UG", speech: "ach" },
    { code: "teo", key: "language.teo", recognition: "teo-UG", speech: "teo" },
    { code: "xog", key: "language.xog", recognition: "xog-UG", speech: "xog" },
  ];

  // Neutral site for Quick exit. location.replace means Back cannot return here.
  const QUICK_EXIT_URL = "https://www.google.com";

  const KEYS = {
    language: "lafia.language.v1",
    consent: "lafia.consent.v1",
    saveChats: "lafia.saveChats.v1",
    chats: "lafia.chats.v1",
  };

  const state = {
    language: "en",
    screen: "consent",
    strings: {},
    fallback: {},
    messages: [],
    lastCitations: [],
    busy: false,
    saveChats: false,
    facilities: [],
    emergency: null,
    chw: null,
    location: null,
    speakingIndex: null,
    recognition: null,
    recognitionActive: false,
    lastEscape: 0,
  };

  const els = {};
  const HEART_MARK = '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 20s-7-4.1-7-9.4A4.4 4.4 0 0 1 12 7.7a4.4 4.4 0 0 1 7 2.9C19 15.9 12 20 12 20Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>';

  document.addEventListener("DOMContentLoaded", init);

  async function init() {
    cacheElements();
    // Remove conversation keys from the old prototype; chats must be opt-in.
    ["lafia.conversations.v1", "lafia.current.v1", "lafia.messages.v1"].forEach((key) => {
      try {
        localStorage.removeItem(key);
      } catch (error) {
        /* storage may be unavailable */
      }
    });
    await loadEnglish();
    state.language = localStorage.getItem(KEYS.language) || "en";
    await loadLanguage(state.language);
    applyTranslations();
    renderLanguageOptions();
    bindEvents();
    renderSaveToggles();
    setupSpeechRecognition();
    setupSpeechSynthesis();
    loadFacilities();

    const consent = readJson(KEYS.consent, null);
    if (consent && consent.accepted) {
      openChat();
    } else {
      showScreen("consent");
    }
  }

  function cacheElements() {
    [
      "screen-consent", "screen-chat", "screen-care",
      "language-select", "chat-language", "consent-check", "continue-btn",
      "messages", "welcome", "suggestions", "question", "chat-form",
      "mic-btn", "send-btn", "sources-btn", "open-sources", "privacy-btn",
      "quick-exit", "care-quick-exit", "find-care-btn", "care-back",
      "sources-list", "sources-list-mobile", "privacy-sheet", "sources-sheet",
      "source-sheet", "source-kind", "source-title", "source-meta",
      "source-excerpt", "source-actions", "facility-list", "location-btn",
      "location-status", "chw-btn", "emergency-btn", "emergency-number",
      "toast",
    ].forEach((id) => {
      els[id] = document.getElementById(id);
    });
  }

  /* ───────────────── i18n ───────────────── */

  async function loadEnglish() {
    state.fallback = await fetchJson("/static/i18n/en.json", {});
  }

  async function loadLanguage(code) {
    if (code === "en") {
      state.strings = { ...state.fallback };
      return;
    }
    const data = await fetchJson(`/static/i18n/${code}.json`, {});
    state.strings = { ...state.fallback, ...data };
  }

  function t(key, vars) {
    let value = state.strings[key] ?? state.fallback[key] ?? key;
    if (vars) {
      Object.keys(vars).forEach((name) => {
        value = value.replace(new RegExp(`\\{${name}\\}`, "g"), String(vars[name]));
      });
    }
    return value;
  }

  function applyTranslations() {
    document.title = t("app.title");
    document.documentElement.lang = state.language;
    document.querySelectorAll("[data-i18n]").forEach((node) => {
      node.textContent = t(node.dataset.i18n);
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
      node.setAttribute("placeholder", t(node.dataset.i18nPlaceholder));
    });
    document.querySelectorAll("[data-i18n-aria]").forEach((node) => {
      node.setAttribute("aria-label", t(node.dataset.i18nAria));
    });
    renderLanguageOptions();
  }

  function renderLanguageOptions() {
    [els["language-select"], els["chat-language"]].forEach((select) => {
      if (!select) return;
      const current = state.language;
      select.innerHTML = "";
      LANGUAGES.forEach((language) => {
        const option = document.createElement("option");
        option.value = language.code;
        option.textContent = t(language.key);
        select.appendChild(option);
      });
      select.value = current;
      select.setAttribute("aria-label", t("chat.language"));
    });
  }

  async function changeLanguage(code) {
    if (!LANGUAGES.some((language) => language.code === code)) return;
    state.language = code;
    localStorage.setItem(KEYS.language, code);
    await loadLanguage(code);
    cancelSpeech();
    applyTranslations();
    renderSuggestions();
    if (!state.busy) renderMessages();
    renderSources();
    renderFacilities();
    renderSaveToggles();
    refreshListenButtons();
  }

  /* ───────────────── screens and consent ───────────────── */

  function showScreen(name) {
    state.screen = name;
    ["consent", "chat", "care"].forEach((screen) => {
      const node = els[`screen-${screen}`];
      if (node) node.hidden = screen !== name;
    });
    closeSheets();
    if (name === "chat" && window.matchMedia("(min-width: 900px)").matches) {
      window.requestAnimationFrame(() => els.question?.focus());
    }
  }

  function openChat() {
    showScreen("chat");
    if (state.saveChats && state.messages.length === 0) {
      restoreSavedChats();
    }
    if (state.messages.length) {
      hideWelcome();
      renderMessages();
      scrollToBottom();
    } else {
      showWelcome();
    }
    refreshListenButtons();
  }

  function acceptConsent() {
    if (!els["consent-check"].checked) return;
    localStorage.setItem(
      KEYS.consent,
      JSON.stringify({ accepted: true, version: 1, at: Date.now() })
    );
    openChat();
  }

  /* ───────────────── chat ───────────────── */

  function renderSuggestions() {
    const keys = ["chat.suggestion1", "chat.suggestion2", "chat.suggestion3", "chat.suggestion4"];
    els.suggestions.innerHTML = "";
    keys.forEach((key) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "suggestion";
      button.innerHTML = `<span aria-hidden="true">${HEART_MARK}</span><span>${escapeHtml(t(key))}</span>`;
      button.addEventListener("click", () => {
        els.question.value = t(key);
        autoResize();
        submitQuestion();
      });
      els.suggestions.appendChild(button);
    });
  }

  function showWelcome() {
    els.welcome?.classList.remove("hidden");
    renderSuggestions();
  }

  function hideWelcome() {
    els.welcome?.classList.add("hidden");
  }

  function renderMessages() {
    els.messages.querySelectorAll(".message").forEach((node) => node.remove());
    if (!state.messages.length) {
      showWelcome();
      return;
    }
    hideWelcome();
    state.messages.forEach((message, index) => renderMessage(message, index));
  }

  function renderMessage(message, index) {
    const article = document.createElement("article");
    article.className = `message ${message.role}`;
    article.dataset.index = String(index);

    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.innerHTML =
      message.role === "assistant"
        ? '<img src="/static/brand/lafia-mark.png" alt="" />'
        : t("chat.you");

    const main = document.createElement("div");
    main.className = "message-main";

    const author = document.createElement("p");
    author.className = "message-author";
    author.textContent = message.role === "assistant" ? t("chat.lafia") : t("chat.you");

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    if (message.pending) {
      bubble.innerHTML = '<span class="typing" aria-label="' + escapeHtml(t("chat.typing")) + '"><span></span><span></span><span></span></span>';
    } else {
      bubble.innerHTML = mdToHtml(message.content || "");
      if (message.error) bubble.classList.add("error");
    }

    main.append(author, bubble);
    article.append(avatar, main);
    els.messages.appendChild(article);

    if (!message.pending && message.role === "assistant" && !message.error) {
      renderMessageSources(article, message.citations || []);
      renderMessageActions(article, index);
    }
    return article;
  }

  function renderMessageSources(article, citations) {
    const main = article.querySelector(".message-main");
    main.querySelector(".source-chips")?.remove();
    if (!citations || !citations.length) return;

    const wrap = document.createElement("div");
    wrap.className = "source-chips";
    const seen = new Set();
    citations
      .filter((citation) => {
        const key = citation.document_id || citation.filename;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .slice(0, 3)
      .forEach((citation) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "source-chip";
      button.innerHTML =
        '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 5.5A1.5 1.5 0 0 1 6.5 4H11v16H6.5A1.5 1.5 0 0 1 5 18.5v-13ZM13 4h4.5A1.5 1.5 0 0 1 19 5.5v13a1.5 1.5 0 0 1-1.5 1.5H13V4Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>' +
        `<span>${escapeHtml(citation.filename || t("chat.sources"))}</span>`;
      button.addEventListener("click", () => openSource(citation));
      wrap.appendChild(button);
    });
    main.appendChild(wrap);
  }

  function renderMessageActions(article, index) {
    const main = article.querySelector(".message-main");
    main.querySelector(".message-actions")?.remove();
    const actions = document.createElement("div");
    actions.className = "message-actions";

    const listen = document.createElement("button");
    listen.type = "button";
    listen.className = "answer-action listen-btn";
    listen.dataset.index = String(index);
    listen.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 10v4h4l4 4V6L8 10H4Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M15 9.5a3.5 3.5 0 0 1 0 5M17.5 7a7 7 0 0 1 0 10" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>' +
      `<span>${escapeHtml(t("chat.listen"))}</span>`;
    listen.setAttribute("aria-label", t("chat.listenAria"));
    listen.addEventListener("click", () => speakMessage(index));
    if (!getVoiceForLanguage()) listen.hidden = true;
    actions.appendChild(listen);
    main.appendChild(actions);
  }

  async function submitQuestion() {
    const question = els.question.value.trim();
    if (!question || state.busy) return;
    if (!state.saveChats) {
      // never write chats to storage while saving is off
      localStorage.removeItem(KEYS.chats);
    }

    const history = state.messages
      .filter((message) => !message.pending && message.content)
      .slice(-10)
      .map((message) => ({ role: message.role, content: message.content }));

    els.question.value = "";
    autoResize();
    state.busy = true;
    els["send-btn"].disabled = true;
    hideWelcome();

    const userMessage = { role: "user", content: question, ts: Date.now() };
    state.messages.push(userMessage);
    renderMessage(userMessage, state.messages.length - 1);

    const assistantMessage = {
      role: "assistant",
      content: "",
      citations: [],
      pending: true,
      ts: Date.now(),
    };
    state.messages.push(assistantMessage);
    const article = renderMessage(assistantMessage, state.messages.length - 1);
    const bubble = article.querySelector(".bubble");
    scrollToBottom();

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          language: state.language,
          history,
        }),
      });

      if (!response.ok) {
        throw new Error(t("chat.error"));
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error(t("chat.error"));

      const decoder = new TextDecoder();
      let buffer = "";
      let finished = false;
      let scheduled = false;

      const paint = () => {
        if (scheduled) return;
        scheduled = true;
        window.requestAnimationFrame(() => {
          scheduled = false;
          bubble.innerHTML = mdToHtml(assistantMessage.content);
          scrollToBottom();
        });
      };

      while (!finished) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line);
          if (event.type === "delta" && event.content) {
            assistantMessage.content += event.content;
            paint();
          } else if (event.type === "references" && Array.isArray(event.citations)) {
            assistantMessage.citations = event.citations;
          } else if (event.type === "done") {
            if (event.answer) assistantMessage.content = event.answer;
            if (Array.isArray(event.citations)) assistantMessage.citations = event.citations;
            finished = true;
          } else if (event.type === "error") {
            throw new Error(t("chat.error"));
          }
        }
      }
      if (buffer.trim()) {
        const event = JSON.parse(buffer.trim());
        if (event.type === "done") {
          if (event.answer) assistantMessage.content = event.answer;
          if (Array.isArray(event.citations)) assistantMessage.citations = event.citations;
        }
      }

      assistantMessage.pending = false;
      assistantMessage.ts = Date.now();
      assistantMessage.citations = preferCited(
        assistantMessage.citations,
        assistantMessage.content
      );
      bubble.innerHTML = mdToHtml(assistantMessage.content || t("chat.error"));
      renderMessageSources(article, assistantMessage.citations);
      renderMessageActions(article, state.messages.length - 1);
      setLastCitations(assistantMessage.citations);
    } catch (error) {
      assistantMessage.pending = false;
      assistantMessage.error = true;
      assistantMessage.content = t("chat.error");
      bubble.classList.add("error");
      bubble.textContent = t("chat.error");
    } finally {
      state.busy = false;
      els["send-btn"].disabled = false;
      assistantMessage.pending = false;
      saveChatsIfEnabled();
      scrollToBottom();
      els.question.focus();
    }
  }

  function preferCited(citations, content) {
    if (!citations?.length) return [];
    const text = String(content || "").toLowerCase();
    const bracketText = (text.match(/\[[^\]]+\]/g) || []).join(" ");
    if (bracketText) {
      const direct = citations.filter((citation) =>
        bracketText.includes(String(citation.filename || "").toLowerCase())
      );
      if (direct.length) return direct;
      const keywords = citations.filter((citation) =>
        String(citation.filename || "")
          .toLowerCase()
          .replace("who - ", "")
          .split(/[^a-z]+/)
          .filter((word) => word.length > 5)
          .some((word) => bracketText.includes(word))
      );
      if (keywords.length) return keywords;
    }
    const byName = citations.filter((citation) =>
      text.includes(String(citation.filename || "").toLowerCase())
    );
    return byName.length ? byName : citations;
  }

  function setLastCitations(citations) {
    state.lastCitations = Array.isArray(citations) ? citations : [];
    renderSources();
  }

  function renderSources() {
    const citations = state.lastCitations || [];
    renderSourceCards(els["sources-list"], citations);
    renderSourceCards(els["sources-list-mobile"], citations);
  }

  function renderSourceCards(container, citations) {
    if (!container) return;
    container.innerHTML = "";
    if (!citations.length) {
      const empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = t("chat.sourcesEmpty");
      container.appendChild(empty);
      return;
    }
    citations.forEach((citation) => {
      const card = document.createElement("article");
      card.className = "source-card";
      const button = document.createElement("button");
      button.type = "button";
      button.innerHTML =
        `<h3>${escapeHtml(citation.filename || t("chat.sources"))}</h3>` +
        `<p>${escapeHtml(sourceLocation(citation))}</p>` +
        `<p class="excerpt">${escapeHtml(citation.excerpt || "")}</p>`;
      button.addEventListener("click", () => openSource(citation));
      card.appendChild(button);
      container.appendChild(card);
    });
  }

  function sourceLocation(citation) {
    if (citation.source_type === "who" || citation.source_type === "web") {
      return `${t("chat.section")} ${citation.page_start || 1}`;
    }
    const start = citation.page_start || 1;
    const end = citation.page_end || start;
    return start === end ? `${t("chat.page")} ${start}` : `${t("chat.page")} ${start}–${end}`;
  }

  function openSource(citation) {
    els["source-kind"].textContent =
      citation.source_type === "who" ? t("chat.whoSource") : t("chat.documentSource");
    els["source-title"].textContent = citation.filename || t("chat.sources");
    els["source-meta"].textContent = sourceLocation(citation);
    els["source-excerpt"].textContent = citation.excerpt || "";
    els["source-actions"].innerHTML = "";

    if (citation.url) {
      const link = document.createElement("a");
      link.href = citation.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = citation.url;
      els["source-actions"].appendChild(link);
    }
    if (citation.source_type === "pdf" && citation.document_id) {
      const preview = document.createElement("a");
      preview.href = `/documents/${encodeURIComponent(citation.document_id)}/inline#page=${citation.page_start || 1}`;
      preview.target = "_blank";
      preview.rel = "noopener noreferrer";
      preview.textContent = `${t("chat.page")} ${citation.page_start || 1}`;
      els["source-actions"].appendChild(preview);
    }
    openSheet("source-sheet");
  }

  /* ───────────────── saving and deletion ───────────────── */

  function saveChatsIfEnabled() {
    if (!state.saveChats) return;
    const messages = state.messages
      .filter((message) => !message.pending)
      .map(({ role, content, citations, ts, error }) => ({ role, content, citations, ts, error }));
    try {
      localStorage.setItem(
        KEYS.chats,
        JSON.stringify({ version: 1, updatedAt: Date.now(), messages })
      );
    } catch (error) {
      // Storage may be unavailable in private mode; chat still works in memory.
    }
  }

  function restoreSavedChats() {
    const saved = readJson(KEYS.chats, null);
    if (!saved || !Array.isArray(saved.messages)) return;
    state.messages = saved.messages;
    const lastAssistant = [...saved.messages].reverse().find((message) => message.role === "assistant");
    state.lastCitations = lastAssistant?.citations || [];
  }

  function setSaveChats(enabled) {
    state.saveChats = Boolean(enabled);
    localStorage.setItem(KEYS.saveChats, String(state.saveChats));
    if (state.saveChats) {
      saveChatsIfEnabled();
      toast(t("chat.savingOn"));
    } else {
      localStorage.removeItem(KEYS.chats);
      toast(t("chat.savingOff"));
    }
    renderSaveToggles();
  }

  function renderSaveToggles() {
    document.querySelectorAll(".js-save-toggle").forEach((toggle) => {
      toggle.checked = state.saveChats;
    });
  }

  function deleteChats() {
    if (!window.confirm(t("chat.deleteConfirm"))) return;
    localStorage.removeItem(KEYS.chats);
    state.messages = [];
    state.lastCitations = [];
    renderMessages();
    renderSources();
    closeSheets();
    toast(t("chat.deleted"));
  }

  /* ───────────────── quick exit ───────────────── */

  function quickExit() {
    try {
      state.messages = [];
      state.lastCitations = [];
      localStorage.removeItem(KEYS.chats);
      cancelSpeech();
      if (state.recognition) state.recognition.abort();
    } catch (error) {
      /* continue to the neutral site */
    }
    window.location.replace(QUICK_EXIT_URL);
  }

  function handleEscape(event) {
    if (event.key !== "Escape") return;
    const now = Date.now();
    if (now - state.lastEscape < 1500) {
      event.preventDefault();
      quickExit();
      return;
    }
    state.lastEscape = now;
    if (hasOpenSheet()) {
      closeSheets();
      return;
    }
    toast(t("chat.pressEscAgain"));
  }

  /* ───────────────── find care ───────────────── */

  async function loadFacilities() {
    const data = await fetchJson("/data/facilities.json", null);
    if (!data) {
      if (els["facility-list"]) {
        els["facility-list"].innerHTML = `<p class="hint">${escapeHtml(t("care.noFacilities"))}</p>`;
      }
      return;
    }
    state.facilities = Array.isArray(data.facilities) ? data.facilities : [];
    state.emergency = data.emergency || null;
    state.chw = data.chw || null;
    if (state.emergency) {
      const tel = state.emergency.tel || "112";
      els["emergency-btn"].href = `tel:${tel}`;
      els["emergency-number"].textContent = state.emergency.display || tel;
    }
    renderFacilities();
  }

  function renderFacilities() {
    const list = els["facility-list"];
    if (!list) return;
    let facilities = [...state.facilities];
    if (state.location) {
      facilities = facilities
        .map((facility) => ({
          ...facility,
          distance: haversineKm(
            state.location.lat,
            state.location.lon,
            Number(facility.latitude),
            Number(facility.longitude)
          ),
        }))
        .sort((a, b) => a.distance - b.distance);
    }
    list.innerHTML = "";
    if (!facilities.length) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = t("care.noFacilities");
      list.appendChild(empty);
      return;
    }
    facilities.forEach((facility) => {
      const card = document.createElement("article");
      card.className = "facility-card";
      const distance =
        typeof facility.distance === "number"
          ? t("care.distanceAway", { distance: facility.distance.toFixed(1) })
          : t("care.distanceUnknown");
      card.innerHTML =
        `<div class="facility-top"><div><h3>${escapeHtml(facility.name)}</h3>` +
        `<p class="facility-type">${escapeHtml(facility.type || "")}</p></div>` +
        `<span class="distance-badge">${escapeHtml(distance)}</span></div>` +
        `<p class="facility-meta"><strong>${escapeHtml(t("care.hours"))}:</strong> ${escapeHtml(facility.hours || "")}<br>` +
        `${escapeHtml(facility.address || "")}</p>` +
        `<a class="facility-call" href="tel:${String(facility.phone || "").replace(/[^\d+]/g, "")}" ` +
        `aria-label="${escapeHtml(t("care.callAria"))}: ${escapeHtml(facility.name)}">` +
        `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M6.6 4.5h2.8l1.4 3.5-1.9 1.4a12 12 0 0 0 5.7 5.7l1.4-1.9 3.5 1.4v2.8a2 2 0 0 1-2.2 2A16 16 0 0 1 4.6 6.7a2 2 0 0 1 2-2.2Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>` +
        `${escapeHtml(t("care.call"))} · ${escapeHtml(facility.phone || "")}</a>`;
      list.appendChild(card);
    });
  }

  function useLocation() {
    if (!navigator.geolocation) {
      els["location-status"].textContent = t("care.locationUnsupported");
      return;
    }
    els["location-btn"].disabled = true;
    els["location-status"].textContent = t("common.loading");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        state.location = {
          lat: position.coords.latitude,
          lon: position.coords.longitude,
        };
        renderFacilities();
        els["location-status"].textContent = t("care.locationHint");
        els["location-btn"].disabled = false;
      },
      () => {
        els["location-status"].textContent = t("care.locationDenied");
        els["location-btn"].disabled = false;
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 0 }
    );
  }

  function haversineKm(lat1, lon1, lat2, lon2) {
    if ([lat1, lon1, lat2, lon2].some((value) => Number.isNaN(value))) return 0;
    const R = 6371;
    const dLat = ((lat2 - lat1) * Math.PI) / 180;
    const dLon = ((lon2 - lon1) * Math.PI) / 180;
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos((lat1 * Math.PI) / 180) *
        Math.cos((lat2 * Math.PI) / 180) *
        Math.sin(dLon / 2) ** 2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  /* ───────────────── speech output ───────────────── */

  function setupSpeechSynthesis() {
    if (!("speechSynthesis" in window)) return;
    if (typeof window.speechSynthesis.addEventListener === "function") {
      window.speechSynthesis.addEventListener("voiceschanged", refreshListenButtons);
    }
    window.speechSynthesis.onvoiceschanged = refreshListenButtons;
    refreshListenButtons();
  }

  function getVoiceForLanguage() {
    if (!("speechSynthesis" in window)) return null;
    const language = LANGUAGES.find((item) => item.code === state.language) || LANGUAGES[0];
    const voices = window.speechSynthesis.getVoices();
    if (!voices.length) return null;
    return (
      voices.find((voice) => voice.lang?.toLowerCase().replace("_", "-").startsWith(language.speech)) ||
      (language.code === "en"
        ? voices.find((voice) => voice.lang?.toLowerCase().startsWith("en"))
        : null)
    );
  }

  function refreshListenButtons() {
    document.querySelectorAll(".listen-btn").forEach((button) => {
      button.hidden = !getVoiceForLanguage();
    });
  }

  function speakMessage(index) {
    const message = state.messages[index];
    if (!message || !message.content) return;
    if (!("speechSynthesis" in window)) {
      toast(t("chat.voiceUnavailable"));
      return;
    }
    const voice = getVoiceForLanguage();
    if (!voice) {
      toast(t("chat.voiceUnavailable"));
      return;
    }
    if (state.speakingIndex === index) {
      cancelSpeech();
      return;
    }
    cancelSpeech();
    const utterance = new SpeechSynthesisUtterance(stripMarkdown(message.content));
    utterance.voice = voice;
    utterance.lang = voice.lang;
    utterance.rate = 0.95;
    utterance.onend = () => {
      state.speakingIndex = null;
      updateSpeakingButtons();
    };
    utterance.onerror = () => {
      state.speakingIndex = null;
      updateSpeakingButtons();
    };
    state.speakingIndex = index;
    updateSpeakingButtons();
    window.speechSynthesis.speak(utterance);
  }

  function cancelSpeech() {
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    state.speakingIndex = null;
    updateSpeakingButtons();
  }

  function updateSpeakingButtons() {
    document.querySelectorAll(".listen-btn").forEach((button) => {
      const active = Number(button.dataset.index) === state.speakingIndex;
      const label = active ? t("chat.stop") : t("chat.listen");
      button.querySelector("span").textContent = label;
      button.setAttribute("aria-label", active ? t("chat.stop") : t("chat.listenAria"));
      button.classList.toggle("speaking", active);
    });
    refreshListenButtons();
  }

  /* ───────────────── speech input ───────────────── */

  function setupSpeechRecognition() {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) {
      els["mic-btn"].addEventListener("click", () => toast(t("chat.micUnsupported")));
      return;
    }
    const recognition = new Recognition();
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    state.recognition = recognition;

    const stop = () => {
      state.recognitionActive = false;
      els["mic-btn"].classList.remove("recording");
      try {
        recognition.stop();
      } catch (error) {
        /* noop */
      }
    };

    els["mic-btn"].addEventListener("click", () => {
      if (state.recognitionActive) {
        stop();
        return;
      }
      const language = LANGUAGES.find((item) => item.code === state.language) || LANGUAGES[0];
      recognition.lang = language.recognition;
      try {
        recognition.start();
        state.recognitionActive = true;
        els["mic-btn"].classList.add("recording");
      } catch (error) {
        toast(t("chat.micUnsupported"));
      }
    });

    recognition.addEventListener("result", (event) => {
      const transcript = event.results?.[0]?.[0]?.transcript || "";
      if (transcript) {
        els.question.value = transcript;
        autoResize();
        els.question.focus();
      }
    });
    recognition.addEventListener("end", stop);
    recognition.addEventListener("error", () => {
      stop();
      toast(t("chat.micDenied"));
    });
  }

  /* ───────────────── UI helpers ───────────────── */

  function bindEvents() {
    els["consent-check"].addEventListener("change", () => {
      els["continue-btn"].disabled = !els["consent-check"].checked;
    });
    els["continue-btn"].addEventListener("click", acceptConsent);
    els["language-select"].addEventListener("change", (event) => changeLanguage(event.target.value));
    els["chat-language"].addEventListener("change", (event) => changeLanguage(event.target.value));

    els["chat-form"].addEventListener("submit", (event) => {
      event.preventDefault();
      submitQuestion();
    });
    els.question.addEventListener("input", autoResize);
    els.question.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        submitQuestion();
      }
    });

    els["quick-exit"].addEventListener("click", quickExit);
    els["care-quick-exit"].addEventListener("click", quickExit);
    document.querySelectorAll("[data-quick-exit]").forEach((button) => {
      button.addEventListener("click", quickExit);
    });

    els["privacy-btn"].addEventListener("click", () => openSheet("privacy-sheet"));
    els["sources-btn"].addEventListener("click", () => openSheet("sources-sheet"));
    els["open-sources"].addEventListener("click", () => openSheet("sources-sheet"));
    document.querySelectorAll("[data-close-sheet]").forEach((button) => {
      button.addEventListener("click", closeSheets);
    });

    document.querySelectorAll(".js-save-toggle").forEach((toggle) => {
      toggle.addEventListener("change", (event) => setSaveChats(event.target.checked));
    });
    document.querySelectorAll(".js-delete-chats").forEach((button) => {
      button.addEventListener("click", deleteChats);
    });

    els["find-care-btn"].addEventListener("click", () => {
      showScreen("care");
      renderFacilities();
    });
    els["care-back"].addEventListener("click", () => showScreen("chat"));
    els["location-btn"].addEventListener("click", useLocation);
    els["chw-btn"].addEventListener("click", () => toast(t("care.chwNotConnected")));

    document.addEventListener("keydown", handleEscape);
    window.addEventListener("pagehide", () => {
      cancelSpeech();
    });
  }

  function openSheet(id) {
    closeSheets();
    const sheet = els[id];
    if (sheet) sheet.hidden = false;
  }

  function closeSheets() {
    ["privacy-sheet", "sources-sheet", "source-sheet"].forEach((id) => {
      if (els[id]) els[id].hidden = true;
    });
  }

  function hasOpenSheet() {
    return ["privacy-sheet", "sources-sheet", "source-sheet"].some(
      (id) => els[id] && !els[id].hidden
    );
  }

  function autoResize() {
    const textarea = els.question;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 140)}px`;
  }

  function scrollToBottom() {
    els.messages.scrollTop = els.messages.scrollHeight;
  }

  let toastTimer = null;
  function toast(message) {
    if (!els.toast) return;
    els.toast.textContent = message;
    els.toast.hidden = false;
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => {
      els.toast.hidden = true;
    }, 3800);
  }

  function mdToHtml(markdown) {
    if (!markdown) return "";
    const escaped = escapeHtml(String(markdown).replace(/\r\n/g, "\n"));
    const lines = escaped.split("\n");
    const html = [];
    let listType = null;
    const closeList = () => {
      if (listType) {
        html.push(`</${listType}>`);
        listType = null;
      }
    };
    for (const rawLine of lines) {
      const line = rawLine.trimEnd();
      if (!line.trim()) {
        closeList();
        continue;
      }
      const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
      const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
      if (bullet) {
        if (listType !== "ul") {
          closeList();
          listType = "ul";
          html.push("<ul>");
        }
        html.push(`<li>${inlineMd(bullet[1])}</li>`);
        continue;
      }
      if (numbered) {
        if (listType !== "ol") {
          closeList();
          listType = "ol";
          html.push("<ol>");
        }
        html.push(`<li>${inlineMd(numbered[1])}</li>`);
        continue;
      }
      closeList();
      const heading = line.match(/^(#{1,4})\s+(.*)$/);
      if (heading) {
        const level = Math.min(heading[1].length + 2, 4);
        html.push(`<h${level}>${inlineMd(heading[2])}</h${level}>`);
        continue;
      }
      html.push(`<p>${inlineMd(line)}</p>`);
    }
    closeList();
    return html.join("");
  }

  function inlineMd(text) {
    return text
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  }

  function stripMarkdown(text) {
    return String(text)
      .replace(/```[\s\S]*?```/g, " ")
      .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
      .replace(/[#*_`>]/g, "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  async function fetchJson(url, fallback) {
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) return fallback;
      return await response.json();
    } catch (error) {
      return fallback;
    }
  }

  function readJson(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (error) {
      return fallback;
    }
  }
})();
