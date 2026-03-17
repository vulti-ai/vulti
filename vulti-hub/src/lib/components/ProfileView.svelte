<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { api } from '$lib/api';
	import { onMount } from 'svelte';
	import { marked } from 'marked';

	onMount(() => {
		store.loadSoul();
		store.loadMemories();
	});

	let editingName = $state(false);
	let nameDraft = $state('');
	let editingPersonality = $state(false);
	let editingMemory = $state(false);
	let editingUser = $state(false);
	let personalityDraft = $state('');
	let memoryDraft = $state('');
	let userDraft = $state('');

	function startEditName() {
		nameDraft = store.activeAgent?.name || '';
		editingName = true;
	}
	async function saveName() {
		if (!nameDraft.trim() || !store.activeAgent) return;
		try {
			await api.updateAgent(store.activeAgent.id, { name: nameDraft.trim() });
			await store.loadAgents();
		} catch {}
		editingName = false;
	}

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

	function startEditPersonality() {
		personalityDraft = store.soul;
		editingPersonality = true;
	}
	async function savePersonality() {
		await store.saveSoul(personalityDraft);
		editingPersonality = false;
	}

	function startEditMemory() {
		memoryDraft = store.memories.memory;
		editingMemory = true;
	}
	async function saveMemory() {
		await store.saveMemory('memory', memoryDraft);
		editingMemory = false;
	}

	function startEditUser() {
		userDraft = store.memories.user;
		editingUser = true;
	}
	async function saveUser() {
		await store.saveMemory('user', userDraft);
		editingUser = false;
	}
</script>

<div class="h-full overflow-y-auto">
	<div class="mx-auto max-w-4xl space-y-8 p-6">

		<!-- Agent Identity -->
		{#if store.activeAgent}
			<section class="flex items-center gap-4">
				<div class="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 text-2xl font-bold text-primary">
					{store.activeAgent.name.charAt(0)}
				</div>
				<div class="flex-1">
					{#if editingName}
						<div class="flex items-center gap-2">
							<input
								type="text"
								bind:value={nameDraft}
								class="rounded-lg border border-border bg-surface px-3 py-1.5 text-xl font-bold text-ink focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
								onkeydown={(e) => e.key === 'Enter' && saveName()}
							/>
							<button onclick={saveName} class="rounded bg-primary px-3 py-1.5 text-xs text-white hover:bg-primary-hover">Save</button>
							<button onclick={() => editingName = false} class="text-xs text-ink-muted hover:text-ink">Cancel</button>
						</div>
					{:else}
						<button onclick={startEditName} class="group flex items-center gap-2" title="Edit name">
							<h2 class="text-2xl font-bold text-ink">{store.activeAgent.name}</h2>
							<svg class="h-4 w-4 text-ink-faint opacity-0 group-hover:opacity-100 transition-opacity" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
								<path stroke-linecap="round" stroke-linejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L6.832 19.82a4.5 4.5 0 01-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 011.13-1.897L16.863 4.487z" />
							</svg>
						</button>
					{/if}
				</div>
			</section>
		{/if}

		<!-- Personality -->
		<section>
			<div class="mb-3 flex items-center justify-between">
				<h3 class="text-sm font-medium uppercase text-ink-muted">Personality</h3>
				{#if editingPersonality}
					<div class="flex gap-2">
						<button onclick={() => editingPersonality = false} class="text-xs text-ink-muted hover:text-ink">Cancel</button>
						<button onclick={savePersonality} class="rounded bg-primary px-3 py-1 text-xs text-white hover:bg-primary-hover">Save</button>
					</div>
				{:else}
					<button onclick={startEditPersonality} class="text-xs text-primary hover:underline">Edit</button>
				{/if}
			</div>
			{#if editingPersonality}
				<textarea
					bind:value={personalityDraft}
					class="h-64 w-full rounded-lg border border-border bg-surface p-4 text-sm text-ink font-mono resize-y focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
				></textarea>
			{:else if store.soul}
				<div class="prose prose-sm max-w-none rounded-lg border border-border bg-surface p-4 text-ink">
					{@html marked(store.soul)}
				</div>
			{:else}
				<p class="text-sm text-ink-muted italic">No personality defined yet.</p>
			{/if}
		</section>

		<!-- Agent Memory -->
		<section>
			<div class="mb-3 flex items-center justify-between">
				<h3 class="text-sm font-medium uppercase text-ink-muted">
					Agent Memory
					{#if memoryEntries.length > 0}
						<span class="ml-1 text-ink-faint font-normal normal-case">({memoryEntries.length} entries)</span>
					{/if}
				</h3>
				{#if editingMemory}
					<div class="flex gap-2">
						<button onclick={() => editingMemory = false} class="text-xs text-ink-muted hover:text-ink">Cancel</button>
						<button onclick={saveMemory} class="rounded bg-primary px-3 py-1 text-xs text-white hover:bg-primary-hover">Save</button>
					</div>
				{:else}
					<button onclick={startEditMemory} class="text-xs text-primary hover:underline">Edit</button>
				{/if}
			</div>
			{#if editingMemory}
				<textarea
					bind:value={memoryDraft}
					class="h-80 w-full rounded-lg border border-border bg-surface p-4 text-sm text-ink font-mono resize-y focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
				></textarea>
			{:else if memoryEntries.length > 0}
				<div class="space-y-2">
					{#each memoryEntries as entry}
						<div class="rounded-lg border border-border bg-surface px-4 py-3 text-sm text-ink leading-relaxed">
							{entry}
						</div>
					{/each}
				</div>
			{:else}
				<p class="text-sm text-ink-muted italic">No agent memory yet.</p>
			{/if}
		</section>

		<!-- User Profile -->
		<section>
			<div class="mb-3 flex items-center justify-between">
				<h3 class="text-sm font-medium uppercase text-ink-muted">
					User Profile
					{#if userEntries.length > 0}
						<span class="ml-1 text-ink-faint font-normal normal-case">({userEntries.length} entries)</span>
					{/if}
				</h3>
				{#if editingUser}
					<div class="flex gap-2">
						<button onclick={() => editingUser = false} class="text-xs text-ink-muted hover:text-ink">Cancel</button>
						<button onclick={saveUser} class="rounded bg-primary px-3 py-1 text-xs text-white hover:bg-primary-hover">Save</button>
					</div>
				{:else}
					<button onclick={startEditUser} class="text-xs text-primary hover:underline">Edit</button>
				{/if}
			</div>
			{#if editingUser}
				<textarea
					bind:value={userDraft}
					class="h-64 w-full rounded-lg border border-border bg-surface p-4 text-sm text-ink font-mono resize-y focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
				></textarea>
			{:else if userEntries.length > 0}
				<div class="space-y-2">
					{#each userEntries as entry}
						<div class="rounded-lg border border-border bg-surface px-4 py-3 text-sm text-ink leading-relaxed">
							{entry}
						</div>
					{/each}
				</div>
			{:else}
				<p class="text-sm text-ink-muted italic">No user profile yet.</p>
			{/if}
		</section>

	</div>
</div>
