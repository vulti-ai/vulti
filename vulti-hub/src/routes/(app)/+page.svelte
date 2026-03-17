<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import ChatView from '$lib/components/ChatView.svelte';
	import CronView from '$lib/components/CronView.svelte';
	import MemoriesView from '$lib/components/MemoriesView.svelte';
	import SoulView from '$lib/components/SoulView.svelte';
	import AnalyticsView from '$lib/components/AnalyticsView.svelte';
</script>

<svelte:head>
	<title>Vulti</title>
</svelte:head>

{#if store.currentView === 'chat'}
	<ChatView />
{:else if store.currentView === 'cron'}
	<CronView />
{:else if store.currentView === 'memories'}
	<MemoriesView />
{:else if store.currentView === 'soul'}
	<SoulView />
{:else if store.currentView === 'analytics'}
	<AnalyticsView />
{/if}
