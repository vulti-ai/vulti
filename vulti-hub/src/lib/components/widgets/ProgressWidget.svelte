<script lang="ts">
	let { data }: { data: { label?: string; percent?: number; variant?: string; indeterminate?: boolean } } = $props();

	const barColors: Record<string, string> = {
		success: 'bg-green-500',
		warning: 'bg-yellow-500',
		error: 'bg-red-500',
		info: 'bg-primary',
	};
	let barColor = $derived(barColors[data.variant || 'info'] || barColors.info);
</script>

<div class="space-y-1">
	{#if data.label}
		<div class="flex items-center justify-between">
			<span class="text-xs text-ink-muted">{data.label}</span>
			{#if !data.indeterminate && data.percent != null}
				<span class="text-xs font-medium text-ink-dim">{data.percent}%</span>
			{/if}
		</div>
	{/if}
	<div class="h-2 rounded-full bg-ink/5 overflow-hidden">
		{#if data.indeterminate}
			<div class="h-full w-1/3 rounded-full {barColor} animate-pulse"></div>
		{:else}
			<div class="h-full rounded-full {barColor} transition-all" style="width: {data.percent || 0}%;"></div>
		{/if}
	</div>
</div>
