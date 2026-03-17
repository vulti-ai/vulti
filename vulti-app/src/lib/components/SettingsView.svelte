<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { clearToken } from '$lib/api';
	import { onMount } from 'svelte';

	let theme = $state<'dark' | 'light'>(
		(typeof localStorage !== 'undefined' && localStorage.getItem('vulti-theme') as 'dark' | 'light') || 'light'
	);

	$effect(() => {
		document.documentElement.classList.toggle('dark', theme === 'dark');
		document.documentElement.classList.toggle('light', theme === 'light');
		localStorage.setItem('vulti-theme', theme);
		const meta = document.querySelector('meta[name="theme-color"]');
		if (meta) meta.setAttribute('content', theme === 'dark' ? '#1E1C1A' : '#F5F0E8');
	});
	let secretsExpanded = $state<Record<string, boolean>>({});

	onMount(() => {
		store.loadStatus();
		store.loadSecrets();
		store.loadOAuth();
		store.loadChannels();
		store.loadIntegrations();
	});

	function logout() {
		clearToken();
		store.authenticated = false;
		store.ws.disconnect();
	}

	function reload() {
		store.loadStatus();
		store.loadSecrets();
		store.loadOAuth();
		store.loadChannels();
		store.loadIntegrations();
	}

	function toggleCategory(cat: string) {
		secretsExpanded[cat] = !secretsExpanded[cat];
	}

	function getSecretsByCategory(): Record<string, typeof store.secrets> {
		const grouped: Record<string, typeof store.secrets> = {};
		for (const s of store.secrets) {
			if (!grouped[s.category]) grouped[s.category] = [];
			grouped[s.category].push(s);
		}
		return grouped;
	}

	function getIntegrationsByCategory(): Record<string, typeof store.integrations> {
		const grouped: Record<string, typeof store.integrations> = {};
		for (const i of store.integrations) {
			const cat = i.category || 'Other';
			if (!grouped[cat]) grouped[cat] = [];
			grouped[cat].push(i);
		}
		return grouped;
	}

	function statusColor(status: string): string {
		if (status === 'connected') return 'bg-green-500';
		if (status === 'degraded') return 'bg-yellow-500';
		if (status === 'configured') return 'bg-blue-500';
		return 'bg-red-500';
	}

	function statusBadge(status: string): string {
		if (status === 'connected') return 'bg-green-500/10 text-green-400';
		if (status === 'degraded') return 'bg-yellow-500/10 text-yellow-400';
		if (status === 'configured') return 'bg-blue-500/10 text-blue-400';
		return 'bg-red-500/10 text-red-400';
	}
</script>

