<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { onMount } from 'svelte';

	let { children } = $props();

	onMount(() => {
		store.loadAgents();
		store.loadRelationships();
		store.loadOwner();
	});
</script>

<div class="relative h-screen w-screen overflow-hidden" style="z-index: 1;">
	<main class="h-full w-full">
		{@render children()}
	</main>
</div>

{#if store.notifications.length > 0}
	<div class="fixed right-4 top-4 z-50 flex flex-col gap-2">
		{#each store.notifications.slice(0, 3) as notif, i}
			<div class="flex max-w-sm items-start gap-3 rounded-lg border border-border bg-surface p-3 shadow-lg backdrop-blur-xl">
				<span class="text-xs font-medium uppercase text-primary">{notif.source}</span>
				<p class="flex-1 text-sm text-ink/80">{notif.summary}</p>
				<button onclick={() => store.dismissNotification(i)} class="text-ink/40 hover:text-ink">x</button>
			</div>
		{/each}
	</div>
{/if}
