<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { onMount } from 'svelte';

	let { status, onComplete }: {
		status: 'pending' | 'connected' | 'skipped';
		onComplete: () => void;
	} = $props();

	let phase = $state<'checking' | 'not_installed' | 'installing' | 'installed_not_running' | 'connected'>(
		status === 'connected' ? 'connected' : 'checking'
	);
	let tailscaleIp = $state(store.gatewayGlobal.tailscale.ip || '');
	let error = $state('');
	let pollInterval: ReturnType<typeof setInterval> | null = null;

	// Check if we're running inside Tauri
	const isTauri = typeof window !== 'undefined' && '__TAURI__' in window;

	onMount(() => {
		checkTailscale();
		return () => { if (pollInterval) clearInterval(pollInterval); };
	});

	async function checkTailscale() {
		if (!isTauri) {
			// Fallback for browser dev: show manual IP input
			phase = 'installed_not_running';
			return;
		}

		try {
			const { invoke } = await import('@tauri-apps/api/core');
			const result = await invoke<{ installed: boolean; running: boolean; ip: string | null }>('tailscale_status');

			if (result.ip && result.running) {
				tailscaleIp = result.ip;
				phase = 'connected';
				store.updateGlobalSettings({ tailscale: { ip: result.ip, connected: true } });
			} else if (result.installed) {
				phase = 'installed_not_running';
				startPolling();
			} else {
				phase = 'not_installed';
			}
		} catch {
			phase = 'installed_not_running';
		}
	}

	async function installTailscale() {
		if (!isTauri) return;
		phase = 'installing';
		error = '';

		try {
			const { invoke } = await import('@tauri-apps/api/core');
			await invoke<string>('install_tailscale');
			phase = 'installed_not_running';
			startPolling();
		} catch (e) {
			error = `Installation failed: ${e}`;
			phase = 'not_installed';
		}
	}

	async function openTailscale() {
		if (!isTauri) return;
		try {
			const { invoke } = await import('@tauri-apps/api/core');
			await invoke('open_tailscale');
		} catch {}
	}

	function startPolling() {
		// Poll every 3s to detect when Tailscale connects
		if (pollInterval) clearInterval(pollInterval);
		pollInterval = setInterval(async () => {
			if (!isTauri) return;
			try {
				const { invoke } = await import('@tauri-apps/api/core');
				const result = await invoke<{ installed: boolean; running: boolean; ip: string | null }>('tailscale_status');
				if (result.ip && result.running) {
					tailscaleIp = result.ip;
					phase = 'connected';
					store.updateGlobalSettings({ tailscale: { ip: result.ip, connected: true } });
					if (pollInterval) clearInterval(pollInterval);
				}
			} catch {}
		}, 3000);
	}

	function manualConfirm() {
		if (!tailscaleIp.trim() || !/^100\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(tailscaleIp.trim())) {
			error = 'Enter a valid Tailscale IP (starts with 100.)';
			return;
		}
		phase = 'connected';
		store.updateGlobalSettings({ tailscale: { ip: tailscaleIp.trim(), connected: true } });
	}
</script>

<div class="space-y-6">
	<div>
		<div class="mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-500/10">
			<svg class="h-7 w-7 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
				<path stroke-linecap="round" stroke-linejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" />
			</svg>
		</div>
		<h2 class="text-2xl font-bold text-ink">Tailscale</h2>
		<p class="mt-2 text-ink-dim">
			Tailscale creates a secure private network so your phone can reach this Gateway.
		</p>
	</div>

	{#if phase === 'checking'}
		<div class="flex items-center gap-3 rounded-xl border border-border bg-surface p-5">
			<div class="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent"></div>
			<span class="text-sm text-ink-dim">Detecting Tailscale...</span>
		</div>

	{:else if phase === 'not_installed'}
		<div class="rounded-xl border border-yellow-500/20 bg-yellow-500/5 p-5">
			<p class="text-sm text-ink">Tailscale is not installed on this Mac.</p>
			<p class="mt-1 text-xs text-ink-muted">Click below to install it automatically.</p>
		</div>

		{#if error}
			<p class="text-sm text-red-400">{error}</p>
		{/if}

		<button
			onclick={installTailscale}
			class="w-full rounded-lg bg-primary py-3 text-sm font-medium text-white hover:bg-primary-hover"
		>
			Install Tailscale
		</button>

	{:else if phase === 'installing'}
		<div class="flex items-center gap-3 rounded-xl border border-border bg-surface p-5">
			<div class="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent"></div>
			<span class="text-sm text-ink-dim">Installing Tailscale...</span>
		</div>

	{:else if phase === 'installed_not_running'}
		<div class="rounded-xl border border-yellow-500/20 bg-yellow-500/5 p-5">
			<p class="text-sm text-ink">Tailscale is installed but not connected.</p>
			<p class="mt-1 text-xs text-ink-muted">Open Tailscale and sign in. We'll detect it automatically.</p>
		</div>

		<button
			onclick={openTailscale}
			class="w-full rounded-lg bg-primary py-3 text-sm font-medium text-white hover:bg-primary-hover"
		>
			Open Tailscale
		</button>

		<div class="flex items-center gap-3">
			<div class="h-4 w-4 animate-spin rounded-full border-2 border-ink-faint border-t-primary"></div>
			<span class="text-xs text-ink-muted">Waiting for Tailscale to connect...</span>
		</div>

		<!-- Manual fallback -->
		<div class="border-t border-border pt-4">
			<p class="mb-2 text-xs text-ink-muted">Or enter your Tailscale IP manually:</p>
			<div class="flex gap-2">
				<input
					type="text"
					bind:value={tailscaleIp}
					placeholder="100.x.x.x"
					class="flex-1 rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink placeholder-ink-faint focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
					onkeydown={(e) => e.key === 'Enter' && manualConfirm()}
				/>
				<button
					onclick={manualConfirm}
					class="shrink-0 rounded-lg bg-surface-hover px-3 py-2 text-sm text-ink-dim hover:text-ink"
				>
					Confirm
				</button>
			</div>
			{#if error}
				<p class="mt-1 text-xs text-red-400">{error}</p>
			{/if}
		</div>

	{:else if phase === 'connected'}
		<div class="rounded-xl border border-green-500/20 bg-green-500/5 p-5">
			<div class="flex items-center gap-3">
				<div class="flex h-8 w-8 items-center justify-center rounded-full bg-green-500/10">
					<svg class="h-5 w-5 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" />
					</svg>
				</div>
				<div>
					<p class="font-medium text-green-400">Tailscale Connected</p>
					<p class="text-sm text-ink-muted">
						Devices can reach this Gateway at <code class="rounded bg-paper-shadow px-1.5 py-0.5 text-xs font-mono">{tailscaleIp}</code>
					</p>
				</div>
			</div>
		</div>
		<button
			onclick={onComplete}
			class="w-full rounded-lg bg-primary py-3 text-sm font-medium text-white hover:bg-primary-hover"
		>
			Continue
		</button>
	{/if}
</div>
