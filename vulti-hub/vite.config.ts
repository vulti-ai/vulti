import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import wasm from 'vite-plugin-wasm';
import topLevelAwait from 'vite-plugin-top-level-await';
import { defineConfig } from 'vite';

export default defineConfig({
	server: {
		host: '127.0.0.1'
	},
	plugins: [
		wasm(),
		topLevelAwait(),
		tailwindcss(),
		sveltekit()
	]
});
