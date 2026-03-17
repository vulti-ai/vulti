import { chromium } from 'playwright';
const TOKEN = 'yMMaMvjFr1h6Gzj-o4kpaoEDlaQpfSYPTjD-jcEruL8';
const BASE = 'http://localhost:5173';
async function run() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 1200 } });
  await page.goto(`${BASE}?token=${TOKEN}`);
  await page.waitForTimeout(2000);
  // Navigate to Settings
  const btn = page.locator('button:has(span:text("Settings"))');
  await btn.first().click();
  await page.waitForTimeout(2000);
  await page.screenshot({ path: '/tmp/hector-screenshots/settings-top.png' });
  // Scroll down to see more
  await page.evaluate(() => document.querySelector('.overflow-y-auto')?.scrollBy(0, 600));
  await page.waitForTimeout(500);
  await page.screenshot({ path: '/tmp/hector-screenshots/settings-mid.png' });
  // Scroll more
  await page.evaluate(() => document.querySelector('.overflow-y-auto')?.scrollBy(0, 600));
  await page.waitForTimeout(500);
  await page.screenshot({ path: '/tmp/hector-screenshots/settings-bottom.png' });
  console.log('Done');
  await browser.close();
}
run().catch(e => { console.error(e); process.exit(1); });
