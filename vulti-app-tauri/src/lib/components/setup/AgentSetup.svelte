<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import type { Agent } from '$lib/api';
	import ServiceConnector from './ServiceConnector.svelte';
	import ReadTab from './tabs/ReadTab.svelte';
	import WriteTab from './tabs/WriteTab.svelte';

	let { agent }: { agent: Agent } = $props();

	// svelte-ignore state_referenced_locally
	let name = $state(agent.name);
	// svelte-ignore state_referenced_locally
	let avatar = $state(agent.avatar || '');
	// svelte-ignore state_referenced_locally
	let personality = $state(agent.personality || '');

	let activeTab = $state<'read' | 'write'>('read');

	const emojiOptions = ['🤖', '🧠', '💼', '🏠', '🎨', '📊', '🔧', '🌟', '🎯', '🦊', '🐻', '🦉'];

	function saveProfile() {
		store.updateAgent(agent.id, { name, avatar, personality });
	}

	let rc = $derived((agent.services ?? []).filter(s => s.permission !== 'write' && s.status === 'connected').length);
	let wc = $derived((agent.services ?? []).filter(s => s.permission === 'write' && s.status === 'connected').length);

	function getModelService(type: string) {
		return (agent.services ?? []).find(s => s.type === type);
	}

	function connectModel(type: string, label: string) {
		store.addServiceToAgent(agent.id, {
			id: crypto.randomUUID(), category: 'ai_models', type, label,
			status: 'connected', config: {}
		});
	}

	function disconnectModel(type: string) {
		const svc = getModelService(type);
		if (svc) store.removeServiceFromAgent(agent.id, svc.id);
	}

</script>

<div class="flex h-full flex-col">
	<!-- Profile section -->
	<div class="border-b border-border px-6 py-5">
		<div class="mx-auto max-w-2xl space-y-5">
			<!-- Avatar + Name row -->
			<div class="flex items-start gap-4">
				<div class="flex flex-wrap gap-1.5">
					{#each emojiOptions as emoji}
						<button
							onclick={() => { avatar = emoji; saveProfile(); }}
							class="flex h-8 w-8 items-center justify-center rounded-lg border text-sm transition-colors
								{avatar === emoji ? 'border-primary bg-primary/10' : 'border-border hover:bg-surface-hover'}"
						>
							{emoji}
						</button>
					{/each}
				</div>
				<div class="flex-1">
					<input
						type="text"
						bind:value={name}
						onblur={saveProfile}
						placeholder="Agent name"
						class="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink placeholder-ink-faint focus:border-primary focus:outline-none"
					/>
				</div>
			</div>

			<!-- Personality -->
			<textarea
				bind:value={personality}
				onblur={saveProfile}
				placeholder="Describe this agent's role and personality..."
				rows="2"
				class="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink placeholder-ink-faint focus:border-primary focus:outline-none"
			></textarea>

			<!-- AI Models (compact) -->
			<div class="space-y-2">
				<h4 class="text-xs font-medium uppercase text-ink-muted">Model</h4>
				<div class="flex flex-wrap gap-2">
					<ServiceConnector type="openrouter" label="OpenRouter" category="ai_models" description="200+ models"
						status={getModelService('openrouter') ? 'connected' : 'disconnected'}
						onConnect={() => connectModel('openrouter', 'OpenRouter')}
						onDisconnect={() => disconnectModel('openrouter')} />
					<ServiceConnector type="anthropic" label="Anthropic" category="ai_models" description="Claude"
						status={getModelService('anthropic') ? 'connected' : 'disconnected'}
						onConnect={() => connectModel('anthropic', 'Anthropic')}
						onDisconnect={() => disconnectModel('anthropic')} />
					<ServiceConnector type="openai" label="OpenAI" category="ai_models" description="GPT"
						status={getModelService('openai') ? 'connected' : 'disconnected'}
						onConnect={() => connectModel('openai', 'OpenAI')}
						onDisconnect={() => disconnectModel('openai')} />
				</div>
			</div>

		</div>
	</div>

	<!-- Read / Write tabs -->
	<div class="flex gap-1 border-b border-border px-6">
		<button
			onclick={() => activeTab = 'read'}
			class="border-b-2 px-4 py-3 text-sm transition-colors
				{activeTab === 'read' ? 'border-primary text-ink font-medium' : 'border-transparent text-ink-dim hover:text-ink'}"
		>
			Read
			{#if rc > 0}
				<span class="ml-1 rounded-full bg-green-500/10 px-1.5 py-0.5 text-xs text-green-400">{rc}</span>
			{/if}
		</button>
		<button
			onclick={() => activeTab = 'write'}
			class="border-b-2 px-4 py-3 text-sm transition-colors
				{activeTab === 'write' ? 'border-primary text-ink font-medium' : 'border-transparent text-ink-dim hover:text-ink'}"
		>
			Write
			{#if wc > 0}
				<span class="ml-1 rounded-full bg-amber-500/10 px-1.5 py-0.5 text-xs text-amber-400">{wc}</span>
			{/if}
		</button>
	</div>

	<!-- Tab content -->
	<div class="flex-1 overflow-y-auto p-6">
		<div class="mx-auto max-w-2xl">
			{#if activeTab === 'read'}
				<ReadTab {agent} />
			{:else}
				<WriteTab {agent} />
			{/if}
		</div>
	</div>
</div>
