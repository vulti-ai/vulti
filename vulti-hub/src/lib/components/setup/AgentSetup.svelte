<script lang="ts">
	import { store, type GatewayAgent } from '$lib/stores/app.svelte';
	import IdentityTab from './tabs/IdentityTab.svelte';
	import AIModelsTab from './tabs/AIModelsTab.svelte';
	import CommunicationTab from './tabs/CommunicationTab.svelte';
	import FilesTab from './tabs/FilesTab.svelte';
	import CalendarContactsTab from './tabs/CalendarContactsTab.svelte';
	import KnowledgeTab from './tabs/KnowledgeTab.svelte';
	import CodeTab from './tabs/CodeTab.svelte';
	import OtherTab from './tabs/OtherTab.svelte';

	let { agent }: { agent: GatewayAgent } = $props();

	const tabs = [
		{ id: 'identity', label: 'Identity' },
		{ id: 'ai_models', label: 'AI Models' },
		{ id: 'communication', label: 'Communication' },
		{ id: 'files', label: 'Files' },
		{ id: 'calendar_contacts', label: 'Calendar & Contacts' },
		{ id: 'knowledge', label: 'Knowledge' },
		{ id: 'code', label: 'Code' },
		{ id: 'other', label: 'Other' },
	] as const;

	let activeTab = $state<string>('identity');

	function serviceCount(category: string): number {
		return agent.services.filter(s => s.category === category && s.status === 'connected').length;
	}

	function saveAgent() {
		store.updateAgent(agent.id, { status: 'ready' });
	}

	function deleteAgent() {
		store.deleteAgent(agent.id);
	}
</script>

<div class="flex h-full flex-col">
	<!-- Agent header -->
	<div class="flex items-center justify-between border-b border-border px-6 py-4">
		<div class="flex items-center gap-3">
			<span class="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-lg">
				{agent.avatar || agent.name.charAt(0)}
			</span>
			<div>
				<h2 class="text-lg font-bold text-ink">{agent.name}</h2>
				<p class="text-xs text-ink-muted">
					{agent.status === 'ready' ? 'Ready' : 'Setting up'} · {agent.services.filter(s => s.status === 'connected').length} services connected
				</p>
			</div>
		</div>
		<div class="flex items-center gap-2">
			<button
				onclick={deleteAgent}
				class="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-xs text-red-400 hover:bg-red-500/20"
			>
				Delete
			</button>
			<button
				onclick={saveAgent}
				class="rounded-lg bg-primary px-4 py-1.5 text-sm font-medium text-white hover:bg-primary-hover"
			>
				Save
			</button>
		</div>
	</div>

	<!-- Tabs -->
	<div class="flex gap-1 overflow-x-auto border-b border-border px-6">
		{#each tabs as tab}
			<button
				onclick={() => activeTab = tab.id}
				class="shrink-0 border-b-2 px-3 py-3 text-sm transition-colors
					{activeTab === tab.id ? 'border-primary text-ink font-medium' : 'border-transparent text-ink-dim hover:text-ink'}"
			>
				{tab.label}
				{#if tab.id !== 'identity'}
					{@const count = serviceCount(tab.id)}
					{#if count > 0}
						<span class="ml-1 rounded-full bg-green-500/10 px-1.5 py-0.5 text-xs text-green-400">{count}</span>
					{/if}
				{/if}
			</button>
		{/each}
	</div>

	<!-- Tab content -->
	<div class="flex-1 overflow-y-auto p-6">
		<div class="mx-auto max-w-2xl">
			{#if activeTab === 'identity'}
				<IdentityTab {agent} />
			{:else if activeTab === 'ai_models'}
				<AIModelsTab {agent} />
			{:else if activeTab === 'communication'}
				<CommunicationTab {agent} />
			{:else if activeTab === 'files'}
				<FilesTab {agent} />
			{:else if activeTab === 'calendar_contacts'}
				<CalendarContactsTab {agent} />
			{:else if activeTab === 'knowledge'}
				<KnowledgeTab {agent} />
			{:else if activeTab === 'code'}
				<CodeTab {agent} />
			{:else if activeTab === 'other'}
				<OtherTab {agent} />
			{/if}
		</div>
	</div>
</div>
