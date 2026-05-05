// Diff check: load local index.html headlessly, log every failed network request.
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';

const BASE = 'http://localhost:8000';
const browser = await chromium.launch({
  executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  args: ['--no-sandbox'],
});
const page = await browser.newContext({ viewport: { width: 1440, height: 900 } }).then(c => c.newPage());

const failures = [];
const requests = [];
page.on('request', (r) => requests.push(r.url()));
page.on('requestfailed', (r) => failures.push({ url: r.url(), reason: r.failure()?.errorText || 'unknown' }));
page.on('response', (resp) => {
  if (resp.status() >= 400) failures.push({ url: resp.url(), reason: 'HTTP ' + resp.status() });
});

const consoleErrs = [];
page.on('pageerror', (e) => consoleErrs.push(e.message.slice(0, 140)));
page.on('console', (msg) => {
  if (msg.type() === 'error') consoleErrs.push('[console] ' + msg.text().slice(0, 140));
});

await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 }).catch((e) => console.warn('nav timeout', e.message));

// Scroll through the whole page to trigger lazy-loaded content
const scrollHeight = await page.evaluate(() => document.body.scrollHeight);
for (let y = 0; y < scrollHeight; y += 500) {
  await page.evaluate((yy) => window.scrollTo(0, yy), y);
  await page.waitForTimeout(150);
}
await page.waitForTimeout(1500);

console.log('\n--- Total network requests:', requests.length);
console.log('--- Failed/4xx/5xx:', failures.length);
const dedup = [...new Map(failures.map(f => [f.url, f])).values()];
for (const f of dedup) {
  console.log('  ', f.reason.padEnd(20), f.url);
}

console.log('\n--- JS errors / console errors:', consoleErrs.length);
for (const e of consoleErrs.slice(0, 20)) console.log('  ', e);

// Detect lazy / hidden content
const dynStats = await page.evaluate(() => {
  const empty = [...document.querySelectorAll('img')].filter(i => !i.src || i.src.endsWith('#') || i.src === window.location.href).length;
  const broken = [...document.querySelectorAll('img')].filter(i => i.complete && i.naturalWidth === 0).length;
  const videos = [...document.querySelectorAll('video,iframe')].length;
  const dataSrc = [...document.querySelectorAll('[data-src],[data-bg],[data-lazy],[data-srcset]')].length;
  return { empty, broken, videos, dataSrc };
});
console.log('\n--- DOM diagnostics:', JSON.stringify(dynStats));

await browser.close();
