<script lang="ts">
	import { onMount } from 'svelte';
	import { setToken } from '$lib/api';

	let { status, onComplete }: {
		status: 'pending' | 'connected';
		onComplete: () => void;
	} = $props();

	// svelte-ignore state_referenced_locally
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

	async function notifyOnce() {
		if (!notified) {
			notified = true;
			if (isTauri) {
				try {
					const { invoke } = await import('@tauri-apps/api/core');
					const token = await invoke<string>('get_gateway_token');
					if (token) setToken(token);
				} catch {}
			}
			onComplete();
		}
	}

	$effect(() => {
		if (phase === 'connected') notifyOnce();
	});

	async function checkGateway() {
		if (!isTauri) {
			try {
				const res = await fetch('http://localhost:8080/api/status', { signal: AbortSignal.timeout(2000) });
				if (res.ok) { phase = 'connected'; return; }
			} catch {}
			phase = 'checking';
			return;
		}
		try {
			const { invoke } = await import('@tauri-apps/api/core');
			const result = await invoke<{ running: boolean }>('check_gateway');
			if (result.running) { phase = 'connected'; }
			else { await startGateway(); }
		} catch { phase = 'checking'; }
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
		} catch (e) { error = String(e); phase = 'error'; }
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
					if (result.running) { phase = 'connected'; if (pollInterval) clearInterval(pollInterval); return; }
				} else {
					const res = await fetch('http://localhost:8080/api/status', { signal: AbortSignal.timeout(2000) });
					if (res.ok) { phase = 'connected'; if (pollInterval) clearInterval(pollInterval); return; }
				}
			} catch {}
			if (pollCount >= 15) {
				if (pollInterval) clearInterval(pollInterval);
				error = 'Gateway did not respond after 30 seconds.';
				phase = 'error';
			}
		}, 2000);
	}
</script>

<div class="space-y-4">
	<div>
		<h3 class="text-lg font-semibold text-ink">Gateway</h3>
		<p class="text-sm text-ink-muted">The engine that powers your agents.</p>
	</div>

	{#if phase === 'checking'}
		<div class="flex items-center gap-3 rounded-xl border border-border bg-surface p-4">
			<div class="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent"></div>
			<span class="text-sm text-ink-dim">Checking...</span>
		</div>

	{:else if phase === 'not_installed'}
		<div class="rounded-xl border border-yellow-500/20 bg-yellow-500/5 p-4 text-sm text-ink">
			Not installed. Run: <code class="rounded bg-paper-shadow px-1.5 py-0.5 text-xs font-mono">curl -fsSL https://vulti.ai/install | bash</code>
		</div>

	{:else if phase === 'starting' || phase === 'waiting'}
		<div class="flex items-center gap-3 rounded-xl border border-border bg-surface p-4">
			<div class="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent"></div>
			<span class="text-sm text-ink-dim">Starting...</span>
		</div>

	{:else if phase === 'error'}
		<div class="rounded-xl border border-red-500/20 bg-red-500/5 p-4 text-sm text-ink">
			{error}
		</div>
		<button onclick={startGateway} class="w-full rounded-lg bg-primary py-2.5 text-sm font-medium text-white hover:bg-primary-hover">
			Retry
		</button>

	{:else if phase === 'connected'}
		<div class="rounded-xl border border-yellow-500/20 bg-yellow-500/5 p-5">
			<div class="flex items-center gap-3">
				<svg class="h-5 w-5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" />
				</svg>
				<div>
					<p class="font-medium text-green-500">Gateway Running</p>
					<p class="text-sm text-ink-muted">Gateway is active on <code class="rounded bg-paper-shadow px-1.5 py-0.5 text-xs font-mono">localhost:8080</code></p>
				</div>
			</div>
		</div>
	{/if}
</div>
