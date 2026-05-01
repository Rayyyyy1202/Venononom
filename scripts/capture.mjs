// Capture screenshots of the local GWM demo for review.
// Usage: node scripts/capture.mjs
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
import { mkdir } from 'fs/promises';

const BASE = 'http://localhost:8000';
const OUT = '/home/user/Venononom/screenshots';
await mkdir(OUT, { recursive: true });

const browser = await chromium.launch({
  executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  args: ['--no-sandbox'],
});
const ctx = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 1,
});
const page = await ctx.newPage();

// Suppress noisy AEM/jquery errors in console; keep failures
page.on('pageerror', (err) => console.warn('[pageerror]', err.message.slice(0, 120)));

console.log('1. Loading homepage…');
await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 }).catch((e) => {
  console.warn('networkidle timed out, continuing:', e.message);
});
await page.waitForSelector('.gwm-chatbot__launcher', { timeout: 10000 });
await page.waitForTimeout(1500); // let above-the-fold images settle

await page.screenshot({ path: `${OUT}/01-homepage.png`, fullPage: false });
console.log('   -> 01-homepage.png');

console.log('2. Full-page screenshot…');
await page.screenshot({ path: `${OUT}/02-fullpage.png`, fullPage: true });
console.log('   -> 02-fullpage.png');

console.log('3. Open chatbot panel…');
await page.click('.gwm-chatbot__launcher');
await page.waitForSelector('.gwm-chatbot.is-open .gwm-chatbot__panel', { timeout: 5000 });
await page.waitForTimeout(600); // wait for greeting + suggestions
await page.screenshot({ path: `${OUT}/03-chatbot-open.png`, fullPage: false });
console.log('   -> 03-chatbot-open.png');

console.log('4. Send a question (ORA 5) and capture reply…');
const input = page.locator('.gwm-chatbot__input');
await input.fill('Tell me about GWM ORA 5');
await input.press('Enter');
// Wait for typing indicator then reply
await page.waitForTimeout(2200);
await page.screenshot({ path: `${OUT}/04-chatbot-reply.png`, fullPage: false });
console.log('   -> 04-chatbot-reply.png');

console.log('5. Follow-up about dealership…');
await input.fill('How can I become a dealer?');
await input.press('Enter');
await page.waitForTimeout(2400);
await page.screenshot({ path: `${OUT}/05-chatbot-dealer.png`, fullPage: false });
console.log('   -> 05-chatbot-dealer.png');

console.log('6. Mobile viewport…');
await ctx.close();
const mobileCtx = await browser.newContext({
  viewport: { width: 390, height: 800 },
  deviceScaleFactor: 2,
  userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
});
const mPage = await mobileCtx.newPage();
await mPage.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
await mPage.waitForSelector('.gwm-chatbot__launcher', { timeout: 10000 });
await mPage.waitForTimeout(1500);
await mPage.screenshot({ path: `${OUT}/06-mobile.png`, fullPage: false });
console.log('   -> 06-mobile.png');

await mPage.click('.gwm-chatbot__launcher');
await mPage.waitForTimeout(600);
await mPage.screenshot({ path: `${OUT}/07-mobile-chat.png`, fullPage: false });
console.log('   -> 07-mobile-chat.png');

await browser.close();
console.log('\nDone.');
