/* ======================================================================
   GWM demo — minimal Anthropic chat proxy
   ----------------------------------------------------------------------
   A tiny zero-dependency Node.js server that:
     1. Serves the static demo site from the project root.
     2. Exposes POST /api/chat which forwards conversation history to the
        Anthropic Messages API and returns the assistant reply.

   Run:
     ANTHROPIC_API_KEY=sk-ant-... node server/server.js

   Then open http://localhost:3000

   The frontend stays in "demo" mode by default (no key needed). To switch
   it to live mode, edit index.html and add before chatbot.js:
     <script>
       window.GWM_CHATBOT_CONFIG = { mode: 'api', endpoint: '/api/chat' };
     </script>
   ====================================================================== */

const http = require('http');
const fs   = require('fs');
const path = require('path');

const PORT       = process.env.PORT || 3000;
const ROOT       = path.resolve(__dirname, '..');
const API_KEY    = process.env.ANTHROPIC_API_KEY || '';
const MODEL      = process.env.ANTHROPIC_MODEL || 'claude-haiku-4-5-20251001';

const SYSTEM_PROMPT = [
  "You are the GWM Europe virtual assistant for a sales-pitch demo site.",
  "GWM (Great Wall Motor) is launching three vehicles in Europe:",
  "  - GWM ORA 5: a premium electric SUV, up to 440 km WLTP, 0-100 in 6.9s.",
  "  - GWM H7: an intelligent full-size hybrid SUV with Hi4 AWD (~5.6 L/100km).",
  "  - GWM JOLION MAX: a compact urban hybrid SUV (1.5T, ~4.7 L/100km).",
  "Warranty: 5 years bumper-to-bumper, 8 years / 160,000 km on the EV battery,",
  "24/7 European roadside assistance.",
  "Tech highlights: Hi4 hybrid platform, Coffee Intelligence voice assistant,",
  "L2+ ADAS calibrated for EU roads, OTA updates.",
  "",
  "Style: friendly, concise, helpful. 1-3 short paragraphs max.",
  "If the user asks about pricing or exact launch dates, explain that final",
  "European pricing and timing will be announced closer to launch and offer to",
  "register their interest. If asked something off-topic, politely steer back",
  "to GWM products and services."
].join('\n');

// --------------------------------------------------------------------- MIME
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css':  'text/css; charset=utf-8',
  '.js':   'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg':  'image/svg+xml',
  '.png':  'image/png',
  '.jpg':  'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.ico':  'image/x-icon',
  '.txt':  'text/plain; charset=utf-8'
};

// ------------------------------------------------------------------- Static
function serveStatic(req, res) {
  let urlPath = decodeURIComponent(req.url.split('?')[0]);
  if (urlPath === '/' || urlPath === '') urlPath = '/index.html';

  const filePath = path.join(ROOT, urlPath);
  // Prevent path traversal outside ROOT
  if (!filePath.startsWith(ROOT)) {
    res.writeHead(403); return res.end('Forbidden');
  }

  fs.stat(filePath, (err, stat) => {
    if (err || !stat.isFile()) {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      return res.end('Not found');
    }
    const ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
    fs.createReadStream(filePath).pipe(res);
  });
}

// --------------------------------------------------------------- Read body
function readJSON(req) {
  return new Promise((resolve, reject) => {
    let data = '';
    req.on('data', (c) => { data += c; if (data.length > 1e6) req.destroy(); });
    req.on('end', () => {
      try { resolve(data ? JSON.parse(data) : {}); }
      catch (e) { reject(e); }
    });
    req.on('error', reject);
  });
}

// ---------------------------------------------------------- Anthropic call
async function callAnthropic(messages) {
  if (!API_KEY) throw new Error('ANTHROPIC_API_KEY is not set');

  const body = {
    model: MODEL,
    max_tokens: 512,
    system: SYSTEM_PROMPT,
    messages: messages
      .filter(m => m && (m.role === 'user' || m.role === 'assistant'))
      .map(m => ({ role: m.role, content: String(m.content || '') }))
  };

  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-api-key': API_KEY,
      'anthropic-version': '2023-06-01'
    },
    body: JSON.stringify(body)
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Anthropic API ${res.status}: ${err}`);
  }
  const data = await res.json();
  const text = (data.content || [])
    .filter(b => b.type === 'text')
    .map(b => b.text)
    .join('\n')
    .trim();
  return text || "Sorry, I didn't catch that — could you rephrase?";
}

// ------------------------------------------------------------------- Server
const server = http.createServer(async (req, res) => {
  // Chat endpoint
  if (req.method === 'POST' && req.url === '/api/chat') {
    try {
      const { messages = [] } = await readJSON(req);
      const reply = await callAnthropic(messages);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ reply }));
    } catch (err) {
      console.error('[chat error]', err.message);
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: err.message }));
    }
    return;
  }

  // Health
  if (req.method === 'GET' && req.url === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify({ ok: true, model: MODEL, hasKey: !!API_KEY }));
  }

  // Default: static
  if (req.method === 'GET') return serveStatic(req, res);

  res.writeHead(405); res.end('Method not allowed');
});

server.listen(PORT, () => {
  console.log(`\nGWM demo running at http://localhost:${PORT}`);
  console.log(`  Anthropic key: ${API_KEY ? 'configured ✓' : 'NOT set — chatbot will fail in api mode'}`);
  console.log(`  Model:         ${MODEL}\n`);
});
