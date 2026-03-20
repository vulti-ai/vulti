<script lang="ts">
	let { data }: { data: { columns?: string[]; rows?: string[][] } } = $props();
</script>

<div class="overflow-x-auto">
	<table class="w-full text-left text-sm">
		{#if data.columns}
			<thead>
				<tr class="border-b border-border">
					{#each data.columns as col}
						<th class="px-3 py-2 text-xs font-medium text-ink-muted">{col}</th>
					{/each}
				</tr>
			</thead>
		{/if}
		<tbody>
			{#each data.rows || [] as row}
				<tr class="border-b border-border/50">
					{#each row as cell}
						<td class="px-3 py-2 text-ink-dim">{cell}</td>
					{/each}
				</tr>
			{/each}
		</tbody>
	</table>
</div>
