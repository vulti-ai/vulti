import { chromium } from 'playwright';
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

await page.goto('http://localhost:5199');
await page.waitForTimeout(1000);
await page.fill('input[type="password"]', 'test-token');
await page.click('button[type="submit"]');
await page.waitForTimeout(1000);

// Record a video-like sequence of the collapse animation
// Take rapid screenshots during transition
await page.screenshot({ path: '/tmp/h4-before.png' });

// Click collapse and capture mid-transition
await page.locator('aside button').last().click();
await page.waitForTimeout(100);
await page.screenshot({ path: '/tmp/h4-mid1.png' });
await page.waitForTimeout(100);
await page.screenshot({ path: '/tmp/h4-mid2.png' });
await page.waitForTimeout(300);
await page.screenshot({ path: '/tmp/h4-after.png' });

// Expand again
await page.locator('aside button').last().click();
await page.waitForTimeout(100);
await page.screenshot({ path: '/tmp/h4-expand-mid.png' });
await page.waitForTimeout(400);
await page.screenshot({ path: '/tmp/h4-expand-done.png' });

await browser.close();
