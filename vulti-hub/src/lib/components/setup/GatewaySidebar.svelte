<script lang="ts">
	import { store } from '$lib/stores/app.svelte';

	let { onSelectSettings, onNewAgent, settingsActive = false }: {
		onSelectSettings: () => void;
		onNewAgent: () => void;
		settingsActive?: boolean;
	} = $props();

	function statusColor(status: string): string {
		if (status === 'ready') return 'bg-green-500';
		if (status === 'setting_up') return 'bg-yellow-500';
		return 'bg-red-500';
	}

	function selectAgent(id: string) {
		store.gatewayActiveAgentId = id;
	}

	function forkActive() {
		if (store.gatewayActiveAgentId) {
			store.forkAgent(store.gatewayActiveAgentId);
		}
	}
</script>

<div class="flex h-full w-64 shrink-0 flex-col border-r border-border bg-paper-warm">
	<!-- Header -->
	<div class="flex h-14 shrink-0 items-center gap-2 border-b border-border px-4">
		<div class="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-sm font-bold text-white">H</div>
		<span class="text-lg font-semibold text-ink">Vulti</span>
	</div>

	<!-- Settings -->
	<div class="px-3 pt-3">
		<button
			onclick={onSelectSettings}
			class="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors
				{settingsActive ? 'bg-surface text-ink' : 'text-ink-dim hover:bg-surface-hover'}"
		>
			<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
				<path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.573-1.066z" />
				<path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
			</svg>
			<span>Settings</span>
			{#if !store.gatewayGlobal.tailscale.connected}
				<span class="ml-auto h-2 w-2 rounded-full bg-yellow-500"></span>
			{/if}
		</button>
	</div>

	<!-- Divider -->
	<div class="mx-4 my-2 border-t border-border"></div>

	<!-- Agents label -->
	<div class="flex items-center justify-between px-4 py-1">
		<span class="text-xs font-medium uppercase text-ink-muted">Agents</span>
		<span class="text-xs text-ink-faint">{store.gatewayAgents.length}</span>
	</div>

	<!-- Agent list -->
	<nav class="flex-1 overflow-y-auto px-3 pb-3">
		{#each store.gatewayAgents as agent}
			<button
				onclick={() => selectAgent(agent.id)}
				class="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition-colors
					{agent.id === store.gatewayActiveAgentId && !settingsActive ? 'bg-surface text-ink' : 'text-ink-dim hover:bg-surface-hover'}"
			>
				<span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm">
					{agent.avatar || agent.name.charAt(0)}
				</span>
				<span class="flex-1 truncate font-medium">{agent.name}</span>
				<span class="h-2 w-2 shrink-0 rounded-full {statusColor(agent.status)}"></span>
			</button>
		{/each}

		{#if store.gatewayAgents.length === 0}
			<p class="px-3 py-4 text-center text-xs text-ink-muted">No agents yet</p>
		{/if}
	</nav>

	<!-- Bottom actions -->
	<div class="border-t border-border p-3 space-y-1">
		<button
			onclick={onNewAgent}
			class="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-primary hover:bg-surface-hover"
		>
			<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
			</svg>
			New Agent
		</button>
		{#if store.gatewayActiveAgentId && !settingsActive}
			<button
				onclick={forkActive}
				class="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-ink-dim hover:bg-surface-hover"
			>
				<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M15.75 17.25v3.375c0 .621-.504 1.125-1.125 1.125h-9.75a1.125 1.125 0 01-1.125-1.125V7.875c0-.621.504-1.125 1.125-1.125H6.75a9.06 9.06 0 011.5.124m7.5 10.376h3.375c.621 0 1.125-.504 1.125-1.125V11.25c0-4.46-3.243-8.161-7.5-8.876a9.06 9.06 0 00-1.5-.124H9.375c-.621 0-1.125.504-1.125 1.125v3.5m7.5 10.375H9.375a1.125 1.125 0 01-1.125-1.125v-9.25m12 6.625v-1.875a3.375 3.375 0 00-3.375-3.375h-1.5a1.125 1.125 0 01-1.125-1.125v-1.5a3.375 3.375 0 00-3.375-3.375H9.75" />
				</svg>
				Fork Agent
			</button>
		{/if}
	</div>
</div>
