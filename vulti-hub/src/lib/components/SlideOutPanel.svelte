<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import ProfileView from './ProfileView.svelte';
	import CronView from './CronView.svelte';
	import RulesView from './RulesView.svelte';
	import AnalyticsView from './AnalyticsView.svelte';
	import ChatView from './ChatView.svelte';
	import OwnerPanel from './OwnerPanel.svelte';
	import GlobalSettingsView from './setup/GlobalSettingsView.svelte';
	import ConnectionsView from './ConnectionsView.svelte';
	import AgentConnectionsView from './AgentConnectionsView.svelte';
	import CreateAgentView from './setup/CreateAgentView.svelte';
	import OnboardingWizard from './OnboardingWizard.svelte';
	import AuditView from './AuditView.svelte';
	import SkillsView from './SkillsView.svelte';
	import WalletView from './WalletView.svelte';
	import type { Agent } from '$lib/api';

	let { mode, onclose, onmodechange }: {
		mode: 'agent' | 'owner' | 'settings' | 'create' | 'onboard' | 'audit';
		onclose: () => void;
		onmodechange?: (newMode: string) => void;
	} = $props();

	let activeTab = $state<'profile' | 'connections' | 'skills' | 'actions' | 'wallet' | 'analytics'>('profile');
	let settingsTab = $state<'general' | 'connections'>('general');
	let actionsSubTab = $state<'cron' | 'rules'>('cron');
	let activeAgent = $derived(store.activeAgent);

	const tabs = [
		{ id: 'profile' as const, label: 'Profile' },
		{ id: 'connections' as const, label: 'Connections' },
		{ id: 'skills' as const, label: 'Skills' },
		{ id: 'actions' as const, label: 'Actions' },
		{ id: 'wallet' as const, label: 'Wallet' },
		{ id: 'analytics' as const, label: 'Analytics' },
	];

	function handleAgentCreated(_agent: Agent) {
		onmodechange?.('onboard');
	}

	// Title
	let title = $derived.by(() => {
		if (mode === 'owner') return 'Profile';
		if (mode === 'settings') return 'Settings';
		if (mode === 'create') return 'New Agent';
		if (mode === 'onboard') return 'Setup';
		if (mode === 'audit') return 'Audit Log';
		if (activeAgent) return activeAgent.name;
		return '';
	});
</script>

