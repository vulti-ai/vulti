<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { marked } from 'marked';
	import { onMount } from 'svelte';

	let editing = $state(false);
	let editContent = $state('');
	let saving = $state(false);

	onMount(() => {
		store.loadSoul();
	});

	function startEdit() {
		editContent = store.soul;
		editing = true;
	}

	async function save() {
		saving = true;
		try {
			await store.saveSoul(editContent);
			editing = false;
		} finally {
			saving = false;
		}
	}

	function cancel() {
		editing = false;
	}

	function getRendered(): string {
		if (!store.soul) return '<p class="text-slate-500">No soul file found.</p>';
		return marked.parse(store.soul) as string;
	}
</script>

<div class="flex h-full flex-col">
	<header class="flex h-14 shrink-0 items-center justify-between border-b border-border px-6">
		<h2 class="font-semibold">Soul</h2>
		{#if !editing}
			<button
				onclick={startEdit}
				class="rounded-lg bg-surface-hover px-3 py-1.5 text-xs text-slate-300 hover:bg-surface-active"
			>
				Edit
			</button>
		{/if}
	</header>

	<div class="flex-1 overflow-y-auto p-6">
		<div class="mx-auto max-w-3xl">
			<p class="mb-4 text-xs text-slate-500">
				Vulti's identity, personality, and operating principles. This defines how the agent thinks and behaves.
			</p>

			{#if editing}
				<textarea
					bind:value={editContent}
					class="min-h-[600px] w-full rounded-xl border border-border bg-surface p-4 font-mono text-sm text-slate-200 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
					spellcheck="false"
				></textarea>
				<div class="mt-4 flex gap-2">
					<button
						onclick={save}
						disabled={saving}
						class="rounded-lg bg-primary px-4 py-2 text-sm text-white hover:bg-primary-hover disabled:opacity-50"
					>
						{saving ? 'Saving...' : 'Save'}
					</button>
					<button
						onclick={cancel}
						class="rounded-lg bg-surface-hover px-4 py-2 text-sm text-slate-300 hover:bg-surface-active"
					>
						Cancel
					</button>
				</div>
			{:else}
				<div class="prose rounded-xl border border-border bg-surface p-6 text-sm text-slate-200">
					{@html getRendered()}
				</div>
			{/if}
		</div>
	</div>
</div>
