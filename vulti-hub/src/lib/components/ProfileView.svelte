<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import type { AgentRole } from '$lib/api';
	import { marked } from 'marked';

	const roles: { value: AgentRole; label: string }[] = [
		{ value: 'assistant', label: 'Assistant' },
		{ value: 'therapist', label: 'Therapist' },
		{ value: 'researcher', label: 'Researcher' },
		{ value: 'engineer', label: 'Engineer' },
		{ value: 'writer', label: 'Writer' },
		{ value: 'analyst', label: 'Analyst' },
		{ value: 'coach', label: 'Coach' },
		{ value: 'creative', label: 'Creative' },
		{ value: 'ops', label: 'Ops' },
	];

	let editingRole = $state(false);

	async function setRole(role: AgentRole) {
		if (!store.activeAgent) return;
		await store.updateAgent(store.activeAgent.id, { role });
		editingRole = false;
	}

	// Cache parsed markdown so marked() doesn't re-run on every render
	let soulHtml = $derived(store.soul ? marked(store.soul) : '');

	let editingName = $state(false);
	let nameDraft = $state('');

	function startEditName() {
		nameDraft = store.activeAgent?.name || '';
		editingName = true;
	}
	async function saveName() {
		if (!nameDraft.trim() || !store.activeAgent) return;
		await store.updateAgent(store.activeAgent.id, { name: nameDraft.trim() });
		editingName = false;
	}

	let { ondelete }: { ondelete?: () => void } = $props();

	let showDeleteConfirm = $state(false);
	let deleting = $state(false);

	async function deleteAgent() {
		if (!store.activeAgent) return;
		deleting = true;
		try {
			await store.deleteAgent(store.activeAgent.id);
			ondelete?.();
		} finally {
			deleting = false;
			showDeleteConfirm = false;
		}
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
</script>

<div class="h-full overflow-y-auto">
	<div class="mx-auto max-w-4xl space-y-8 p-6">

		<!-- Agent Identity -->
		{#if store.activeAgent}
			<section class="flex items-center gap-4">
				{#if store.activeAgentId && store.avatarCache[store.activeAgentId]}
					<img class="h-16 w-16 rounded-2xl object-cover" src={store.avatarCache[store.activeAgentId]} alt={store.activeAgent.name} />
				{:else}
					<div class="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 text-2xl font-bold text-primary">
						{store.activeAgent.name.charAt(0)}
					</div>
				{/if}
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
						<div>
							<button onclick={startEditName} class="group flex items-center gap-2" title="Edit name">
								<h2 class="text-2xl font-bold text-ink">{store.activeAgent.name}</h2>
								<svg class="h-4 w-4 text-ink-faint opacity-0 group-hover:opacity-100 transition-opacity" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
									<path stroke-linecap="round" stroke-linejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L6.832 19.82a4.5 4.5 0 01-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 011.13-1.897L16.863 4.487z" />
								</svg>
							</button>
							{#if editingRole}
								<div class="mt-1 flex flex-wrap gap-1.5">
									{#each roles as role}
										<button
											onclick={() => setRole(role.value)}
											class="rounded-md border px-2.5 py-1 text-xs transition-colors
												{store.activeAgent.role === role.value
													? 'border-primary bg-primary/10 text-primary font-medium'
													: 'border-border text-ink-muted hover:border-ink-faint hover:text-ink'}"
										>
											{role.label}
										</button>
									{/each}
									<button onclick={() => editingRole = false} class="px-2 py-1 text-xs text-ink-faint hover:text-ink">Cancel</button>
								</div>
							{:else}
								<button onclick={() => editingRole = true} class="mt-0.5 text-sm text-ink-muted capitalize hover:text-primary transition-colors" title="Change role">
									{store.activeAgent.role || 'Set role'}
								</button>
							{/if}
						</div>
					{/if}
				</div>
				<!-- Delete -->
				{#if !showDeleteConfirm}
					<button onclick={() => showDeleteConfirm = true} class="ml-auto self-start text-xs text-red-400 hover:text-red-300">
						Delete
					</button>
				{:else}
					<div class="ml-auto flex items-center gap-2 self-start rounded-lg border border-red-500/30 bg-red-500/5 px-3 py-1.5">
						<span class="text-xs text-ink-muted">Delete from all platforms?</span>
						<button
							onclick={deleteAgent}
							disabled={deleting}
							class="rounded-md bg-red-500 px-2.5 py-1 text-xs font-medium text-white hover:bg-red-600 disabled:opacity-50"
						>
							{deleting ? 'Deleting...' : 'Yes'}
						</button>
						<button onclick={() => showDeleteConfirm = false} class="text-xs text-ink-muted hover:text-ink">No</button>
					</div>
				{/if}
			</section>
		{/if}

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
