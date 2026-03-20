<script lang="ts">
	import { store, type GatewayAgent } from '$lib/stores/app.svelte';

	let { agent }: { agent: GatewayAgent } = $props();

	// svelte-ignore state_referenced_locally
	let name = $state(agent.name);
	// svelte-ignore state_referenced_locally
	let avatar = $state(agent.avatar || '');
	// svelte-ignore state_referenced_locally
	let personality = $state(agent.personality || '');

	const emojiOptions = ['🤖', '🧠', '💼', '🏠', '🎨', '📊', '🔧', '🌟', '🎯', '🦊', '🐻', '🦉'];

	function save() {
		store.updateAgent(agent.id, { name, avatar, personality });
	}
</script>

<div class="space-y-6">
	<div>
		<h3 class="text-lg font-semibold text-ink">Agent Identity</h3>
		<p class="text-sm text-ink-dim">Give your agent a name and personality.</p>
	</div>

	<!-- Avatar -->
	<div>
		<span class="mb-2 block text-sm font-medium text-ink">Avatar</span>
		<div class="flex flex-wrap gap-2">
			{#each emojiOptions as emoji}
				<button
					onclick={() => { avatar = emoji; save(); }}
					class="flex h-10 w-10 items-center justify-center rounded-lg border text-lg transition-colors
						{avatar === emoji ? 'border-primary bg-primary/10' : 'border-border hover:bg-surface-hover'}"
				>
					{emoji}
				</button>
			{/each}
		</div>
	</div>

	<!-- Name -->
	<div>
		<label for="agent-name" class="mb-1.5 block text-sm font-medium text-ink">Name</label>
		<input
			id="agent-name"
			type="text"
			bind:value={name}
			onblur={save}
			placeholder="e.g. James, WorkBot, Personal Assistant"
			class="w-full rounded-lg border border-border bg-surface px-4 py-3 text-sm text-ink placeholder-ink-faint focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
		/>
	</div>

	<!-- Personality -->
	<div>
		<label for="personality" class="mb-1.5 block text-sm font-medium text-ink">Personality & Role</label>
		<textarea
			id="personality"
			bind:value={personality}
			onblur={save}
			placeholder="Describe this agent's role, tone, and specialties. e.g. 'A professional work assistant focused on email management and scheduling. Formal tone, concise responses.'"
			rows="4"
			class="w-full rounded-lg border border-border bg-surface px-4 py-3 text-sm text-ink placeholder-ink-faint focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
		></textarea>
	</div>
</div>
