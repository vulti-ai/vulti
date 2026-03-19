<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	let { data }: { data: { label?: string; message?: string; variant?: string } } = $props();

	const btnStyles: Record<string, string> = {
		primary: 'bg-primary text-white hover:bg-primary-hover',
		secondary: 'bg-surface border border-border text-ink hover:bg-surface-hover',
		danger: 'bg-red-500 text-white hover:bg-red-600',
	};

	function click() {
		if (data.message) {
			store.sendMessage(data.message);
		}
	}
</script>

<button
	class="rounded-lg px-4 py-2 text-sm font-medium transition-colors {btnStyles[data.variant || 'primary'] || btnStyles.primary}"
	onclick={click}
>
	{data.label || 'Action'}
</button>
