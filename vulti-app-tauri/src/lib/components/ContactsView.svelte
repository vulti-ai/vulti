<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { onMount } from 'svelte';

	let search = $state('');

	onMount(() => {
		store.loadContacts();
	});

	let filtered = $derived(
		store.contacts.filter(c =>
			c.name.toLowerCase().includes(search.toLowerCase()) ||
			c.tags.some(t => t.toLowerCase().includes(search.toLowerCase()))
		)
	);
</script>

<div class="flex h-full flex-col">
	<header class="flex h-14 shrink-0 items-center justify-between border-b border-border px-6">
		<h2 class="font-semibold">Contacts</h2>
		<span class="text-sm text-slate-400">{store.contacts.length} contacts</span>
	</header>

	<!-- Search -->
	<div class="border-b border-border p-4">
		<input
			type="text"
			bind:value={search}
			placeholder="Search contacts..."
			class="w-full rounded-lg border border-border bg-surface px-4 py-2 text-sm text-white placeholder-slate-500 focus:border-primary focus:outline-none"
		/>
	</div>

	<div class="flex-1 overflow-y-auto">
		{#if filtered.length === 0}
			<div class="flex h-full flex-col items-center justify-center text-slate-400">
				<svg class="mb-3 h-12 w-12 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1">
					<path stroke-linecap="round" stroke-linejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
				</svg>
				<p class="text-sm font-medium">No contacts yet</p>
				<p class="text-xs text-slate-500 mt-1">Contacts are built automatically from your interactions</p>
			</div>
		{:else}
			<div class="divide-y divide-border">
				{#each filtered as contact}
					<div class="flex items-center gap-4 p-4 hover:bg-surface-hover transition-colors">
						<div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-surface text-sm font-bold text-primary">
							{contact.name.charAt(0).toUpperCase()}
						</div>
						<div class="flex-1 min-w-0">
							<p class="font-medium text-sm">{contact.name}</p>
							<div class="flex gap-2 mt-0.5">
								{#each contact.platforms as p}
									<span class="text-xs text-slate-400">{p.platform}: {p.handle}</span>
								{/each}
							</div>
						</div>
						<div class="text-right">
							{#if contact.last_interaction}
								<p class="text-xs text-slate-500">{new Date(contact.last_interaction).toLocaleDateString()}</p>
							{/if}
							<div class="flex gap-1 mt-1 justify-end">
								{#each contact.tags as tag}
									<span class="rounded bg-surface px-1.5 py-0.5 text-[10px] text-slate-400">{tag}</span>
								{/each}
							</div>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>
