<script lang="ts">
	import { onMount } from 'svelte';

	let { status, onComplete }: {
		status: 'pending' | 'connected';
		onComplete: () => void;
	} = $props();

	let phase = $state<'checking' | 'not_installed' | 'starting' | 'waiting' | 'connected' | 'error'>(
		status === 'connected' ? 'connected' : 'checking'
	);
	let error = $state('');
	let pollInterval: ReturnType<typeof setInterval> | null = null;
	let pollCount = $state(0);
	let notified = false;

	const isTauri = typeof window !== 'undefined' && '__TAURI__' in window;

	onMount(() => {
		if (phase !== 'connected') checkGateway();
		else notifyOnce();
		return () => { if (pollInterval) clearInterval(pollInterval); };
	});

	function notifyOnce() {
		if (!notified) {
			notified = true;
			onComplete();
		}
	}

	// Auto-notify parent when connected
	$effect(() => {
		if (phase === 'connected') notifyOnce();
	});

	async function checkGateway() {
		if (!isTauri) {
			// Browser dev mode: just check if gateway is reachable
			try {
				const res = await fetch('http://localhost:8080/api/status', { signal: AbortSignal.timeout(2000) });
				if (res.ok) {
					phase = 'connected';
					return;
				}
			} catch {}
			phase = 'pending';
			return;
		}

		try {
			const { invoke } = await import('@tauri-apps/api/core');
			const result = await invoke<{ running: boolean }>('check_gateway');
			if (result.running) {
				phase = 'connected';
			} else {
				// Auto-start the gateway
				await startGateway();
			}
		} catch {
			phase = 'pending';
		}
	}

	async function startGateway() {
		if (!isTauri) return;
		phase = 'starting';
		error = '';

		try {
			const { invoke } = await import('@tauri-apps/api/core');
			await invoke<{ running: boolean; pid: number | null }>('start_gateway');
			phase = 'waiting';
			startPolling();
		} catch (e) {
			error = String(e);
			phase = 'error';
		}
	}

	function startPolling() {
		pollCount = 0;
		if (pollInterval) clearInterval(pollInterval);
		pollInterval = setInterval(async () => {
			pollCount++;
			try {
				if (isTauri) {
					const { invoke } = await import('@tauri-apps/api/core');
					const result = await invoke<{ running: boolean }>('check_gateway');
					if (result.running) {
						phase = 'connected';
						if (pollInterval) clearInterval(pollInterval);
						return;
					}
				} else {
					const res = await fetch('http://localhost:8080/api/status', { signal: AbortSignal.timeout(2000) });
					if (res.ok) {
						phase = 'connected';
						if (pollInterval) clearInterval(pollInterval);
						return;
					}
				}
			} catch {}
			// Timeout after 30s (15 polls x 2s)
			if (pollCount >= 15) {
				if (pollInterval) clearInterval(pollInterval);
				error = 'Gateway did not respond after 30 seconds. Check that vulti-core is installed correctly.';
				phase = 'error';
			}
		}, 2000);
	}
</script>

<div class="space-y-6">
	<div>
		<div class="mb-3 flex items-center gap-3">
			<div class="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-emerald-500/10">
				<svg class="h-7 w-7 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3m-19.5 0a4.5 4.5 0 01.9-2.7L5.737 5.1a3.375 3.375 0 012.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 01.9 2.7m0 0a3 3 0 01-3 3m0 3h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008zm-3 6h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008z" />
				</svg>
			</div>
			<div>
				<h2 class="text-2xl font-bold text-ink">Gateway</h2>
				<p class="text-ink-dim">The AI engine that powers your agents.</p>
			</div>
		</div>
	</div>

	{#if phase === 'checking'}
		<div class="flex items-center gap-3 rounded-xl border border-border bg-surface p-5">
			<div class="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent"></div>
			<span class="text-sm text-ink-dim">Checking gateway...</span>
		</div>

	{:else if phase === 'not_installed'}
		<div class="rounded-xl border border-yellow-500/20 bg-yellow-500/5 p-5">
			<p class="text-sm text-ink">Vulti Core is not installed.</p>
			<p class="mt-1 text-xs text-ink-muted">Install it to get started.</p>
		</div>
		<code class="block rounded-lg bg-paper-shadow px-4 py-3 text-sm text-ink-dim">
			curl -fsSL https://vulti.ai/install | bash
		</code>

	{:else if phase === 'starting' || phase === 'waiting'}
		<div class="flex items-center gap-3 rounded-xl border border-border bg-surface p-5">
			<div class="h-5 w-5 animate-spin rounded-full border-2 border-emerald-400 border-t-transparent"></div>
			<div>
				<span class="text-sm text-ink">{phase === 'starting' ? 'Starting Vulti Core...' : 'Waiting for gateway to be ready...'}</span>
				<p class="text-xs text-ink-muted">This may take a few seconds on first launch.</p>
			</div>
		</div>

	{:else if phase === 'error'}
		<div class="rounded-xl border border-red-500/20 bg-red-500/5 p-5">
			<p class="text-sm text-ink">Failed to start gateway</p>
			<p class="mt-1 text-xs text-ink-muted">{error}</p>
		</div>
		<button
			onclick={startGateway}
			class="w-full rounded-lg bg-primary py-3 text-sm font-medium text-white hover:bg-primary-hover"
		>
			Retry
		</button>

	{:else if phase === 'connected'}
		<div class="rounded-xl border border-green-500/20 bg-green-500/5 p-5">
			<div class="flex items-center gap-3">
				<div class="flex h-8 w-8 items-center justify-center rounded-full bg-green-500/10">
					<svg class="h-5 w-5 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" />
					</svg>
				</div>
				<div>
					<p class="font-medium text-green-400">Gateway Running</p>
					<p class="text-sm text-ink-muted">Gateway is active on <code class="rounded bg-paper-shadow px-1.5 py-0.5 text-xs font-mono">localhost:8080</code></p>
				</div>
			</div>
		</div>
	{/if}
</div>
