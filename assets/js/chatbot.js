/* ======================================================================
   GWM Europe — AI Chatbot widget (demo)
   ----------------------------------------------------------------------
   Two operating modes:
     1. "demo"  — runs entirely in-browser with rule-based responses.
                  Perfect for showing a prospective client what the UX feels
                  like without needing any backend or API keys.
     2. "api"   — POSTs the conversation to a configurable endpoint
                  (default: /api/chat) which proxies to the Anthropic API.
                  See server/server.js for a reference implementation.

   Configure via window.GWM_CHATBOT_CONFIG before this script runs, e.g.:
     window.GWM_CHATBOT_CONFIG = { mode: 'api', endpoint: '/api/chat' };
   ====================================================================== */

(() => {
  const CONFIG = Object.assign({
    mode: 'demo',                // 'demo' | 'api'
    endpoint: '/api/chat',
    botName: 'GWM Assistant',
    greeting:
      "Hi! I'm the GWM virtual assistant. Ask me about our models, range, hybrid tech, or how to book a test drive.",
    suggestions: [
      'Tell me about ORA 5',
      'Compare H7 and JOLION MAX',
      'How do I book a test drive?',
      'What warranty do you offer?'
    ]
  }, window.GWM_CHATBOT_CONFIG || {});

  const root = document.getElementById('gwm-chatbot-root');
  if (!root) return;

  // Conversation state — kept in memory; in API mode, sent on each turn.
  const history = [];

  // ---------- Render skeleton ----------
  root.innerHTML = `
    <button class="gwm-chat-launcher" id="gwmChatLauncher" aria-label="Open chat">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
           stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
      </svg>
      <span class="badge">1</span>
    </button>

    <section class="gwm-chat-panel" id="gwmChatPanel" role="dialog" aria-label="GWM assistant">
      <header class="gwm-chat-head">
        <div class="avatar">GWM</div>
        <div class="head-text">
          <h4>${escapeHTML(CONFIG.botName)}</h4>
          <div class="status">Online · usually replies instantly</div>
        </div>
        <button class="gwm-chat-close" id="gwmChatClose" aria-label="Close">×</button>
      </header>
      <div class="gwm-chat-body" id="gwmChatBody"></div>
      <div class="gwm-suggest" id="gwmSuggest"></div>
      <form class="gwm-chat-input" id="gwmChatForm">
        <input type="text" id="gwmChatInput" placeholder="Ask about a model, range, dealer…" autocomplete="off" />
        <button type="submit" id="gwmChatSend" aria-label="Send">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
               stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 2L11 13"/>
            <path d="M22 2l-7 20-4-9-9-4 20-7z"/>
          </svg>
        </button>
      </form>
      <div class="gwm-chat-foot">Demo prototype · powered by AI</div>
    </section>
  `;

  const launcher  = document.getElementById('gwmChatLauncher');
  const panel     = document.getElementById('gwmChatPanel');
  const closeBtn  = document.getElementById('gwmChatClose');
  const body      = document.getElementById('gwmChatBody');
  const form      = document.getElementById('gwmChatForm');
  const input     = document.getElementById('gwmChatInput');
  const sendBtn   = document.getElementById('gwmChatSend');
  const suggest   = document.getElementById('gwmSuggest');
  const badge     = launcher.querySelector('.badge');

  // ---------- Open / close ----------
  let opened = false;
  const open = () => {
    panel.classList.add('open');
    opened = true;
    badge.style.display = 'none';
    setTimeout(() => input.focus(), 200);
  };
  const close = () => panel.classList.remove('open');

  launcher.addEventListener('click', () => panel.classList.contains('open') ? close() : open());
  closeBtn.addEventListener('click', close);

  // Greeting + suggestions on first open
  appendBot(CONFIG.greeting);
  renderSuggestions(CONFIG.suggestions);

  // ---------- Form submit ----------
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    sendUserMessage(text);
  });

  // ---------- Public API for inline triggers ----------
  window.GWMChatbot = {
    open, close,
    ask: (text) => { open(); sendUserMessage(text); }
  };

  // ======================================================================
  // Core message flow
  // ======================================================================
  async function sendUserMessage(text) {
    appendUser(text);
    history.push({ role: 'user', content: text });
    suggest.innerHTML = '';
    const typing = appendTyping();
    sendBtn.disabled = true;

    try {
      const reply = CONFIG.mode === 'api'
        ? await callBackend(history)
        : await demoReply(text);
      typing.remove();
      appendBot(reply);
      history.push({ role: 'assistant', content: reply });
    } catch (err) {
      typing.remove();
      appendBot(
        "Sorry — I couldn't reach the assistant just now. Please try again, or contact our team via the Contact section."
      );
      console.error('[GWMChatbot]', err);
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  }

  async function callBackend(messages) {
    const res = await fetch(CONFIG.endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages })
    });
    if (!res.ok) throw new Error('Bad response: ' + res.status);
    const data = await res.json();
    return data.reply || "I'm not sure how to answer that yet.";
  }

  // ======================================================================
  // Rendering helpers
  // ======================================================================
  function appendUser(text) {
    const el = document.createElement('div');
    el.className = 'gwm-msg user';
    el.textContent = text;
    body.appendChild(el);
    scrollToEnd();
    return el;
  }

  function appendBot(text) {
    const el = document.createElement('div');
    el.className = 'gwm-msg bot';
    el.innerHTML = formatBotText(text);
    body.appendChild(el);
    scrollToEnd();
    return el;
  }

  function appendTyping() {
    const el = document.createElement('div');
    el.className = 'gwm-typing';
    el.innerHTML = '<span></span><span></span><span></span>';
    body.appendChild(el);
    scrollToEnd();
    return el;
  }

  function renderSuggestions(items) {
    suggest.innerHTML = '';
    items.forEach(text => {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = text;
      b.addEventListener('click', () => sendUserMessage(text));
      suggest.appendChild(b);
    });
  }

  function scrollToEnd() {
    body.scrollTop = body.scrollHeight;
  }

  function escapeHTML(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  function formatBotText(text) {
    // Very small formatter: escape, then turn **bold**, line breaks, and bullets.
    let html = escapeHTML(text);
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\n- /g, '<br>• ');
    html = html.replace(/\n/g, '<br>');
    return html;
  }

  // ======================================================================
  // Demo mode — rule-based knowledge about the GWM line-up
  // ======================================================================
  const KB = {
    ora5: {
      name: 'GWM ORA 5',
      tagline: 'Premium electric SUV',
      copy:
        "**GWM ORA 5** is our stylish premium electric SUV.\n" +
        "- Range: up to 440 km (WLTP)\n" +
        "- 0–100 km/h: 6.9 s\n" +
        "- Drive: single or dual motor\n" +
        "It's designed for daily city life with a refined, quiet cabin and fast-charging support."
    },
    h7: {
      name: 'GWM H7',
      tagline: 'Intelligent hybrid SUV',
      copy:
        "**GWM H7** is our full-size intelligent hybrid SUV — \"Driven by Bold Intelligence\".\n" +
        "- Powertrain: Hi4 Hybrid AWD\n" +
        "- Combined consumption: 5.6 L / 100 km\n" +
        "- Towing capacity: 2,500 kg\n" +
        "It pairs adaptive AWD with a calm, tech-forward cabin and L2+ ADAS."
    },
    jolion: {
      name: 'GWM JOLION MAX',
      tagline: 'Compact urban SUV',
      copy:
        "**GWM JOLION MAX** is our versatile compact urban SUV.\n" +
        "- Engine: 1.5T hybrid\n" +
        "- Combined consumption: 4.7 L / 100 km\n" +
        "- Boot: 430 L\n" +
        "Smart safety, comfort and efficiency — ready for the city or the weekend."
    }
  };

  function demoReply(raw) {
    const q = raw.toLowerCase();
    // Simulate latency for realism
    const wait = 600 + Math.random() * 600;
    return new Promise((resolve) => setTimeout(() => resolve(answer(q)), wait));
  }

  function answer(q) {
    // Greetings
    if (/\b(hi|hello|hey|hallo|bonjour|ciao|hola)\b/.test(q)) {
      return "Hi there! 👋 What can I help you with today — a specific model, our hybrid technology, or arranging a test drive?";
    }
    // Models
    if (/\bora\s*5?\b|\bora-5\b/.test(q)) return KB.ora5.copy;
    if (/\bh7\b/.test(q))                 return KB.h7.copy;
    if (/\bjolion\b/.test(q))             return KB.jolion.copy;

    // Compare
    if (/\bcompare|vs\b|versus|difference/.test(q)) {
      return (
        "Here's a quick comparison of our launch line-up:\n\n" +
        "**ORA 5** — fully electric, ~440 km WLTP, premium urban SUV.\n" +
        "**H7** — Hi4 hybrid AWD, ~5.6 L/100 km, full-size intelligent SUV.\n" +
        "**JOLION MAX** — 1.5T hybrid, ~4.7 L/100 km, compact and efficient.\n\n" +
        "Want me to go deeper on any one of them?"
      );
    }

    // Test drive / dealer
    if (/test[\s-]?drive|book|reserve|dealer|showroom|nearest/.test(q)) {
      return (
        "You can book a test drive directly from this page — scroll to the **\"Book a test drive\"** button, " +
        "or share your country and I'll point you to the closest authorised GWM dealer at launch."
      );
    }

    // Pricing
    if (/price|cost|how much|pricing/.test(q)) {
      return (
        "Final European pricing will be confirmed closer to launch. If you'd like, I can register your interest " +
        "and our team will email you the price list as soon as it's announced."
      );
    }

    // Warranty / service
    if (/warranty|guarantee|service|maintenance|battery/.test(q)) {
      return (
        "Every new GWM in Europe comes with:\n" +
        "- **5-year** bumper-to-bumper warranty\n" +
        "- **8-year / 160,000 km** battery warranty on electrified models\n" +
        "- **24/7** European roadside assistance\n" +
        "- Genuine parts + certified technicians at every authorised service point."
      );
    }

    // Charging / EV
    if (/charg(e|ing)|kw|kwh|fast.?charg|range/.test(q)) {
      return (
        "Our electrified line-up supports DC fast-charging. ORA 5 can charge from 30% → 80% in around 30 minutes " +
        "on a public DC charger, and ships with a Type-2 cable for AC home charging up to 11 kW."
      );
    }

    // Safety / ADAS
    if (/safety|adas|autopilot|crash|ncap|assist/.test(q)) {
      return (
        "Safety is core to every GWM. The European line-up targets a 5★ Euro NCAP rating and ships with " +
        "**L2+ ADAS** — adaptive cruise, lane-centring, blind-spot monitoring and 360° awareness, all calibrated for EU roads."
      );
    }

    // Tech / Hi4 / Coffee Intelligence
    if (/hi4|hybrid|powertrain|coffee|infotain|software|ota/.test(q)) {
      return (
        "Our **Hi4** platform is a three-motor intelligent hybrid system — it shifts seamlessly between EV and hybrid " +
        "modes for efficiency in town and confidence on long journeys. The cabin runs **Coffee Intelligence**, our " +
        "voice-first assistant, with regular OTA updates."
      );
    }

    // About
    if (/about|company|history|founded|who.+gwm|great wall/.test(q)) {
      return (
        "GWM (Great Wall Motor) was founded in 1984 and is one of the world's largest dedicated SUV and pickup makers. " +
        "We sell in 170+ countries and are now bringing a fully electrified line-up to Europe, with HQ in Munich."
      );
    }

    // Contact
    if (/contact|email|phone|reach|press/.test(q)) {
      return (
        "You can reach us via the **Contact** section at the bottom of the page, or email enquiries to " +
        "info@gwm-europe.com (demo address). Press contacts are listed under Company → Press."
      );
    }

    // Thanks
    if (/thank|thanks|cheers|appreciate/.test(q)) {
      return "You're very welcome! Anything else I can help you with?";
    }

    // Fallback
    return (
      "Good question — I'm a demo assistant focused on the GWM Europe line-up. " +
      "Try asking about **ORA 5**, **H7** or **JOLION MAX**, our **hybrid technology**, **warranty**, or how to **book a test drive**."
    );
  }
})();
