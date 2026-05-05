// Verify the new chatbot widget works end-to-end against the FastAPI backend.
// Without a real OPENAI_API_KEY, sending a message should display the
// graceful error fallback in the chat panel.
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';

const BASE = 'http://localhost:8000';
const OUT = '/home/user/Venononom/screenshots';

const browser = await chromium.launch({
  executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  args: ['--no-sandbox'],
});
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
page.on('pageerror', (e) => console.warn('[pageerror]', e.message.slice(0, 120)));

await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
await page.waitForSelector('.gwm-chatbot__launcher', { timeout: 10000 });
await page.waitForTimeout(1500);

// Open panel
await page.click('.gwm-chatbot__launcher');
await page.waitForSelector('.gwm-chatbot.is-open .gwm-chatbot__panel', { timeout: 5000 });
await page.waitForTimeout(800);

// Ask a question — without OPENAI_API_KEY it should surface graceful error
const input = page.locator('.gwm-chatbot__input');
await input.fill('Tell me about GWM ORA 5');
await input.press('Enter');
await page.waitForTimeout(2500);

await page.screenshot({ path: `${OUT}/08-backend-error-fallback.png`, fullPage: false });
console.log('-> 08-backend-error-fallback.png');

await browser.close();
