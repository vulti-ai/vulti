<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { type Agent } from '$lib/api';

	let { onCreated, onCancel }: {
		onCreated: (agent: Agent) => void;
		onCancel: () => void;
	} = $props();

	let name = $state('');
	let avatar = $state('');
	let personality = $state('');
	let cloneFrom = $state('');
	let creating = $state(false);
	let error = $state('');

	const avatarOptions = ['🤖', '🧠', '💼', '🏠', '🎨', '📊', '🔧', '🌟', '🎯', '🦊', '🐻', '🦉'];

	async function handleCreate() {
		if (!name.trim()) {
			error = 'Name is required';
			return;
		}
		error = '';
		creating = true;
		try {
			const agent = await store.createAgent({
				name: name.trim(),
				avatar: avatar || undefined,
				personality: personality.trim() || undefined,
				description: personality.trim().slice(0, 100) || undefined,
				inherit_from: cloneFrom || undefined,
			});
			onCreated(agent);
		} catch (e: any) {
			error = e.message || 'Failed to create agent';
		} finally {
			creating = false;
		}
	}
</script>

<div class="flex h-full items-start justify-center overflow-y-auto p-8">
	<div class="w-full max-w-lg">
		<h2 class="mb-6 text-2xl font-bold text-ink">Create New Agent</h2>

		<!-- Name -->
		<div class="mb-5">
			<label for="agent-name" class="mb-1.5 block text-sm font-medium text-ink">Name</label>
			<input
				id="agent-name"
				type="text"
				bind:value={name}
				placeholder="e.g. James, Research Bot, Work Assistant"
				class="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-primary focus:outline-none"
			/>
		</div>

		<!-- Avatar -->
		<div class="mb-5">
			<label class="mb-1.5 block text-sm font-medium text-ink">Avatar</label>
			<div class="flex flex-wrap gap-2">
				{#each avatarOptions as emoji}
					<button
						onclick={() => avatar = avatar === emoji ? '' : emoji}
						class="flex h-10 w-10 items-center justify-center rounded-lg border text-lg transition-colors
							{avatar === emoji ? 'border-primary bg-primary/10' : 'border-border bg-surface hover:bg-surface-hover'}"
					>
						{emoji}
					</button>
				{/each}
			</div>
			{#if !avatar && name}
				<p class="mt-1 text-xs text-ink-muted">Default: {name.charAt(0).toUpperCase()}</p>
			{/if}
		</div>

		<!-- Personality -->
		<div class="mb-5">
			<label for="agent-personality" class="mb-1.5 block text-sm font-medium text-ink">Personality <span class="text-ink-muted">(optional)</span></label>
			<textarea
				id="agent-personality"
				bind:value={personality}
				rows="4"
				placeholder="Describe this agent's personality, role, and how it should behave. This becomes the agent's SOUL.md."
				class="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-primary focus:outline-none"
			></textarea>
		</div>

		<!-- Clone from -->
		{#if store.agents.length > 0}
			<div class="mb-6">
				<label for="clone-from" class="mb-1.5 block text-sm font-medium text-ink">Clone config from <span class="text-ink-muted">(optional)</span></label>
				<select
					id="clone-from"
					bind:value={cloneFrom}
					class="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none"
				>
					<option value="">Start fresh</option>
					{#each store.agents as agent}
						<option value={agent.id}>{agent.name} — copies config and soul</option>
					{/each}
				</select>
			</div>
		{/if}

		<!-- Error -->
		{#if error}
			<p class="mb-4 text-sm text-red-400">{error}</p>
		{/if}

		<!-- Actions -->
		<div class="flex items-center justify-end gap-3">
			<button
				onclick={onCancel}
				class="rounded-lg px-4 py-2 text-sm text-ink-muted hover:text-ink"
			>
				Cancel
			</button>
			<button
				onclick={handleCreate}
				disabled={creating || !name.trim()}
				class="rounded-lg bg-primary px-5 py-2 text-sm font-medium text-white hover:bg-primary-hover disabled:opacity-50"
			>
				{creating ? 'Creating...' : 'Create Agent'}
			</button>
		</div>
	</div>
</div>
