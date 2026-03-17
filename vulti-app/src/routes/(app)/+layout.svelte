<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { onMount } from 'svelte';
	import VultiLogo from '$lib/components/VultiLogo.svelte';

	let { children } = $props();
	let showAgentPicker = $state(false);

	const navItems = [
		{ id: 'chat' as const, label: 'Chat', svg: 'M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z' },
		{ id: 'cron' as const, label: 'Cron', svg: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z' },
		{ id: 'memories' as const, label: 'Memories', svg: 'M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z' },
		{ id: 'soul' as const, label: 'Soul', svg: 'M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z' },
		{ id: 'analytics' as const, label: 'Analytics', svg: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' }
	] as const;

	function statusColor(status: string): string {
		if (status === 'ready') return 'bg-green-500';
		if (status === 'setting_up') return 'bg-yellow-500';
		return 'bg-red-500';
	}

	onMount(() => {
		if (window.innerWidth < 768) {
			store.sidebarOpen = false;
		}
		store.loadSessions();
	});

	function navigate(view: typeof store.currentView) {
		store.currentView = view;
		if (window.innerWidth < 768) {
			store.sidebarOpen = false;
		}
	}

	function selectAgent(id: string) {
		store.gatewayActiveAgentId = id;
		showAgentPicker = false;
		// Reload data for the new agent context
		store.loadSessions();
	}
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="app-shell flex h-screen w-screen overflow-hidden">
	<!-- Sidebar -->
	<aside
		class="sidebar flex shrink-0 flex-col overflow-hidden border-r border-border sidebar-glass"
		class:open={store.sidebarOpen}
	>
		<div class="flex w-56 shrink-0 flex-col" style="min-height: 100%;">
			<!-- Logo -->
			<div class="flex h-14 shrink-0 items-center border-b border-border px-3 overflow-hidden">
				<VultiLogo mode="wordmark" size={16} />
			</div>

			<!-- Agent Picker -->
			<div class="relative shrink-0 border-b border-border p-2">
				<button
					onclick={() => (showAgentPicker = !showAgentPicker)}
					title={store.activeGatewayAgent?.name || 'Select agent'}
					class="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left transition-colors hover:bg-surface-hover"
				>
					{#if store.activeGatewayAgent}
						<span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-surface text-sm">
							{store.activeGatewayAgent.avatar || store.activeGatewayAgent.name.charAt(0)}
						</span>
						<span class="sidebar-label flex-1 truncate text-sm font-medium">{store.activeGatewayAgent.name}</span>
						<span class="sidebar-label h-2 w-2 shrink-0 rounded-full {statusColor(store.activeGatewayAgent.status)}"></span>
					{:else}
						<span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-surface text-xs text-slate-500">?</span>
						<span class="sidebar-label flex-1 text-sm text-slate-500">No agent</span>
					{/if}
					<svg class="sidebar-label h-3 w-3 shrink-0 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
					</svg>
				</button>

				{#if showAgentPicker}
					<div class="fixed inset-0 z-40" onclick={() => (showAgentPicker = false)} onkeydown={() => {}}></div>
					<div class="absolute left-2 right-2 top-full z-50 mt-1 rounded-lg border border-border bg-slate-900 py-1 shadow-xl">
						{#each store.gatewayAgents as agent}
							<button
								onclick={() => selectAgent(agent.id)}
								class="flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors"
								class:bg-surface-active={store.gatewayActiveAgentId === agent.id}
								class:hover:bg-surface-hover={store.gatewayActiveAgentId !== agent.id}
							>
								<span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface text-xs">
									{agent.avatar || agent.name.charAt(0)}
								</span>
								<span class="flex-1 truncate">{agent.name}</span>
								<span class="h-2 w-2 shrink-0 rounded-full {statusColor(agent.status)}"></span>
							</button>
						{/each}
						{#if store.gatewayAgents.length === 0}
							<p class="px-3 py-2 text-xs text-slate-500">No agents configured</p>
							<p class="px-3 pb-2 text-xs text-slate-600">Set up agents in the Gateway app</p>
						{/if}
					</div>
				{/if}
			</div>

			<!-- Navigation -->
			<nav class="flex-1 overflow-y-auto p-2">
				{#each navItems as item}
					<button
						onclick={() => navigate(item.id)}
						title={item.label}
						class="mb-1 flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition-colors"
						class:bg-primary={store.currentView === item.id}
						class:text-white={store.currentView === item.id}
						class:text-slate-400={store.currentView !== item.id}
						class:hover:bg-surface-hover={store.currentView !== item.id}
						class:hover:text-white={store.currentView !== item.id}
					>
						<svg class="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
							<path stroke-linecap="round" stroke-linejoin="round" d={item.svg} />
						</svg>
						<span class="sidebar-label flex-1 text-left">{item.label}</span>
					</button>
				{/each}
			</nav>

			<!-- Collapse -->
			<button
				onclick={() => (store.sidebarOpen = !store.sidebarOpen)}
				class="flex h-10 shrink-0 items-center gap-3 border-t border-border px-3 text-slate-500 hover:text-white"
			>
				<svg class="h-5 w-5 shrink-0 transition-transform duration-200" class:rotate-180={!store.sidebarOpen} fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
				</svg>
				<span class="sidebar-label text-xs">Collapse</span>
			</button>
		</div>
	</aside>

	<main class="flex flex-1 flex-col overflow-hidden">
		{@render children()}
	</main>
</div>

{#if store.notifications.length > 0}
	<div class="fixed right-4 top-4 z-50 flex flex-col gap-2">
		{#each store.notifications.slice(0, 3) as notif, i}
			<div class="flex max-w-sm items-start gap-3 rounded-lg border border-border bg-surface p-3 shadow-lg">
				<span class="text-xs font-medium uppercase text-primary">{notif.source}</span>
				<p class="flex-1 text-sm text-slate-200">{notif.summary}</p>
				<button onclick={() => store.dismissNotification(i)} class="text-slate-400 hover:text-white">x</button>
			</div>
		{/each}
	</div>
{/if}

<style>
	.app-shell {
		position: relative;
		z-index: 1;
	}

	.sidebar-glass {
		backdrop-filter: blur(24px) saturate(1.6);
		-webkit-backdrop-filter: blur(24px) saturate(1.6);
	}

	:global(html.light) .sidebar-glass {
		background: rgba(237, 231, 219, 0.78);
	}

	:global(html.dark) .sidebar-glass {
		background: rgba(30, 28, 26, 0.88);
	}

	.sidebar {
		width: 3.5rem;
		transition: width 200ms ease;
	}
	.sidebar.open {
		width: 16rem;
	}
	.sidebar-label {
		white-space: nowrap;
		opacity: 0;
		transition: opacity 150ms ease;
		pointer-events: none;
	}
	.sidebar.open .sidebar-label {
		opacity: 1;
		pointer-events: auto;
	}
</style>
