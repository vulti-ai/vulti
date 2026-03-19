<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	let { data }: { data: { fields?: { name: string; label: string; type?: string; placeholder?: string }[]; submit_label?: string; message_template?: string } } = $props();

	let values = $state<Record<string, string>>({});

	function submit() {
		let msg = data.message_template || '';
		for (const [key, val] of Object.entries(values)) {
			msg = msg.replaceAll(`{${key}}`, val);
		}
		if (msg.trim()) {
			store.sendMessage(msg);
		}
		// Clear form
		values = {};
	}
</script>

<div class="space-y-3">
	{#each data.fields || [] as field}
		<div>
			<label class="mb-1 block text-xs font-medium text-ink-muted">{field.label}</label>
			<input
				type={field.type || 'text'}
				placeholder={field.placeholder || ''}
				class="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-muted/50 focus:border-primary focus:outline-none"
				bind:value={values[field.name]}
			/>
		</div>
	{/each}
	<button
		class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-hover transition-colors"
		onclick={submit}
	>
		{data.submit_label || 'Submit'}
	</button>
</div>
