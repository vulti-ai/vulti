<script lang="ts">
	import type { ServiceCategory } from '$lib/stores/app.svelte';

	let { type, label, description, category, status = 'disconnected', onConnect, onDisconnect }: {
		type: string;
		label: string;
		description: string;
		category: ServiceCategory;
		status?: 'connected' | 'disconnected' | 'pending';
		onConnect: () => void;
		onDisconnect?: () => void;
	} = $props();

	let expanded = $state(false);
</script>

<div class="rounded-xl border border-border bg-surface">
	<div class="flex items-center justify-between p-4">
		<div class="flex items-center gap-3">
			<div class="h-2.5 w-2.5 rounded-full
				{status === 'connected' ? 'bg-green-500' :
				 status === 'pending' ? 'bg-yellow-500' : 'bg-ink-faint'}"></div>
			<div>
				<p class="text-sm font-medium text-ink">{label}</p>
				<p class="text-xs text-ink-muted">{description}</p>
			</div>
		</div>
		<div class="flex items-center gap-2">
			{#if status === 'connected'}
				<span class="rounded-full bg-green-500/10 px-2 py-0.5 text-xs text-green-400">Connected</span>
				{#if onDisconnect}
					<button onclick={onDisconnect} class="text-xs text-red-400 hover:text-red-300">Disconnect</button>
				{/if}
			{:else}
				<button
					onclick={onConnect}
					class="rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-hover"
				>
					Connect
				</button>
			{/if}
		</div>
	</div>
</div>
