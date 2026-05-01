/* GWM AI Assistant — vanilla JS demo widget.
   Frontend-only: matches user queries against /chatbot/knowledge.json
   using a simple keyword-overlap scorer. No external requests are made. */

(function () {
  "use strict";

  const STORAGE_KEY = "gwm_chatbot_history_v1";
  const KB_URL = computeKbUrl();
  const SCRIPT_NAME = "GWM Assistant";

  let kb = null;
  let root = null;
  let panel = null;
  let body = null;
  let input = null;
  let sendBtn = null;
  let suggestionsEl = null;

  function computeKbUrl() {
    const cur = document.currentScript && document.currentScript.src;
    if (!cur) return "/chatbot/knowledge.json";
    return cur.replace(/chatbot\.js(\?.*)?$/, "knowledge.json");
  }

  /* ---------- Mount ---------- */

  function mount() {
    if (document.querySelector(".gwm-chatbot")) return;
    root = document.createElement("div");
    root.className = "gwm-chatbot";
    root.innerHTML = `
      <button class="gwm-chatbot__launcher" type="button" aria-label="Open chat">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 4h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H8l-4 4V6a2 2 0 0 1 2-2zm3 6h10v2H7v-2zm0-3h10v2H7V7z"/>
        </svg>
        <span class="gwm-chatbot__launcher-badge">AI</span>
      </button>
      <div class="gwm-chatbot__panel" role="dialog" aria-label="GWM Assistant">
        <div class="gwm-chatbot__header">
          <div class="gwm-chatbot__avatar">GW</div>
          <div class="gwm-chatbot__title">
            <div class="gwm-chatbot__title-main">GWM Assistant</div>
            <div class="gwm-chatbot__title-sub">Online · Demo</div>
          </div>
          <button class="gwm-chatbot__close" type="button" aria-label="Close chat">
            <svg viewBox="0 0 24 24"><path d="M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
          </button>
        </div>
        <div class="gwm-chatbot__body" aria-live="polite"></div>
        <div class="gwm-chatbot__input-wrap">
          <textarea class="gwm-chatbot__input" rows="1" placeholder="Ask about GWM models, dealers, contact…" aria-label="Type your message"></textarea>
          <button class="gwm-chatbot__send" type="button" aria-label="Send">
            <svg viewBox="0 0 24 24"><path d="M2 21l21-9L2 3v7l15 2-15 2z"/></svg>
          </button>
        </div>
        <div class="gwm-chatbot__footer">Demo assistant · answers come from public website content</div>
      </div>
    `;
    document.body.appendChild(root);

    panel = root.querySelector(".gwm-chatbot__panel");
    body = root.querySelector(".gwm-chatbot__body");
    input = root.querySelector(".gwm-chatbot__input");
    sendBtn = root.querySelector(".gwm-chatbot__send");

    root.querySelector(".gwm-chatbot__launcher").addEventListener("click", togglePanel);
    root.querySelector(".gwm-chatbot__close").addEventListener("click", () => setOpen(false));
    sendBtn.addEventListener("click", handleSend);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    });
    input.addEventListener("input", autoGrow);
  }

  function togglePanel() {
    setOpen(!root.classList.contains("is-open"));
  }
  function setOpen(open) {
    root.classList.toggle("is-open", open);
    if (open) setTimeout(() => input && input.focus(), 50);
  }
  function autoGrow() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 100) + "px";
  }

  /* ---------- Conversation ---------- */

  function loadHistory() {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch (e) {
      return [];
    }
  }
  function saveHistory(history) {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(history));
    } catch (e) { /* ignore quota */ }
  }

  function renderInitial() {
    const history = loadHistory();
    if (history.length) {
      history.forEach((m) => appendMessage(m.role, m.text, m.links || [], { animate: false }));
    } else {
      const greeting = "Hi! I'm the **GWM Assistant** — a demo bot for this site. I can help with our upcoming models (**ORA 5**, **H7**, **JOLION MAX**), dealership opportunities, warranty and contact info. What would you like to know?";
      appendMessage("bot", greeting, [], { animate: false, persist: true });
    }
    renderSuggestions();
  }

  function renderSuggestions() {
    if (suggestionsEl) suggestionsEl.remove();
    if (!kb || !kb.suggestions || !kb.suggestions.length) return;
    suggestionsEl = document.createElement("div");
    suggestionsEl.className = "gwm-chatbot__suggestions";
    kb.suggestions.forEach((s) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "gwm-chatbot__chip";
      chip.textContent = s;
      chip.addEventListener("click", () => {
        input.value = s;
        handleSend();
      });
      suggestionsEl.appendChild(chip);
    });
    body.appendChild(suggestionsEl);
    scrollBottom();
  }

  function handleSend() {
    const text = (input.value || "").trim();
    if (!text) return;
    input.value = "";
    autoGrow();
    if (suggestionsEl) { suggestionsEl.remove(); suggestionsEl = null; }
    appendMessage("user", text, [], { persist: true });
    respondTo(text);
  }

  function respondTo(query) {
    const typing = showTyping();
    const delay = 500 + Math.min(900, query.length * 22);
    setTimeout(() => {
      typing.remove();
      const reply = answer(query);
      appendMessage("bot", reply.text, reply.links, { typewriter: true, persist: true });
    }, delay);
  }

  /* ---------- Matching engine ---------- */

  function tokenize(s) {
    return (s || "")
      .toLowerCase()
      .replace(/[^\p{L}\p{N}\s]+/gu, " ")
      .split(/\s+/)
      .filter(Boolean);
  }

  function answer(query) {
    if (!kb) {
      return { text: "Loading knowledge base, please try again in a moment.", links: [] };
    }
    const qTokens = tokenize(query);
    const qStr = " " + qTokens.join(" ") + " ";
    let best = null;
    let bestScore = 0;
    for (const item of kb.qa) {
      let score = 0;
      for (const kw of item.keywords) {
        const kwLower = kw.toLowerCase();
        // multi-word keywords: substring match weighted higher
        if (kwLower.includes(" ")) {
          if (qStr.includes(" " + kwLower + " ") || query.toLowerCase().includes(kwLower)) {
            score += 3;
          }
        } else {
          if (qTokens.includes(kwLower)) score += 2;
          else if (qStr.includes(kwLower)) score += 1;
        }
      }
      if (score > bestScore) {
        bestScore = score;
        best = item;
      }
    }
    if (best && bestScore >= 2) {
      return { text: best.answer, links: best.links || [] };
    }
    return { text: kb.fallback, links: [] };
  }

  /* ---------- Rendering ---------- */

  function appendMessage(role, text, links, opts) {
    opts = opts || {};
    const el = document.createElement("div");
    el.className = "gwm-chatbot__msg gwm-chatbot__msg--" + role;
    body.appendChild(el);
    if (opts.typewriter) {
      typeInto(el, text, () => {
        if (links && links.length) appendLinks(el, links);
        scrollBottom();
      });
    } else {
      el.innerHTML = formatMd(text);
      if (links && links.length) appendLinks(el, links);
    }
    scrollBottom();
    if (opts.persist !== false) {
      const history = loadHistory();
      history.push({ role, text, links: links || [] });
      // cap history to last 40 messages
      if (history.length > 40) history.splice(0, history.length - 40);
      saveHistory(history);
    }
  }

  function appendLinks(parent, links) {
    const wrap = document.createElement("div");
    wrap.className = "gwm-chatbot__msg-links";
    links.forEach((lk) => {
      const a = document.createElement("a");
      a.className = "gwm-chatbot__msg-link";
      a.href = lk.url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = lk.label;
      wrap.appendChild(a);
    });
    parent.appendChild(wrap);
  }

  function showTyping() {
    const el = document.createElement("div");
    el.className = "gwm-chatbot__msg gwm-chatbot__msg--bot";
    el.innerHTML = '<div class="gwm-chatbot__typing"><span></span><span></span><span></span></div>';
    body.appendChild(el);
    scrollBottom();
    return el;
  }

  function typeInto(el, fullText, done) {
    const formatted = formatMd(fullText);
    // For typewriter, fade in by chunk on plain text, then swap to formatted at end
    const plain = stripMd(fullText);
    let i = 0;
    el.textContent = "";
    const step = Math.max(1, Math.floor(plain.length / 60)); // ~60 ticks total
    const interval = setInterval(() => {
      i += step;
      el.textContent = plain.slice(0, i);
      scrollBottom();
      if (i >= plain.length) {
        clearInterval(interval);
        el.innerHTML = formatted;
        if (done) done();
      }
    }, 18);
  }

  function scrollBottom() {
    body.scrollTop = body.scrollHeight;
  }

  /* ---------- Mini markdown ---------- */

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
  }
  function formatMd(text) {
    let s = escapeHtml(text);
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    s = s.replace(/\n/g, "<br>");
    return s;
  }
  function stripMd(text) {
    return text.replace(/\*\*/g, "").replace(/\*/g, "");
  }

  /* ---------- Init ---------- */

  function init() {
    mount();
    fetch(KB_URL, { cache: "no-store" })
      .then((r) => r.json())
      .then((data) => {
        kb = data;
        renderInitial();
      })
      .catch((err) => {
        console.warn("[" + SCRIPT_NAME + "] failed to load knowledge base:", err);
        kb = { qa: [], suggestions: [], fallback: "Knowledge base failed to load." };
        renderInitial();
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
