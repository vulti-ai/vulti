<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { onMount } from 'svelte';

	let showAdd = $state(false);
	let newName = $state('');
	let newUrl = $state('http://localhost:8080');

	onMount(() => {
		store.loadAgents();
	});

	function statusColor(status: string): string {
		if (status === 'connected') return 'bg-green-500';
		if (status === 'error') return 'bg-red-500';
		return 'bg-slate-500';
	}
</script>

<div class="flex h-full flex-col">
	<header class="flex h-14 shrink-0 items-center justify-between border-b border-border px-6">
		<h2 class="font-semibold">Agents</h2>
		<button
			onclick={() => (showAdd = !showAdd)}
			class="rounded-lg bg-primary px-3 py-1.5 text-sm text-white hover:bg-primary-hover"
		>
			{showAdd ? 'Cancel' : '+ Add Agent'}
		</button>
	</header>

	<div class="flex-1 overflow-y-auto">
		{#if showAdd}
			<div class="border-b border-border p-4">
				<div class="space-y-3">
					<input
						type="text"
						bind:value={newName}
						placeholder="Agent name (e.g. Vulti)"
						class="w-full rounded-lg border border-border bg-surface px-4 py-2 text-sm text-white placeholder-slate-500 focus:border-primary focus:outline-none"
					/>
					<input
						type="url"
						bind:value={newUrl}
						placeholder="Agent URL (e.g. http://localhost:8080)"
						class="w-full rounded-lg border border-border bg-surface px-4 py-2 text-sm text-white placeholder-slate-500 focus:border-primary focus:outline-none"
					/>
					<button class="rounded-lg bg-primary px-4 py-2 text-sm text-white hover:bg-primary-hover">
						Connect Agent
					</button>
				</div>
			</div>
		{/if}

		{#if store.agents.length === 0}
			<div class="flex h-full flex-col items-center justify-center text-slate-400">
				<svg class="mb-3 h-12 w-12 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1">
					<path stroke-linecap="round" stroke-linejoin="round" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
				</svg>
				<p class="text-sm font-medium">No agents connected</p>
				<p class="text-xs text-slate-500 mt-1">Add your local Vulti agent or connect to remote agents</p>
			</div>
		{:else}
			<div class="grid gap-4 p-4 md:grid-cols-2">
				{#each store.agents as agent}
					<div class="rounded-xl border border-border bg-surface p-4">
						<div class="flex items-center gap-3 mb-3">
							<div class="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-800 text-lg font-bold text-primary">
								{agent.name.charAt(0)}
							</div>
							<div class="flex-1">
								<p class="font-medium">{agent.name}</p>
								<p class="text-xs text-slate-400">{agent.url}</p>
							</div>
							<span class="flex items-center gap-1.5">
								<span class="h-2 w-2 rounded-full {statusColor(agent.status)}"></span>
								<span class="text-xs text-slate-400">{agent.status}</span>
							</span>
						</div>
						{#if (agent.platforms ?? []).length > 0}
							<div class="flex flex-wrap gap-1.5">
								{#each agent.platforms ?? [] as platform}
									<span class="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300">{platform}</span>
								{/each}
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>
