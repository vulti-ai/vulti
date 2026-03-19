<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	let { data }: { data: { items?: { id: string; title: string; subtitle?: string; status?: string; actions?: { label: string; message: string; variant?: string }[] }[] } } = $props();

	const statusDots: Record<string, string> = {
		active: 'bg-green-500',
		paused: 'bg-yellow-500',
		error: 'bg-red-500',
		disabled: 'bg-ink/30',
	};

	const btnStyles: Record<string, string> = {
		primary: 'bg-primary text-white hover:bg-primary-hover',
		secondary: 'bg-surface text-ink-dim hover:bg-surface-hover',
		danger: 'text-red-400 hover:bg-red-50 hover:text-red-600',
	};
</script>

<div class="divide-y divide-border">
	{#each data.items || [] as item}
		<div class="flex items-center gap-3 py-3 px-1">
			{#if item.status}
				<span class="h-2 w-2 shrink-0 rounded-full {statusDots[item.status] || statusDots.active}"></span>
			{/if}
			<div class="flex-1 min-w-0">
				<p class="text-sm font-medium text-ink">{item.title}</p>
				{#if item.subtitle}
					<p class="text-xs text-ink-muted truncate">{item.subtitle}</p>
				{/if}
			</div>
			{#if item.actions}
				<div class="flex items-center gap-2">
					{#each item.actions as action}
						<button
							class="rounded px-2.5 py-1 text-xs font-medium transition-colors {btnStyles[action.variant || 'secondary'] || btnStyles.secondary}"
							onclick={() => store.sendMessage(action.message.replaceAll('{id}', item.id))}
						>{action.label}</button>
					{/each}
				</div>
			{/if}
		</div>
	{/each}
</div>
