<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { type Agent } from '$lib/api';
	import GatewaySidebar from './setup/GatewaySidebar.svelte';
	import GlobalSettingsView from './setup/GlobalSettingsView.svelte';
	import GatewayStep from './setup/GatewayStep.svelte';
	import TailscaleStep from './setup/TailscaleStep.svelte';
	import CreateAgentView from './setup/CreateAgentView.svelte';
	import AgentSetup from './setup/AgentSetup.svelte';
	import ConfigView from './ConfigView.svelte';
	import ProfileView from './ProfileView.svelte';
	import CronView from './CronView.svelte';
	import RulesView from './RulesView.svelte';
	import AnalyticsView from './AnalyticsView.svelte';

	let actionsSubTab = $state<'cron' | 'rules'>('cron');
	let gatewayConnected = $derived(store.gatewayGlobal.gateway?.connected ?? false);
	let tailscaleConnected = $derived(store.gatewayGlobal.tailscale.connected);

	let showSettings = $state(false);
	let creatingAgent = $state(false);
	let activeAgent = $derived(store.activeAgent);

	// Load agents from gateway when connected
	$effect(() => {
		if (gatewayConnected) {
			store.loadAgents();
		}
	});

	// Preload all data in parallel when an agent is selected
	$effect(() => {
		if (activeAgent) {
			Promise.all([
				store.loadSessions(),
				store.loadStatus(),
				store.loadIntegrations(),
				store.loadMemories(),
				store.loadSoul(),
				store.loadCron(),
				store.loadRules(),
				store.loadAnalytics(),
				store.loadSecrets(),
				store.loadOAuth(),
				store.loadChannels(),
			]);
		}
	});

	function selectSettings() {
		showSettings = true;
		creatingAgent = false;
		store.activeAgentId = null;
	}

	function startNewAgent() {
		creatingAgent = true;
		showSettings = false;
	}

	function handleAgentCreated(agent: Agent) {
		creatingAgent = false;
		// Agent is auto-selected by store.createAgent, show setup
		store.currentView = 'config';
	}

	function handleCreateCancel() {
		creatingAgent = false;
		// Go back to the previously selected agent or settings
		if (!store.activeAgentId && store.agents.length > 0) {
			store.activeAgentId = store.agents[0].id;
		}
	}

	function handleGatewayComplete() {
		store.updateGlobalSettings({ gateway: { connected: true } });
	}

	function handleTailscaleComplete() {
		store.updateGlobalSettings({
			tailscale: { ...store.gatewayGlobal.tailscale, connected: true }
		});
		showSettings = false;
	}

	// When an agent is selected from sidebar, switch away from settings/creating
	$effect(() => {
		if (store.activeAgentId) {
			showSettings = false;
			creatingAgent = false;
		}
	});

	// Show AgentSetup for new agents (setting_up status), ConfigView for established agents
	let showAgentSetup = $derived(
		activeAgent && (activeAgent.status === 'setting_up' || store.currentView === 'config')
	);

	const navItems = [
		{ id: 'profile' as const, label: 'Profile', svg: 'M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z' },
		{ id: 'actions' as const, label: 'Actions', svg: 'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15' },
		{ id: 'analytics' as const, label: 'Analytics', svg: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
		{ id: 'config' as const, label: 'Config', svg: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.573-1.066z' },
	] as const;
</script>

<div class="flex h-full">
	<!-- Sidebar -->
	<GatewaySidebar
		settingsActive={showSettings}
		onSelectSettings={selectSettings}
		onNewAgent={startNewAgent}
	/>

	<!-- Main content -->
	<div class="flex flex-1 flex-col overflow-hidden">
		{#if !gatewayConnected}
			<div class="flex flex-1 items-center justify-center overflow-y-auto">
				<div class="w-full max-w-2xl p-8">
					<GatewayStep status="pending" onComplete={handleGatewayComplete} />
				</div>
			</div>
		{:else if !tailscaleConnected}
			<div class="flex flex-1 items-center justify-center overflow-y-auto">
				<div class="w-full max-w-2xl p-8">
					<TailscaleStep status="pending" onComplete={handleTailscaleComplete} />
				</div>
			</div>
		{:else if creatingAgent}
			<CreateAgentView onCreated={handleAgentCreated} onCancel={handleCreateCancel} />
		{:else if showSettings}
			<div class="flex-1 overflow-y-auto">
				<GlobalSettingsView />
			</div>
		{:else if activeAgent}
			<!-- Agent dashboard -->
			<div class="flex h-full flex-col">
				<!-- Nav bar -->
				<div class="flex shrink-0 items-center gap-1 border-b border-border px-4 py-2">
					{#each navItems as item}
						<button
							onclick={() => store.currentView = item.id}
							class="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors
								{store.currentView === item.id ? 'bg-primary text-white' : 'text-ink-muted hover:bg-surface-hover hover:text-ink'}"
						>
							<svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
								<path stroke-linecap="round" stroke-linejoin="round" d={item.svg} />
							</svg>
							{item.label}
						</button>
					{/each}
				</div>

				<!-- View content -->
				<div class="flex-1 overflow-hidden">
					{#if store.currentView === 'config'}
						{#if activeAgent.status === 'setting_up'}
							<AgentSetup agent={activeAgent} />
						{:else}
							<ConfigView />
						{/if}
					{:else if store.currentView === 'profile'}
						<ProfileView />
					{:else if store.currentView === 'actions'}
						<div class="flex h-full flex-col">
							<div class="flex shrink-0 gap-1 border-b border-border px-4 py-1.5">
								<button
									onclick={() => actionsSubTab = 'cron'}
									class="rounded px-3 py-1 text-xs font-medium transition-colors
										{actionsSubTab === 'cron' ? 'bg-surface-active text-white' : 'text-ink-muted hover:text-ink'}"
								>
									Scheduled Jobs
								</button>
								<button
									onclick={() => actionsSubTab = 'rules'}
									class="rounded px-3 py-1 text-xs font-medium transition-colors
										{actionsSubTab === 'rules' ? 'bg-surface-active text-white' : 'text-ink-muted hover:text-ink'}"
								>
									Rules
								</button>
							</div>
							<div class="flex-1 overflow-hidden">
								{#if actionsSubTab === 'cron'}
									<CronView />
								{:else}
									<RulesView />
								{/if}
							</div>
						</div>
					{:else if store.currentView === 'analytics'}
						<AnalyticsView />
					{/if}
				</div>
			</div>
		{:else}
			<div class="flex flex-1 items-center justify-center">
				<p class="text-ink-muted">Select an agent or create a new one</p>
			</div>
		{/if}
	</div>
</div>
