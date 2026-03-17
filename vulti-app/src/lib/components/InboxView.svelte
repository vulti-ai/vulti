<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { onMount } from 'svelte';

	onMount(() => {
		store.loadInbox();
	});

	function platformColor(source: string): string {
		const colors: Record<string, string> = {
			email: 'bg-blue-500',
			whatsapp: 'bg-green-500',
			telegram: 'bg-sky-500',
			discord: 'bg-indigo-500',
			slack: 'bg-purple-500',
			signal: 'bg-blue-600'
		};
		return colors[source.toLowerCase()] || 'bg-slate-500';
	}

	function timeAgo(ts: string): string {
		const diff = Date.now() - new Date(ts).getTime();
		const mins = Math.floor(diff / 60000);
		if (mins < 60) return `${mins}m ago`;
		const hrs = Math.floor(mins / 60);
		if (hrs < 24) return `${hrs}h ago`;
		return `${Math.floor(hrs / 24)}d ago`;
	}
</script>

<div class="flex h-full flex-col">
	<header class="flex h-14 shrink-0 items-center justify-between border-b border-border px-6">
		<h2 class="font-semibold">Inbox</h2>
		<button
			onclick={() => store.loadInbox()}
			class="rounded-lg bg-surface px-3 py-1.5 text-sm text-slate-300 hover:bg-surface-hover"
		>
			Refresh
		</button>
	</header>

	<div class="flex-1 overflow-y-auto">
		{#if store.inbox.length === 0}
			<div class="flex h-full flex-col items-center justify-center text-slate-400">
				<svg class="mb-3 h-12 w-12 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1">
					<path stroke-linecap="round" stroke-linejoin="round" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
				</svg>
				<p class="text-sm font-medium">No messages yet</p>
				<p class="text-xs text-slate-500 mt-1">Messages from connected platforms will appear here</p>
			</div>
		{:else}
			<div class="divide-y divide-border">
				{#each store.inbox as item}
					<div class="flex items-start gap-4 p-4 hover:bg-surface-hover transition-colors" class:opacity-60={item.read}>
						<div class="flex flex-col items-center gap-1">
							<span class="inline-block h-2 w-2 rounded-full {platformColor(item.source)}"></span>
							<span class="text-[10px] uppercase text-slate-500">{item.source}</span>
						</div>
						<div class="flex-1 min-w-0">
							<div class="flex items-center gap-2 mb-1">
								<span class="font-medium text-sm">{item.sender}</span>
								<span class="text-xs text-slate-500">{timeAgo(item.timestamp)}</span>
								{#if !item.read}
									<span class="h-1.5 w-1.5 rounded-full bg-primary"></span>
								{/if}
							</div>
							<p class="text-sm text-slate-300 truncate">{item.preview}</p>
							{#if item.actions.length > 0}
								<div class="flex gap-2 mt-2">
									{#each item.actions as action}
										<button class="rounded bg-surface px-2.5 py-1 text-xs text-primary hover:bg-surface-active">
											{action}
										</button>
									{/each}
								</div>
							{/if}
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>
