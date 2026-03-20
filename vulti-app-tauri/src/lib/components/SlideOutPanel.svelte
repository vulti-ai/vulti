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
	import DynamicPane from './DynamicPane.svelte';
	import type { Agent, Widget } from '$lib/api';

	let { mode, onclose, onmodechange }: {
		mode: 'agent' | 'owner' | 'settings' | 'create' | 'onboard' | 'audit';
		onclose: () => void;
		onmodechange?: (newMode: string) => void;
	} = $props();

	type TabId = 'home' | 'profile' | 'connections' | 'skills' | 'actions' | 'wallet' | 'analytics';

	// Two-phase tab state:
	// - activeTab: updates immediately on click (drives tab bar highlight)
	// - renderedTab: updates after the browser paints (drives content area mount)
	// Svelte flushes activeTab + tabLoading via microtask → browser paints tab highlight
	// + spinner → setTimeout(0) fires in next macrotask → heavy content mounts.
	let activeTab = $state<TabId>('home');
	let renderedTab = $state<TabId>('home');
	let tabLoading = $state(false);
	let switchTimer: ReturnType<typeof setTimeout> | undefined;

	function switchTab(id: TabId) {
		if (id === activeTab) return;
		activeTab = id;
		tabLoading = true;
		clearTimeout(switchTimer);
		switchTimer = setTimeout(() => {
			renderedTab = id;
			tabLoading = false;
		}, 0);
	}

	let settingsTab = $state<'general' | 'connections'>('general');
	let actionsSubTab = $state<'cron' | 'rules'>('cron');
	let activeAgent = $derived(store.activeAgent);

	const tabHints: Record<string, string> = {
		home: 'Ask your agent to create a custom home view with any widget',
		profile: 'Ask about editing name, role, personality, or description',
		connections: 'Ask about connecting services or managing API access',
		skills: 'Ask about installing skills or creating custom ones',
		actions: 'Ask about scheduling cron jobs or setting up rules',
		wallet: 'Ask about payment setup or crypto vaults',
		analytics: 'Ask about usage stats, costs, or activity trends',
	};
	let chatHint = $derived(tabHints[activeTab] || '');

	// Dynamic pane widgets — only used on the Home tab
	let homeWidgets = $derived.by((): Widget[] | null => {
		const agentId = activeAgent?.id;
		if (!agentId) return null;
		const agentPanes = store.paneWidgets[agentId];
		if (!agentPanes) return null;
		const tabWidgets = agentPanes['home'];
		if (!tabWidgets || tabWidgets.length === 0) return null;
		return tabWidgets as Widget[];
	});

	// Reload pane widgets after each message (agent may have called modify_pane)
	let lastMsgCount = $state(0);
	$effect(() => {
		const count = store.messages.length;
		if (count > lastMsgCount && lastMsgCount > 0) {
			store.loadPaneWidgets();
		}
		lastMsgCount = count;
	});

	const tabs = [
		{ id: 'home' as const, label: 'Home' },
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

	let showDeleteConfirm = $state(false);
	let deleting = $state(false);

	async function deleteAgent() {
		if (!activeAgent) return;
		deleting = true;
		try {
			await store.deleteAgent(activeAgent.id);
			onclose();
		} finally {
			deleting = false;
			showDeleteConfirm = false;
		}
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
			{#if mode === 'agent' && activeAgent}
				<span class="text-[11px] font-mono text-ink-muted/50">@{activeAgent.id}-vulti</span>
			{/if}
			{#if mode === 'agent' && activeAgent?.isDefault}
				<span class="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">default</span>
			{/if}
			{#if mode === 'agent' && activeAgent}
				{#if !showDeleteConfirm}
					<button onclick={() => showDeleteConfirm = true} class="text-xs text-red-400/60 hover:text-red-400">Delete</button>
				{:else}
					<div class="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/5 px-2.5 py-1">
						<span class="text-xs text-ink-muted">Delete?</span>
						<button
							onclick={deleteAgent}
							disabled={deleting}
							class="rounded bg-red-500 px-2 py-0.5 text-xs font-medium text-white hover:bg-red-600 disabled:opacity-50"
						>{deleting ? '...' : 'Yes'}</button>
						<button onclick={() => showDeleteConfirm = false} class="text-xs text-ink-muted hover:text-ink">No</button>
					</div>
				{/if}
			{/if}
		</div>
		<div class="flex items-center gap-2">
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
		</div>
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
					onclick={() => switchTab(tab.id)}
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
					contextHint={chatHint}
					channel={renderedTab}
				/>
			</div>

			<!-- Right: tab content -->
			<div class="panel-content-main">
				{#if tabLoading}
					<div class="flex flex-1 items-center justify-center">
						<svg class="animate-spin text-ink-muted/40" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
							<path d="M21 12a9 9 0 1 1-6.219-8.56" />
						</svg>
					</div>
				{:else if renderedTab === 'home'}
					{#if homeWidgets}
						<div class="flex shrink-0 items-center justify-between border-b border-border px-6 py-2">
							<span class="text-[11px] text-ink-muted/50">Custom home view</span>
							<button
								class="text-xs font-medium text-primary hover:text-primary-hover transition-colors"
								onclick={() => store.clearPaneWidgets('home')}
							>
								Clear widgets
							</button>
						</div>
						<div class="flex-1 overflow-hidden min-h-0">
						<DynamicPane widgets={homeWidgets} tab="home" />
					</div>
					{:else}
						<div class="flex flex-1 items-center justify-center">
							<div class="text-center space-y-3 max-w-xs">
								<div class="text-3xl opacity-30">&#9670;</div>
								<p class="text-sm text-ink-muted">Ask your Agent to create a custom home view for you, with any widget</p>
							</div>
						</div>
					{/if}
				{:else if renderedTab === 'profile'}
					<ProfileView />
				{:else if renderedTab === 'connections'}
					<AgentConnectionsView />
				{:else if renderedTab === 'skills'}
					<SkillsView />
				{:else if renderedTab === 'actions'}
					<div class="flex h-full flex-col">
						<div class="flex shrink-0 items-center justify-end border-b border-border px-6 py-2">
							<div class="flex items-center gap-1 rounded-lg border border-border p-0.5">
								<button
									class="rounded-md px-3 py-1 text-xs font-medium transition-colors {actionsSubTab === 'cron' ? 'bg-primary text-white' : 'text-ink-muted hover:text-ink-dim'}"
									onclick={() => actionsSubTab = 'cron'}
								>Jobs</button>
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
				{:else if renderedTab === 'wallet'}
					<WalletView />
				{:else if renderedTab === 'analytics'}
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
		transition: color 150ms ease;
	}
	.panel-tab:hover {
		color: var(--color-ink-dim);
	}
	.panel-tab.active {
		color: var(--color-ink);
		border-bottom-color: var(--color-ink);
		transition: none;
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
		display: flex;
		flex-direction: column;
		overflow: hidden;
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
