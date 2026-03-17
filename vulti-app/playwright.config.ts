import { defineConfig } from '@playwright/test';

export default defineConfig({
	testDir: './tests',
	timeout: 15000,
	use: {
		baseURL: process.env.BASE_URL || 'http://localhost:5175',
		headless: true,
	},
	projects: [
		{ name: 'chromium', use: { browserName: 'chromium' } },
	],
});
