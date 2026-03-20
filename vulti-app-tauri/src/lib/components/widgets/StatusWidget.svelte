<script lang="ts">
	let { data }: { data: { label?: string; variant?: string; detail?: string } } = $props();

	const dotColors: Record<string, string> = {
		success: 'bg-green-500',
		warning: 'bg-yellow-500',
		error: 'bg-red-500',
		info: 'bg-blue-500',
	};
</script>

<div class="flex items-center gap-3">
	<span class="h-2.5 w-2.5 shrink-0 rounded-full {dotColors[data.variant || 'info'] || dotColors.info}"></span>
	<div>
		<span class="text-sm font-medium text-ink">{data.label || ''}</span>
		{#if data.detail}
			<p class="text-xs text-ink-muted">{data.detail}</p>
		{/if}
	</div>
</div>
