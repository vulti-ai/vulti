<script lang="ts">
	let { data }: { data: { entries?: { key: string; value: string; mono?: boolean; masked?: boolean }[] } } = $props();

	function mask(val: string): string {
		if (val.length <= 8) return val;
		return val.slice(0, 4) + '****' + val.slice(-4);
	}
</script>

<div class="space-y-2">
	{#each data.entries || [] as entry}
		<div class="flex items-baseline justify-between gap-4">
			<span class="shrink-0 text-xs text-ink-muted">{entry.key}</span>
			<span class="text-sm text-ink {entry.mono ? 'font-mono' : ''} text-right truncate">
				{entry.masked ? mask(entry.value) : entry.value}
			</span>
		</div>
	{/each}
</div>
