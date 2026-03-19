<script lang="ts">
	let { data }: { data: { columns?: number; stats?: { label: string; value: string | number; unit?: string }[] } } = $props();
	let cols = $derived(data.columns || 2);
</script>

<div class="grid gap-3" style="grid-template-columns: repeat({cols}, minmax(0, 1fr));">
	{#each data.stats || [] as stat}
		<div class="rounded-xl border border-border bg-surface p-4">
			<p class="text-xs text-ink-muted">{stat.label}</p>
			<p class="mt-1 text-2xl font-bold text-ink">
				{stat.value}{#if stat.unit}<span class="ml-1 text-sm font-normal text-ink-muted">{stat.unit}</span>{/if}
			</p>
		</div>
	{/each}
</div>
