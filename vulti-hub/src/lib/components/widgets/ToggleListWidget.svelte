<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	let { data }: { data: { items?: { id: string; label: string; description?: string; enabled: boolean; tags?: string[] }[]; on_toggle_message?: string } } = $props();

	function toggle(itemId: string, currentState: boolean) {
		const newState = currentState ? 'off' : 'on';
		const msg = (data.on_toggle_message || 'toggle {id} {state}')
			.replaceAll('{id}', itemId)
			.replaceAll('{state}', newState);
		store.sendMessage(msg);
	}
</script>

<div class="divide-y divide-border">
	{#each data.items || [] as item}
		<button
			class="flex w-full items-center gap-3 px-1 py-3 text-left transition-opacity {item.enabled ? '' : 'opacity-50'}"
			onclick={() => toggle(item.id, item.enabled)}
		>
			<div class="flex h-5 w-5 items-center justify-center rounded border transition-colors {item.enabled ? 'border-green-500 bg-green-500/10' : 'border-border'}">
				{#if item.enabled}
					<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" class="text-green-500">
						<path d="M20 6 9 17l-5-5" />
					</svg>
				{/if}
			</div>
			<div class="flex-1 min-w-0">
				<p class="text-sm font-medium text-ink">{item.label}</p>
				{#if item.description}
					<p class="text-xs text-ink-muted truncate">{item.description}</p>
				{/if}
			</div>
			{#if item.tags}
				<div class="flex gap-1">
					{#each item.tags.slice(0, 2) as tag}
						<span class="rounded-full bg-ink/5 px-1.5 py-0.5 text-[10px] text-ink-muted">{tag}</span>
					{/each}
				</div>
			{/if}
		</button>
	{/each}
</div>
