<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { setToken } from '$lib/api';
	import { onMount } from 'svelte';
	import VultiLogo from '$lib/components/VultiLogo.svelte';

	let token = $state('');
	let error = $state('');

	onMount(() => {
		const params = new URLSearchParams(window.location.search);
		const urlToken = params.get('token');
		if (urlToken) {
			token = urlToken;
			window.history.replaceState({}, '', window.location.pathname);
			login();
		}
	});

	async function login() {
		error = '';
		if (!token.trim()) {
			error = 'Token is required';
			return;
		}
		try {
			setToken(token.trim());
			store.authenticated = true;
			store.loadSessions();
		} catch (e) {
			error = 'Authentication failed';
		}
	}
</script>

<div class="flex h-full items-center justify-center px-4">
	<div class="w-full max-w-md text-center">
		<!-- Logo -->
		<div class="mb-8">
			<div class="flex justify-center mb-4">
				<VultiLogo mode="wordmark" size={36} />
			</div>
			<p class="text-sm text-slate-400">Connect to your AI agent</p>
		</div>

		<!-- Form -->
		<div class="rounded-xl border border-border bg-surface p-6 text-left">
			<label for="token-input" class="mb-2 block text-sm font-medium text-slate-300">
				Connection Token
			</label>
			<p class="mb-4 text-xs text-slate-500">
				Paste the token shown in your terminal when you ran <code class="rounded bg-slate-800 px-1.5 py-0.5">vulti gateway</code>
			</p>

			<form onsubmit={login}>
				<input
					id="token-input"
					type="password"
					bind:value={token}
					placeholder="Paste token here"
					class="mb-3 w-full rounded-lg border border-border bg-slate-800 px-4 py-3 text-sm text-white placeholder-slate-500 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
					autofocus
				/>
				{#if error}
					<p class="mb-3 text-sm text-red-400">{error}</p>
				{/if}
				<button
					type="submit"
					class="w-full rounded-lg bg-primary py-3 text-sm font-medium text-white transition-colors hover:bg-primary-hover"
				>
					Connect
				</button>
			</form>
		</div>

		<p class="mt-6 text-xs text-slate-600">
			Or scan the QR code shown in your terminal to connect automatically
		</p>
	</div>
</div>
