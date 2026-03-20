<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	let { data }: { data: { icon?: string; heading?: string; subtext?: string; button?: { label: string; message: string } } } = $props();

	const icons: Record<string, string> = {
		clock: 'M12 8v4l3 3 M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z',
		bolt: 'M13 2L3 14h9l-1 10 10-12h-9l1-10z',
		book: 'M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z',
		search: 'M11 3a8 8 0 1 0 0 16 8 8 0 0 0 0-16z M21 21l-4.35-4.35',
	};
</script>

<div class="flex flex-col items-center justify-center py-8 text-center">
	{#if data.icon && icons[data.icon]}
		<div class="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-ink/5">
			<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="text-ink-muted">
				{#each icons[data.icon].split(' M') as segment, i}
					<path d="{i > 0 ? 'M' : ''}{segment}" />
				{/each}
			</svg>
		</div>
	{/if}
	{#if data.heading}
		<p class="text-sm font-medium text-ink-dim">{data.heading}</p>
	{/if}
	{#if data.subtext}
		<p class="mt-1 text-xs text-ink-muted">{data.subtext}</p>
	{/if}
	{#if data.button}
		<button
			class="mt-4 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-hover transition-colors"
			onclick={() => store.sendMessage(data.button!.message)}
		>
			{data.button.label}
		</button>
	{/if}
</div>