<div class="panel-root">
	<!-- Header bar -->
	<header class="panel-header">
		<div class="flex items-center gap-3">
			{#if mode === 'agent' && activeAgent && store.avatarCache[activeAgent.id]}
				<img class="h-8 w-8 rounded-lg object-cover" src={store.avatarCache[activeAgent.id]} alt={activeAgent.name} />
			{/if}
			<h1 class="text-base font-semibold text-ink">{title}</h1>
			{#if mode === 'agent' && activeAgent?.role}
				<span class="rounded-full bg-ink/5 px-2.5 py-0.5 text-xs text-ink-dim">{activeAgent.role}</span>
			{/if}
		</div>
		<button class="close-btn" onclick={onclose} title="Back to canvas">
			{#if store.isBusy}
				<svg class="animate-spin" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
					<path d="M21 12a9 9 0 1 1-6.219-8.56" />
				</svg>
			{:else}
				<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
					<path d="M18 6 6 18M6 6l12 12" />
				</svg>
			{/if}
		</button>
	</header>

	{#if mode === 'owner'}
		<div class="panel-body">
			<div class="panel-content-narrow">
				<OwnerPanel />
			</div>
		</div>

	{:else if mode === 'settings'}
		<!-- Settings tabs -->
		<nav class="panel-tabs">
			<button
				class="panel-tab"
				class:active={settingsTab === 'general'}
				onclick={() => settingsTab = 'general'}
			>General</button>
			<button
				class="panel-tab"
				class:active={settingsTab === 'connections'}
				onclick={() => settingsTab = 'connections'}
			>Connections</button>
		</nav>
		<div class="panel-body">
			<div class="panel-content-narrow">
				{#if settingsTab === 'general'}
					<GlobalSettingsView />
				{:else}
					<ConnectionsView />
				{/if}
			</div>
		</div>

	{:else if mode === 'create'}
		<div class="panel-body">
			<div class="panel-content-narrow">
				<CreateAgentView
					onCreated={handleAgentCreated}
					onCancel={onclose}
				/>
			</div>
		</div>

	{:else if mode === 'onboard'}
		<div class="flex-1 overflow-hidden">
			<OnboardingWizard onclose={onclose} />
		</div>

	{:else if mode === 'audit'}
		<div class="panel-body">
			<div class="panel-content-narrow">
				<AuditView />
			</div>
		</div>

	{:else if mode === 'agent' && activeAgent}
		<!-- Tab bar -->
		<nav class="panel-tabs">
			{#each tabs as tab}
				<button
					class="panel-tab"
					class:active={activeTab === tab.id}
					onclick={() => activeTab = tab.id}
				>
					{tab.label}
				</button>
			{/each}
		</nav>

		<!-- Two-column layout: chat + content -->
		<div class="panel-body-split">
			<!-- Left: chat -->
			<div class="panel-chat">
				<ChatView
					contextLabel={activeTab}
					channel={activeTab}
				/>
			</div>

			<!-- Right: tab content (agent-modifiable) -->
			<div class="panel-content-main">
				{#if activeTab === 'profile'}
					<ProfileView ondelete={onclose} />
				{:else if activeTab === 'connections'}
					<AgentConnectionsView />
				{:else if activeTab === 'skills'}
					<SkillsView />
				{:else if activeTab === 'actions'}
					<div class="flex h-full flex-col">
						<div class="flex shrink-0 items-center justify-between border-b border-border px-6 py-2">
							<div class="flex items-center gap-1 rounded-lg border border-border p-0.5">
								<button
									class="rounded-md px-3 py-1 text-xs font-medium transition-colors {actionsSubTab === 'cron' ? 'bg-primary text-white' : 'text-ink-muted hover:text-ink-dim'}"
									onclick={() => actionsSubTab = 'cron'}
								>Cron Jobs</button>
								<button
									class="rounded-md px-3 py-1 text-xs font-medium transition-colors {actionsSubTab === 'rules' ? 'bg-primary text-white' : 'text-ink-muted hover:text-ink-dim'}"
									onclick={() => actionsSubTab = 'rules'}
								>Rules</button>
							</div>
						</div>
						<div class="flex-1 overflow-y-auto">
							{#if actionsSubTab === 'cron'}
								<CronView />
							{:else}
								<RulesView />
							{/if}
						</div>
					</div>
				{:else if activeTab === 'wallet'}
					<WalletView />
				{:else if activeTab === 'analytics'}
					<AnalyticsView />
				{/if}
			</div>
		</div>
	{/if}
</div>

<style>
	.panel-root {
		display: flex;
		flex-direction: column;
		height: 100%;
		width: 100%;
	}

	.panel-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		height: 3.5rem;
		padding: 0 1.5rem;
		flex-shrink: 0;
		border-bottom: 1px solid var(--color-border);
	}

	:global(html.light) .panel-root {
		background: rgba(245, 240, 232, 0.92);
		backdrop-filter: blur(40px) saturate(1.5);
		-webkit-backdrop-filter: blur(40px) saturate(1.5);
	}
	:global(html.dark) .panel-root {
		background: rgba(30, 28, 26, 0.92);
		backdrop-filter: blur(40px) saturate(1.5);
		-webkit-backdrop-filter: blur(40px) saturate(1.5);
	}

	.close-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 32px;
		height: 32px;
		border-radius: 8px;
		color: var(--color-ink-muted);
		transition: all 150ms ease;
	}
	.close-btn:hover {
		background: var(--color-surface-hover);
		color: var(--color-ink);
	}

	.panel-tabs {
		display: flex;
		padding: 0 1.5rem;
		gap: 0;
		border-bottom: 1px solid var(--color-border);
		flex-shrink: 0;
	}

	.panel-tab {
		padding: 0.625rem 1rem;
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--color-ink-muted);
		border-bottom: 2px solid transparent;
		transition: all 150ms ease;
	}
	.panel-tab:hover {
		color: var(--color-ink-dim);
	}
	.panel-tab.active {
		color: var(--color-ink);
		border-bottom-color: var(--color-ink);
	}

	.panel-body {
		flex: 1;
		overflow-y: auto;
		padding: 1.5rem;
	}

	.panel-content-narrow {
		max-width: 36rem;
		margin: 0 auto;
	}

	.panel-body-split {
		flex: 1;
		display: flex;
		overflow: hidden;
	}

	.panel-content-main {
		flex: 1;
		overflow-y: auto;
		min-width: 0;
	}

	.panel-chat {
		width: 26rem;
		flex-shrink: 0;
		border-right: 1px solid var(--color-border);
	}

	/* Responsive: stack on smaller screens */
	@media (max-width: 768px) {
		.panel-body-split {
			flex-direction: column;
		}
		.panel-chat {
			width: 100%;
			height: 16rem;
			border-right: none;
			border-bottom: 1px solid var(--color-border);
		}
	}
</style>
