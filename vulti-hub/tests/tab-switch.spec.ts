import { test, expect } from '@playwright/test';

const BASE = process.env.BASE_URL || 'http://localhost:5175';

const MOCK_AGENT = {
	id: 'test-agent',
	name: 'TestBot',
	role: 'tester',
	description: 'A test agent',
	personality: '',
	understanding: '',
	model: 'claude-sonnet-4-20250514',
	systemPrompt: '',
	isDefault: false,
	skills: [],
};

async function openAgentPanel(page: import('@playwright/test').Page) {
	await page.addInitScript(() => {
		localStorage.setItem('vulti_settings', JSON.stringify({ gateway: { connected: true } }));
		localStorage.setItem('vulti_active_agent', 'test-agent');
	});

	await page.addInitScript((agent) => {
		(window as any).__TAURI_INTERNALS__ = {
			invoke: (cmd: string, _args?: any) => {
				const handlers: Record<string, any> = {
					list_agents: [agent],
					get_agent: agent,
					get_agent_avatar: null,
					get_status: { gateway_state: 'running', platforms: {} },
					list_integrations: [],
					get_memories: { memory: '', user: '' },
					get_soul: '',
					list_cron: [],
					list_rules: [],
					get_analytics: null,
					list_secrets: [],
					list_oauth_tokens: [],
					get_channels: { platforms: {} },
					list_relationships: [],
					get_owner: { name: 'Human' },
					get_connections: [],
					get_pane_widgets: {},
					get_wallet: { cards: [] },
				};
				const result = handlers[cmd];
				if (result !== undefined) return Promise.resolve(result);
				return Promise.resolve(null);
			},
			convertFileSrc: (src: string) => src,
		};
	}, MOCK_AGENT);

	await page.goto(BASE, { waitUntil: 'networkidle' });
	await page.waitForTimeout(500);

	// Dismiss Vite error overlay if present
	const overlay = page.locator('vite-error-overlay');
	if (await overlay.count() > 0) {
		await page.evaluate(() => {
			document.querySelector('vite-error-overlay')?.remove();
		});
		await page.waitForTimeout(200);
	}

	const agentNode = page.locator('.svelte-flow__node-agent').first();
	if (await agentNode.count() > 0) {
		await agentNode.click();
	} else {
		const anyNode = page.locator('.svelte-flow__node').first();
		if (await anyNode.count() > 0) await anyNode.click();
	}

	await page.waitForSelector('.panel-tab', { timeout: 5000 });
}

test.describe('Agent tab switching feedback', () => {

	test('clicking a tab immediately highlights it, shows spinner, then loads content', async ({ page }) => {
		await openAgentPanel(page);

		const homeTab = page.locator('.panel-tab', { hasText: 'Home' });
		await expect(homeTab).toHaveClass(/active/);

		// Set up observer to catch the spinner appearing
		await page.evaluate(() => {
			(window as any).__spinnerSeen = false;
			const observer = new MutationObserver(() => {
				const spinner = document.querySelector('.panel-content-main .animate-spin');
				if (spinner) (window as any).__spinnerSeen = true;
			});
			const target = document.querySelector('.panel-content-main');
			if (target) observer.observe(target, { childList: true, subtree: true });
		});

		// Click Profile tab
		const profileTab = page.locator('.panel-tab', { hasText: 'Profile' });
		await profileTab.click();

		// Tab should highlight immediately
		await expect(profileTab).toHaveClass(/active/);
		await expect(homeTab).not.toHaveClass(/active/);

		// Wait for content to settle
		await page.waitForTimeout(500);

		// Spinner should have been visible during the transition
		const spinnerWasSeen = await page.evaluate(() => (window as any).__spinnerSeen);
		expect(spinnerWasSeen).toBe(true);

		// Spinner should now be gone (content loaded)
		const spinner = page.locator('.panel-content-main .animate-spin');
		await expect(spinner).not.toBeVisible({ timeout: 1000 });
	});

	test('clicking already-active tab does nothing', async ({ page }) => {
		await openAgentPanel(page);

		const homeTab = page.locator('.panel-tab', { hasText: 'Home' });
		await expect(homeTab).toHaveClass(/active/);

		await homeTab.click();

		// No spinner
		const spinner = page.locator('.panel-content-main .animate-spin');
		await expect(spinner).not.toBeVisible({ timeout: 300 });
		await expect(homeTab).toHaveClass(/active/);
	});

	test('rapid tab switching settles on last tab', async ({ page }) => {
		await openAgentPanel(page);

		const skillsTab = page.locator('.panel-tab', { hasText: 'Skills' });
		const walletTab = page.locator('.panel-tab', { hasText: 'Wallet' });
		const analyticsTab = page.locator('.panel-tab', { hasText: 'Analytics' });

		await skillsTab.click();
		await walletTab.click();
		await analyticsTab.click();

		await expect(analyticsTab).toHaveClass(/active/);

		const spinner = page.locator('.panel-content-main .animate-spin');
		await expect(spinner).not.toBeVisible({ timeout: 2000 });
	});
});
