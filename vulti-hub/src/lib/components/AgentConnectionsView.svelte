<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { onMount } from 'svelte';

	let agent = $derived(store.activeAgent);
	let allowed = $derived(new Set(agent?.allowedConnections ?? []));

	onMount(() => {
		store.loadConnections();
	});

	async function toggle(connName: string) {
		if (!agent) return;
		const current = agent.allowedConnections ?? [];
		const updated = current.includes(connName)
			? current.filter(c => c !== connName)
			: [...current, connName];
		await store.updateAgentConnections(agent.id, updated);
	}

	function typeLabel(t: string): string {
		switch (t) {
			case 'mcp': return 'MCP';
			case 'api_key': return 'API Key';
			case 'oauth': return 'OAuth';
			case 'custom': return 'Custom';
			default: return t;
		}
	}
</script>

<div class="p-4 space-y-4">
	<div class="flex items-center justify-between">
		<p class="text-xs text-ink-muted">Choose which connections this agent can use.</p>
		{#if allowed.size > 0}
			<span class="rounded-full bg-green-500/15 px-2 py-0.5 text-[10px] font-medium text-green-600">{allowed.size} active</span>
		{/if}
	</div>

	{#if store.connections.length === 0}
		<div class="rounded-lg border border-dashed border-border py-6 text-center">
			<p class="text-xs text-ink-muted">No connections defined yet.</p>
			<p class="text-[10px] text-ink-faint mt-1">Add connections in global Settings.</p>
		</div>
	{:else}
		<div class="space-y-1.5">
			{#each store.connections as conn}
				{@const isAllowed = allowed.has(conn.name)}
				<button
					onclick={() => toggle(conn.name)}
					class="conn-row"
					class:active={isAllowed}
				>
					<!-- Toggle indicator -->
					<div class="toggle-box" class:on={isAllowed}>
						{#if isAllowed}
							<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
								<path d="M20 6 9 17l-5-5" />
							</svg>
						{/if}
					</div>

					<!-- Info -->
					<div class="min-w-0 flex-1">
						<div class="flex items-center gap-2">
							<p class="text-sm font-medium" class:text-ink={isAllowed} class:text-ink-dim={!isAllowed}>{conn.name}</p>
							<span class="text-[10px] text-ink-faint">{typeLabel(conn.type)}</span>
						</div>
						<p class="text-xs truncate" class:text-ink-muted={isAllowed} class:text-ink-faint={!isAllowed}>{conn.description}</p>
					</div>

					<!-- Tags -->
					<div class="flex gap-1 flex-shrink-0">
						{#each conn.tags.slice(0, 2) as tag}
							<span class="rounded-full px-1.5 py-0.5 text-[10px] {isAllowed ? 'bg-green-500/10 text-green-600' : 'bg-ink/5 text-ink-faint'}"
							>{tag}</span>
						{/each}
					</div>
				</button>
			{/each}
		</div>
	{/if}
</div>

<style>
	.conn-row {
		width: 100%;
		display: flex;
		align-items: center;
		gap: 0.75rem;
		border-radius: 0.5rem;
		border: 1px solid var(--color-border);
		padding: 0.625rem 0.75rem;
		text-align: left;
		transition: all 150ms ease;
		background: var(--color-surface);
		opacity: 0.55;
	}
	.conn-row:hover {
		background: var(--color-surface-hover);
		opacity: 0.8;
	}
	.conn-row.active {
		opacity: 1;
		border-color: #22c55e40;
		background: #22c55e08;
	}
	.conn-row.active:hover {
		background: #22c55e12;
	}

	.toggle-box {
		flex-shrink: 0;
		width: 1.125rem;
		height: 1.125rem;
		border-radius: 0.25rem;
		border: 2px solid var(--color-ink-faint);
		display: flex;
		align-items: center;
		justify-content: center;
		transition: all 150ms ease;
	}
	.toggle-box.on {
		background: #22c55e;
		border-color: #22c55e;
	}
</style>
