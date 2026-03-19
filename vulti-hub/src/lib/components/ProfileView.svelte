<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { marked } from 'marked';

	// Cache parsed markdown so marked() doesn't re-run on every render
	let soulHtml = $derived(store.soul ? marked(store.soul) : '');

	// Split memories on § separator into individual entries
	let memoryEntries = $derived(
		store.memories.memory
			? store.memories.memory.split('§').map(s => s.trim()).filter(Boolean)
			: []
	);
	let userEntries = $derived(
		store.memories.user
			? store.memories.user.split('§').map(s => s.trim()).filter(Boolean)
			: []
	);
</script>

<div class="h-full overflow-y-auto">
	<div class="mx-auto max-w-4xl space-y-8 p-6">

		<!-- Personality -->
		<section>
			<h3 class="mb-3 text-sm font-medium uppercase text-ink-muted">Personality</h3>
			<p class="mb-3 text-xs text-ink-faint">Who this agent should act like — their voice, tone, and character.</p>
			{#if store.soul}
				<div class="prose prose-sm max-w-none rounded-lg border border-border bg-surface p-4 text-ink">
					{@html soulHtml}
				</div>
			{:else}
				<p class="text-sm text-ink-muted italic">No personality defined yet.</p>
			{/if}
		</section>

		<!-- Understanding -->
		<section>
			<h3 class="mb-3 text-sm font-medium uppercase text-ink-muted">
				Understanding
				{#if userEntries.length > 0}
					<span class="ml-1 text-ink-faint font-normal normal-case">({userEntries.length} entries)</span>
				{/if}
			</h3>
			<p class="mb-3 text-xs text-ink-faint">What this agent knows about you — your preferences, context, and how you work.</p>
			{#if userEntries.length > 0}
				<div class="space-y-2">
					{#each userEntries as entry}
						<div class="rounded-lg border border-border bg-surface px-4 py-3 text-sm text-ink leading-relaxed">
							{entry}
						</div>
					{/each}
				</div>
			{:else}
				<p class="text-sm text-ink-muted italic">No understanding built yet — this grows as the agent learns about you.</p>
			{/if}
		</section>

		<!-- Memory -->
		<section>
			<h3 class="mb-3 text-sm font-medium uppercase text-ink-muted">
				Memory
				{#if memoryEntries.length > 0}
					<span class="ml-1 text-ink-faint font-normal normal-case">({memoryEntries.length} entries)</span>
				{/if}
			</h3>
			<p class="mb-3 text-xs text-ink-faint">Important things this agent remembers about their service to you.</p>
			{#if memoryEntries.length > 0}
				<div class="space-y-2">
					{#each memoryEntries as entry}
						<div class="rounded-lg border border-border bg-surface px-4 py-3 text-sm text-ink leading-relaxed">
							{entry}
						</div>
					{/each}
				</div>
			{:else}
				<p class="text-sm text-ink-muted italic">No memories yet — the agent saves important things here over time.</p>
			{/if}
		</section>

	</div>
</div>
