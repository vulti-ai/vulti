<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import type { Widget } from '$lib/api';
	import MarkdownWidget from './widgets/MarkdownWidget.svelte';
	import KvWidget from './widgets/KvWidget.svelte';
	import TableWidget from './widgets/TableWidget.svelte';
	import ImageWidget from './widgets/ImageWidget.svelte';
	import StatusWidget from './widgets/StatusWidget.svelte';
	import StatGridWidget from './widgets/StatGridWidget.svelte';
	import BarChartWidget from './widgets/BarChartWidget.svelte';
	import ProgressWidget from './widgets/ProgressWidget.svelte';
	import ButtonWidget from './widgets/ButtonWidget.svelte';
	import FormWidget from './widgets/FormWidget.svelte';
	import ToggleListWidget from './widgets/ToggleListWidget.svelte';
	import ActionListWidget from './widgets/ActionListWidget.svelte';
	import EmptyWidget from './widgets/EmptyWidget.svelte';

	let { widgets, tab }: { widgets: Widget[]; tab: string } = $props();

	const COMPONENTS: Record<string, any> = {
		markdown: MarkdownWidget,
		kv: KvWidget,
		table: TableWidget,
		image: ImageWidget,
		status: StatusWidget,
		stat_grid: StatGridWidget,
		bar_chart: BarChartWidget,
		progress: ProgressWidget,
		button: ButtonWidget,
		form: FormWidget,
		toggle_list: ToggleListWidget,
		action_list: ActionListWidget,
		empty: EmptyWidget,
	};

	async function restoreDefaults() {
		await store.clearPaneWidgets(tab);
	}
</script>

<div class="flex h-full flex-col">
	<div class="flex shrink-0 items-center justify-end border-b border-border px-6 py-2">
		<button
			class="text-xs text-ink-muted hover:text-ink transition-colors"
			onclick={restoreDefaults}
		>
			Restore defaults
		</button>
	</div>

	<div class="flex-1 overflow-y-auto p-6 space-y-4">
		{#each widgets as widget (widget.id)}
			{@const Comp = COMPONENTS[widget.type]}
			<div class="rounded-xl border border-border bg-surface p-4">
				{#if widget.title}
					<h3 class="mb-3 text-sm font-semibold text-ink">{widget.title}</h3>
				{/if}
				{#if Comp}
					<svelte:component this={Comp} data={widget.data} />
				{:else}
					<p class="text-xs text-ink-muted">Unknown widget type: {widget.type}</p>
				{/if}
			</div>
		{/each}
	</div>
</div>
