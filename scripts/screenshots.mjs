// Captures the README screenshots: runs the built app in demo mode (fictional MPs, no OpenNorth calls) and
// drives it in the locally installed Chrome. Usage: npm run screenshots (set CHROME_PATH to use another browser).
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';
import { createApp } from '../server/index.mjs';
import { demoRepresentFetch } from '../server/demoRepresent.mjs';

const out = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../docs/screenshots');
const visitor = { 'First name': 'Ari', 'Last name': 'Lee', 'Street address': '10 Main St', City: 'Ottawa', 'Province or territory': 'ON' };

// A fixed "random" so each run picks the same letters.
const server = createApp({ fetch: demoRepresentFetch, random: () => 0.35 }).listen(0);
const base = `http://localhost:${server.address().port}/campaign/`;
const browser = await chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : { channel: 'chrome' });

async function lookUp(page, postalCode) {
  await page.goto(base);
  for (const [label, value] of Object.entries(visitor)) await page.getByLabel(label).fill(value);
  await page.getByLabel('Postal code').fill(postalCode);
  await page.getByRole('button', { name: /find my mp/i }).click();
}

// Crops a full-page capture to one element, so tall elements are not cut off at the window's edge.
async function shotOf(page, name, selector) {
  await page.evaluate(() => window.scrollTo(0, 0));
  const box = await page.locator(selector).first().boundingBox();
  await shot(page, name, { fullPage: true, clip: box });
}

async function shot(page, name, options = {}) {
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: path.join(out, name), ...options });
  console.log(`wrote docs/screenshots/${name}`);
}

try {
  await mkdir(out, { recursive: true });
  const desktop = await browser.newPage({ viewport: { width: 1360, height: 900 }, deviceScaleFactor: 2 });

  await desktop.goto(base);
  await shot(desktop, '01-start.png');

  await lookUp(desktop, 'K2B 1A1');
  await desktop.locator('.email-editor textarea').waitFor();
  await shot(desktop, '02-draft.png', { fullPage: true });

  await desktop.getByRole('button', { name: /send email/i }).click();
  await shotOf(desktop, '03-send-menu.png', '.draft-card');

  await lookUp(desktop, 'K2C 0A1');
  await desktop.getByText('Choose your MP').waitFor();
  await shotOf(desktop, '04-choose-mp.png', '.campaign-card');

  const phone = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true });
  await lookUp(phone, 'K1P 1A1');
  await phone.locator('.email-editor textarea').waitFor();
  await phone.locator('.draft-actions').evaluate((element) => element.scrollIntoView({ block: 'end' }));
  await phone.evaluate(() => window.scrollBy(0, 24));
  await shot(phone, '05-phone.png');
} finally {
  await browser.close();
  server.close();
}