<div class="flex h-full flex-col">
	<header class="flex h-14 shrink-0 items-center justify-between border-b border-border px-6">
		<h2 class="font-semibold">Settings</h2>
		<button
			onclick={reload}
			class="rounded-lg bg-surface-hover px-3 py-1.5 text-xs text-slate-300 hover:bg-surface-active"
		>
			Refresh
		</button>
	</header>

	<div class="flex-1 overflow-y-auto p-6">
		<div class="mx-auto max-w-3xl space-y-8">

			<!-- Gateway Status -->
			<section>
				<h3 class="mb-3 text-sm font-medium uppercase text-slate-400">Gateway Status</h3>
				<div class="rounded-xl border border-border bg-surface p-4">
					<div class="flex items-center gap-2">
						<div
							class="h-2.5 w-2.5 rounded-full"
							class:bg-green-500={store.systemStatus.gateway_state === 'running'}
							class:bg-red-500={store.systemStatus.gateway_state !== 'running'}
						></div>
						<span class="text-sm font-medium capitalize">{store.systemStatus.gateway_state}</span>
						{#if store.systemStatus.pid}
							<span class="text-xs text-slate-500">PID {store.systemStatus.pid}</span>
						{/if}
					</div>
				</div>
			</section>

			<!-- Integrations (rich cards) -->
			{#if store.integrations.length > 0}
				{#each Object.entries(getIntegrationsByCategory()) as [category, items]}
					<section>
						<h3 class="mb-3 text-sm font-medium uppercase text-slate-400">{category}</h3>
						<div class="space-y-2">
							{#each items as integ}
								<div class="rounded-xl border border-border bg-surface p-4">
									<div class="flex items-center justify-between">
										<div class="flex items-center gap-3">
											<div class="h-2.5 w-2.5 rounded-full {statusColor(integ.status)}"></div>
											<span class="text-sm font-medium">{integ.name}</span>
										</div>
										<span class="rounded-full px-2 py-0.5 text-xs capitalize {statusBadge(integ.status)}">
											{integ.status}
										</span>
									</div>
									{#if integ.details && Object.keys(integ.details).length > 0}
										<div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 pl-[22px]">
											{#each Object.entries(integ.details) as [key, val]}
												{#if val && val !== ''}
													{#if key === 'services' && Array.isArray(val)}
														<span class="text-xs text-slate-400">{val.join(', ')}</span>
													{:else if key === 'note'}
														<span class="text-xs text-yellow-400/80">{val}</span>
													{:else}
														<span class="text-xs text-slate-400">
															<span class="text-slate-500">{key}:</span> {val}
														</span>
													{/if}
												{/if}
											{/each}
										</div>
									{/if}
								</div>
							{/each}
						</div>
					</section>
				{/each}
			{/if}

			<!-- Connected Channels -->
			{#if Object.keys(store.channels.platforms).length > 0}
				<section>
					<h3 class="mb-3 text-sm font-medium uppercase text-slate-400">Connected Channels</h3>
					<div class="space-y-2">
						{#each Object.entries(store.channels.platforms) as [platform, chats]}
							{#if chats.length > 0}
								<div class="rounded-xl border border-border bg-surface p-4">
									<p class="mb-2 text-xs font-medium uppercase text-primary">{platform}</p>
									<div class="space-y-1">
										{#each chats as chat}
											<div class="flex items-center gap-2 text-sm text-slate-300">
												<span class="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-slate-400">{chat.type}</span>
												<span>{chat.name}</span>
											</div>
										{/each}
									</div>
								</div>
							{/if}
						{/each}
					</div>
				</section>
			{/if}

			<!-- OAuth Tokens -->
			{#if store.oauthTokens.length > 0}
				<section>
					<h3 class="mb-3 text-sm font-medium uppercase text-slate-400">OAuth Tokens</h3>
					<div class="space-y-2">
						{#each store.oauthTokens as token}
							<div class="flex items-center justify-between rounded-xl border border-border bg-surface p-4">
								<div>
									<p class="text-sm font-medium">{token.service}</p>
									{#if token.scopes}
										<p class="text-xs text-slate-500">{token.scopes.length} scopes</p>
									{/if}
								</div>
								<div class="flex items-center gap-2">
									{#if token.has_refresh}
										<span class="rounded-full bg-blue-500/10 px-2 py-0.5 text-xs text-blue-400">Refresh</span>
									{/if}
									<span class="rounded-full px-2 py-0.5 text-xs
										{token.valid ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}">
										{token.valid ? 'Valid' : 'Invalid'}
									</span>
								</div>
							</div>
						{/each}
					</div>
				</section>
			{/if}

			<!-- API Keys & Secrets -->
			{#if store.secrets.length > 0}
				<section>
					<h3 class="mb-3 text-sm font-medium uppercase text-slate-400">API Keys & Secrets</h3>
					<div class="space-y-2">
						{#each Object.entries(getSecretsByCategory()) as [category, items]}
							<div class="rounded-xl border border-border bg-surface">
								<button
									onclick={() => toggleCategory(category)}
									class="flex w-full items-center justify-between p-4"
								>
									<div class="flex items-center gap-2">
										<span class="text-sm font-medium">{category}</span>
										<span class="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-400">{items.length}</span>
										<span class="text-xs text-slate-500">{items.filter(s => s.is_set).length}/{items.length} set</span>
									</div>
									<svg
										class="h-4 w-4 text-slate-400 transition-transform"
										class:rotate-180={secretsExpanded[category]}
										fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"
									>
										<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
									</svg>
								</button>
								{#if secretsExpanded[category]}
									<div class="border-t border-border px-4 pb-3">
										{#each items as secret}
											<div class="flex items-center justify-between py-2">
												<span class="font-mono text-xs text-slate-300">{secret.key}</span>
												<div class="flex items-center gap-2">
													<span class="font-mono text-xs text-slate-500">{secret.masked_value}</span>
													<div
														class="h-2 w-2 rounded-full"
														class:bg-green-500={secret.is_set}
														class:bg-red-500={!secret.is_set}
													></div>
												</div>
											</div>
										{/each}
									</div>
								{/if}
							</div>
						{/each}
					</div>
				</section>
			{/if}

			<!-- Appearance -->
			<section>
				<h3 class="mb-3 text-sm font-medium uppercase text-slate-400">Appearance</h3>
				<div class="rounded-xl border border-border bg-surface p-4">
					<div class="flex items-center justify-between">
						<div>
							<p class="text-sm font-medium">Theme</p>
							<p class="text-xs text-slate-400">Choose light or dark mode</p>
						</div>
						<select
							bind:value={theme}
							class="rounded-lg border border-border bg-slate-800 px-3 py-1.5 text-sm text-white"
						>
							<option value="dark">Dark</option>
							<option value="light">Light</option>
						</select>
					</div>
				</div>
			</section>

			<!-- Account -->
			<section>
				<h3 class="mb-3 text-sm font-medium uppercase text-slate-400">Account</h3>
				<button
					onclick={logout}
					class="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm text-red-400 hover:bg-red-500/20"
				>
					Disconnect
				</button>
			</section>
		</div>
	</div>
</div>
