import { test, expect } from '@playwright/test';

const BASE = process.env.BASE_URL || 'http://localhost:5175';

test.describe('Agent tab switching feedback', () => {

	test('clicking a tab immediately highlights it and shows spinner before content loads', async ({ page }) => {
		await page.goto(BASE);

		// Click an agent node to open the panel
		const agentNode = page.locator('.svelte-flow__node-agent').first();
		await agentNode.waitFor({ timeout: 5000 });
		await agentNode.click();

		// Wait for the panel to appear
		await page.waitForSelector('.panel-slide', { timeout: 5000 });

		// Verify we see the tab bar with Home active by default
		const homeTab = page.locator('.panel-tab', { hasText: 'Home' });
		await expect(homeTab).toHaveClass(/active/);

		// Click the Profile tab
		const profileTab = page.locator('.panel-tab', { hasText: 'Profile' });
		await profileTab.click();

		// 1) Tab should be immediately active (highlighted)
		await expect(profileTab).toHaveClass(/active/);

		// 2) Spinner should appear in the content area (tabLoading = true)
		const spinner = page.locator('.panel-content-main .animate-spin');
		// The spinner should be visible right after click (before the 150ms timeout)
		await expect(spinner).toBeVisible({ timeout: 100 });

		// 3) After the loading delay, spinner should disappear and content should render
		await expect(spinner).not.toBeVisible({ timeout: 1000 });

		// Home tab should no longer be active
		await expect(homeTab).not.toHaveClass(/active/);
	});

	test('clicking the already-active tab does nothing (no spinner)', async ({ page }) => {
		await page.goto(BASE);

		const agentNode = page.locator('.svelte-flow__node-agent').first();
		await agentNode.waitFor({ timeout: 5000 });
		await agentNode.click();
		await page.waitForSelector('.panel-slide', { timeout: 5000 });

		// Home is active by default — click it again
		const homeTab = page.locator('.panel-tab', { hasText: 'Home' });
		await expect(homeTab).toHaveClass(/active/);
		await homeTab.click();

		// No spinner should appear
		const spinner = page.locator('.panel-content-main .animate-spin');
		await expect(spinner).not.toBeVisible({ timeout: 200 });
	});

	test('rapid tab switching settles on the last clicked tab', async ({ page }) => {
		await page.goto(BASE);

		const agentNode = page.locator('.svelte-flow__node-agent').first();
		await agentNode.waitFor({ timeout: 5000 });
		await agentNode.click();
		await page.waitForSelector('.panel-slide', { timeout: 5000 });

		// Rapidly click through multiple tabs
		const skillsTab = page.locator('.panel-tab', { hasText: 'Skills' });
		const walletTab = page.locator('.panel-tab', { hasText: 'Wallet' });
		const analyticsTab = page.locator('.panel-tab', { hasText: 'Analytics' });

		await skillsTab.click();
		await walletTab.click();
		await analyticsTab.click();

		// The last tab clicked should be active
		await expect(analyticsTab).toHaveClass(/active/);

		// After settling, spinner should be gone and content should load
		const spinner = page.locator('.panel-content-main .animate-spin');
		await expect(spinner).not.toBeVisible({ timeout: 1000 });
	});
});
