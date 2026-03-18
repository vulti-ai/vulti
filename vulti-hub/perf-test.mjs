import { chromium } from 'playwright';

const BASE = 'http://localhost:4173/setup';

async function measure(page, label, fn) {
  const start = performance.now();
  await fn();
  await page.waitForTimeout(100); // let render settle
  const ms = (performance.now() - start).toFixed(0);
  console.log(`${label}: ${ms}ms`);
  return Number(ms);
}

(async () => {
  // Test both dev and preview
  for (const [name, url] of [['DEV (5173)', 'http://localhost:5173/setup'], ['PROD (4173)', 'http://localhost:4173/setup']]) {
    console.log(`\n=== ${name} ===`);
    const browser = await chromium.launch();
    const page = await browser.newPage();

    try {
      await page.goto(url, { waitUntil: 'networkidle', timeout: 10000 });
    } catch (e) {
      console.log(`  SKIP - not running`);
      await browser.close();
      continue;
    }

    // Wait for agent to appear
    await page.waitForTimeout(2000);

    // Click on Hector agent
    const hector = page.locator('button:has-text("Hector")').first();
    if (await hector.isVisible()) {
      await measure(page, 'Click Hector', () => hector.click());
    } else {
      console.log('  Hector not found, skipping tab tests');
      await browser.close();
      continue;
    }

    await page.waitForTimeout(500);

    // Now measure tab switches
    const tabs = ['Profile', 'Actions', 'Analytics', 'Config'];
    for (const tab of tabs) {
      const btn = page.locator(`button:has-text("${tab}")`).first();
      if (await btn.isVisible()) {
        await measure(page, `Switch to ${tab}`, () => btn.click());
      }
    }

    // Switch back to Profile
    const profileBtn = page.locator('button:has-text("Profile")').first();
    if (await profileBtn.isVisible()) {
      await measure(page, 'Back to Profile', () => profileBtn.click());
    }

    await browser.close();
  }
})();
