<script lang="ts">
	let { data }: { data: { orientation?: string; items?: { label: string; value: number; max?: number }[] } } = $props();
	let isVertical = $derived(data.orientation === 'v');
	let maxVal = $derived(Math.max(...(data.items || []).map(i => i.max || i.value), 1));
</script>

{#if isVertical}
	<div class="flex items-end gap-2" style="height: 120px;">
		{#each data.items || [] as item}
			{@const pct = Math.round((item.value / maxVal) * 100)}
			<div class="flex flex-1 flex-col items-center gap-1">
				<div class="w-full rounded bg-primary" style="height: {pct}%;"></div>
				<span class="text-[10px] text-ink-muted">{item.label}</span>
			</div>
		{/each}
	</div>
{:else}
	<div class="space-y-2">
		{#each data.items || [] as item}
			{@const pct = Math.round((item.value / maxVal) * 100)}
			<div class="flex items-center gap-3">
				<span class="w-24 shrink-0 truncate text-xs text-ink-muted font-mono">{item.label}</span>
				<div class="flex-1 rounded-full bg-primary/20 h-2">
					<div class="rounded-full bg-primary h-2 transition-all" style="width: {pct}%;"></div>
				</div>
				<span class="w-10 text-right text-xs text-ink-muted">{item.value}</span>
			</div>
		{/each}
	</div>
{/if}
