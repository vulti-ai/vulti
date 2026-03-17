<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { onMount } from 'svelte';

	onMount(() => {
		store.loadIntegrations();
		store.loadSecrets();
		store.loadOAuth();
		store.loadChannels();
		store.loadStatus();
	});

	function statusColor(status: string): string {
		if (status === 'connected') return 'text-green-500';
		if (status === 'configured') return 'text-yellow-500';
		if (status === 'degraded') return 'text-orange-400';
		return 'text-red-500';
	}

	function statusDot(status: string): string {
		if (status === 'connected') return 'bg-green-500';
		if (status === 'configured') return 'bg-yellow-500';
		if (status === 'degraded') return 'bg-orange-400';
		return 'bg-red-500';
	}

	function categoryIcon(category: string): string {
		switch (category) {
			case 'Messaging': return 'M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z';
			case 'Cloud': return 'M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z';
			case 'Social': return 'M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z';
			case 'Voice & SMS': return 'M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z';
			case 'Tools': return 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.573-1.066z';
			case 'LLM': return 'M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z';
			default: return 'M13 10V3L4 14h7v7l9-11h-7z';
		}
	}

	// Group integrations by category
	let grouped = $derived(
		store.integrations.reduce((acc, int) => {
			if (!acc[int.category]) acc[int.category] = [];
			acc[int.category].push(int);
			return acc;
		}, {} as Record<string, typeof store.integrations>)
	);

	// Group secrets by category
	let secretGroups = $derived(
		store.secrets.reduce((acc, s) => {
			const cat = s.category || 'Other';
			if (!acc[cat]) acc[cat] = [];
			acc[cat].push(s);
			return acc;
		}, {} as Record<string, typeof store.secrets>)
	);
</script>

<div class="h-full overflow-y-auto">
	<div class="mx-auto max-w-4xl space-y-8 p-6">

		<!-- Gateway Status -->
		<section>
			<div class="flex items-center gap-2 mb-4">
				<div class="h-2.5 w-2.5 rounded-full {store.systemStatus.gateway_state === 'running' ? 'bg-green-500' : 'bg-red-500'}"></div>
				<h3 class="text-sm font-medium uppercase text-ink-muted">Gateway</h3>
				<span class="text-xs text-ink-faint capitalize">{store.systemStatus.gateway_state}</span>
			</div>
			{#if Object.keys(store.systemStatus.platforms).length > 0}
				<div class="flex flex-wrap gap-2">
					{#each Object.entries(store.systemStatus.platforms) as [name, info]}
						<span class="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1 text-xs">
							<span class="h-1.5 w-1.5 rounded-full {info.state === 'connected' ? 'bg-green-500' : 'bg-red-500'}"></span>
							<span class="capitalize text-ink">{name}</span>
						</span>
					{/each}
				</div>
			{/if}
		</section>

		<!-- Integrations -->
		<section>
			<h3 class="mb-4 text-sm font-medium uppercase text-ink-muted">Integrations</h3>
			<div class="space-y-6">
				{#each Object.entries(grouped) as [category, integrations]}
					<div>
						<div class="mb-2 flex items-center gap-2">
							<svg class="h-4 w-4 text-ink-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
								<path stroke-linecap="round" stroke-linejoin="round" d={categoryIcon(category)} />
							</svg>
							<span class="text-xs font-medium text-ink-muted">{category}</span>
						</div>
						<div class="grid gap-2">
							{#each integrations as integration}
								<div class="flex items-center gap-3 rounded-lg border border-border bg-surface px-4 py-3">
									<span class="h-2 w-2 shrink-0 rounded-full {statusDot(integration.status)}"></span>
									<div class="flex-1 min-w-0">
										<div class="flex items-center gap-2">
											<span class="text-sm font-medium text-ink">{integration.name}</span>
											<span class="text-xs capitalize {statusColor(integration.status)}">{integration.status}</span>
										</div>
										{#if integration.details && Object.keys(integration.details).length > 0}
											<div class="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5">
												{#each Object.entries(integration.details) as [key, value]}
													<span class="text-xs text-ink-muted">
														{#if Array.isArray(value)}
															{value.join(', ')}
														{:else}
															{value}
														{/if}
													</span>
												{/each}
											</div>
										{/if}
									</div>
								</div>
							{/each}
						</div>
					</div>
				{/each}
			</div>
		</section>

		<!-- OAuth Tokens -->
		{#if store.oauthTokens.length > 0}
			<section>
				<h3 class="mb-4 text-sm font-medium uppercase text-ink-muted">OAuth Tokens</h3>
				<div class="grid gap-2">
					{#each store.oauthTokens as token}
						<div class="flex items-center gap-3 rounded-lg border border-border bg-surface px-4 py-3">
							<span class="h-2 w-2 shrink-0 rounded-full {token.valid ? 'bg-green-500' : 'bg-red-500'}"></span>
							<span class="text-sm font-medium text-ink">{token.service}</span>
							<span class="text-xs {token.valid ? 'text-green-500' : 'text-red-500'}">{token.valid ? 'Valid' : 'Expired'}</span>
							{#if token.has_refresh}
								<span class="text-xs text-ink-faint">refresh token</span>
							{/if}
						</div>
					{/each}
				</div>
			</section>
		{/if}

		<!-- Channels -->
		{#if Object.keys(store.channels.platforms || {}).length > 0}
			<section>
				<h3 class="mb-4 text-sm font-medium uppercase text-ink-muted">Channels</h3>
				<div class="space-y-3">
					{#each Object.entries(store.channels.platforms || {}) as [platform, channels]}
						{#if channels.length > 0}
							<div>
								<span class="mb-1 block text-xs font-medium capitalize text-ink-muted">{platform}</span>
								<div class="grid gap-1">
									{#each channels as channel}
										<div class="flex items-center gap-2 rounded-md bg-surface px-3 py-2 text-sm">
											<span class="text-ink">{channel.name}</span>
											<span class="text-xs text-ink-faint">{channel.type}</span>
										</div>
									{/each}
								</div>
							</div>
						{/if}
					{/each}
				</div>
			</section>
		{/if}

		<!-- API Keys -->
		{#if store.secrets.length > 0}
			<section>
				<h3 class="mb-4 text-sm font-medium uppercase text-ink-muted">API Keys</h3>
				<div class="space-y-4">
					{#each Object.entries(secretGroups) as [category, secrets]}
						<div>
							<span class="mb-1 block text-xs font-medium text-ink-muted">{category}</span>
							<div class="grid gap-1">
								{#each secrets as secret}
									<div class="flex items-center gap-3 rounded-md bg-surface px-3 py-2">
										<span class="h-1.5 w-1.5 rounded-full {secret.is_set ? 'bg-green-500' : 'bg-red-500'}"></span>
										<span class="flex-1 text-sm text-ink">{secret.key}</span>
										<code class="text-xs text-ink-faint">{secret.masked_value}</code>
									</div>
								{/each}
							</div>
						</div>
					{/each}
				</div>
			</section>
		{/if}

	</div>
</div>
