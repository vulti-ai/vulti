<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import GatewaySidebar from './setup/GatewaySidebar.svelte';
	import AgentSetup from './setup/AgentSetup.svelte';
	import GlobalSettingsView from './setup/GlobalSettingsView.svelte';
	import TailscaleStep from './setup/TailscaleStep.svelte';

	let showSettings = $state(!store.gatewayGlobal.tailscale.connected);
	let showNewAgentPrompt = $state(false);
	let newAgentName = $state('');
	let fillFromAgentId = $state<string | null>(null);

	let activeAgent = $derived(store.activeGatewayAgent);
	let tailscaleConnected = $derived(store.gatewayGlobal.tailscale.connected);
	let hasAgents = $derived(store.gatewayAgents.length > 0);
	let needsFirstAgent = $derived(tailscaleConnected && !hasAgents && !showSettings);

	function selectSettings() {
		showSettings = true;
		showNewAgentPrompt = false;
	}

	function startNewAgent() {
		showSettings = false;
		showNewAgentPrompt = true;
		newAgentName = '';
		fillFromAgentId = null;
	}

	function createAgent() {
		if (!newAgentName.trim()) return;

		if (fillFromAgentId) {
			const forked = store.forkAgent(fillFromAgentId);
			if (forked) {
				store.updateAgent(forked.id, { name: newAgentName.trim() });
			}
		} else {
			store.createAgent(newAgentName.trim());
		}
		showNewAgentPrompt = false;
		showSettings = false;
	}

	function handleTailscaleComplete() {
		store.updateGlobalSettings({
			tailscale: { ...store.gatewayGlobal.tailscale, connected: true }
		});
		showSettings = false;
	}

	function handleAgentSelected() {
		showSettings = false;
		showNewAgentPrompt = false;
	}

	// When an agent is selected from sidebar, switch to agent view
	$effect(() => {
		if (store.gatewayActiveAgentId && !showNewAgentPrompt) {
			showSettings = false;
		}
	});
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
		{#if !tailscaleConnected}
			<!-- First-time: Tailscale gate -->
			<div class="flex flex-1 items-center justify-center overflow-y-auto">
				<div class="w-full max-w-2xl p-8">
					<TailscaleStep status="pending" onComplete={handleTailscaleComplete} />
				</div>
			</div>
		{:else if showSettings}
			<!-- Global settings -->
			<GlobalSettingsView />
		{:else if showNewAgentPrompt || needsFirstAgent}
			<!-- New agent creation -->
			<div class="flex flex-1 items-center justify-center">
				<div class="w-full max-w-md p-8">
					<div class="mb-6 text-center">
						<div class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
							<svg class="h-8 w-8 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
								<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
							</svg>
						</div>
						<h2 class="text-2xl font-bold text-ink">
							{hasAgents ? 'Create New Agent' : 'Create Your First Agent'}
						</h2>
						<p class="mt-2 text-sm text-ink-dim">
							Give your agent a name to get started. You can configure everything else after.
						</p>
					</div>

					<div class="space-y-4">
						<div>
							<label for="new-agent-name" class="mb-1.5 block text-sm font-medium text-ink">Agent Name</label>
							<input
								id="new-agent-name"
								type="text"
								bind:value={newAgentName}
								placeholder="e.g. James, WorkBot, Personal"
								autofocus
								class="w-full rounded-lg border border-border bg-surface px-4 py-3 text-sm text-ink placeholder-ink-faint focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
								onkeydown={(e) => e.key === 'Enter' && createAgent()}
							/>
						</div>

						{#if hasAgents}
							<div>
								<label for="fill-from" class="mb-1.5 block text-sm font-medium text-ink">Fill from existing agent</label>
								<select
									id="fill-from"
									bind:value={fillFromAgentId}
									class="w-full rounded-lg border border-border bg-surface px-4 py-3 text-sm text-ink focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
								>
									<option value={null}>Start fresh</option>
									{#each store.gatewayAgents as agent}
										<option value={agent.id}>{agent.name} ({agent.services.length} services)</option>
									{/each}
								</select>
								<p class="mt-1 text-xs text-ink-muted">Copy all connections from an existing agent</p>
							</div>
						{/if}

						<button
							onclick={createAgent}
							disabled={!newAgentName.trim()}
							class="w-full rounded-lg bg-primary py-3 text-sm font-medium text-white hover:bg-primary-hover disabled:opacity-50"
						>
							Create Agent
						</button>

						{#if hasAgents}
							<button
								onclick={() => { showNewAgentPrompt = false; }}
								class="w-full rounded-lg border border-border py-3 text-sm text-ink-dim hover:bg-surface-hover"
							>
								Cancel
							</button>
						{/if}
					</div>
				</div>
			</div>
		{:else if activeAgent}
			<!-- Agent config -->
			<AgentSetup agent={activeAgent} />
		{:else}
			<!-- Fallback -->
			<div class="flex flex-1 items-center justify-center">
				<p class="text-ink-muted">Select an agent or create a new one</p>
			</div>
		{/if}
	</div>
</div>
