<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { type Agent } from '$lib/api';
	import { onMount } from 'svelte';

	let { onCreated, onCancel }: {
		onCreated: (agent: Agent) => void;
		onCancel: () => void;
	} = $props();

	let name = $state('');
	let selectedModel = $state('');
	let creating = $state(false);
	let error = $state('');

	// Inline key add
	let showAddKey = $state(false);
	let newKeyName = $state('OPENROUTER_API_KEY');
	let newKeyValue = $state('');
	let addingKey = $state(false);

	const keyOptions = [
		{ value: 'OPENROUTER_API_KEY', label: 'OpenRouter' },
		{ value: 'ANTHROPIC_API_KEY', label: 'Anthropic' },
		{ value: 'OPENAI_API_KEY', label: 'OpenAI' },
		{ value: 'DEEPSEEK_API_KEY', label: 'DeepSeek' },
		{ value: 'GOOGLE_API_KEY', label: 'Google AI' },
	];

	let authenticatedProviders = $derived(store.providers.filter(p => p.authenticated));
	let hasAnyProvider = $derived(authenticatedProviders.length > 0);

	onMount(() => { store.loadProviders(); });

	$effect(() => {
		if (!selectedModel && authenticatedProviders.length > 0) {
			selectedModel = authenticatedProviders[0].models[0] || '';
		}
	});

	function modelDisplayName(model: string): string {
		const parts = model.split('/');
		return parts[parts.length - 1].split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
	}

	async function create() {
		if (!name.trim() || !selectedModel) return;
		error = '';
		creating = true;
		try {
			const agent = await store.createAgent({
				name: name.trim(),
				model: selectedModel,
			});
			onCreated(agent);
		} catch (e: any) {
			error = e.message || 'Failed to create agent';
		} finally {
			creating = false;
		}
	}

	async function handleAddKey() {
		if (!newKeyName || !newKeyValue.trim()) return;
		addingKey = true;
		try {
			await store.addSecret(newKeyName, newKeyValue.trim());
			newKeyValue = '';
			showAddKey = false;
		} catch (e: any) {
			error = e.message || 'Failed to save';
		} finally {
			addingKey = false;
		}
	}
</script>

<div class="flex h-full items-start justify-center overflow-y-auto p-8">
	<div class="w-full max-w-md">
		<h2 class="mb-6 text-xl font-bold text-ink">Create Agent</h2>

		<!-- Name -->
		<div class="mb-5">
			<label for="agent-name" class="mb-1.5 block text-sm font-medium text-ink">Name</label>
			<!-- svelte-ignore a11y_autofocus -->
			<input
				id="agent-name"
				type="text"
				bind:value={name}
				autofocus
				placeholder="e.g. Hector, WorkBot, Researcher"
				class="w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-ink placeholder:text-ink-faint focus:border-primary focus:outline-none"
				onkeydown={(e) => e.key === 'Enter' && create()}
			/>
		</div>

		<!-- Model -->
		<div class="mb-5">
			<!-- svelte-ignore a11y_label_has_associated_control -->
			<span class="mb-1.5 block text-sm font-medium text-ink">Model</span>
			{#if hasAnyProvider}
				<div class="space-y-1 rounded-lg border border-border bg-surface p-2 max-h-48 overflow-y-auto">
					{#each authenticatedProviders as provider}
						<div class="mb-1 last:mb-0">
							<p class="px-2 py-0.5 text-xs font-medium uppercase text-ink-muted">{provider.name}</p>
							{#each provider.models as model}
								<button
									onclick={() => selectedModel = model}
									class="flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-left text-sm transition-colors
										{selectedModel === model ? 'bg-primary/10 text-primary font-medium' : 'text-ink hover:bg-surface-hover'}"
								>
									<span class="flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border
										{selectedModel === model ? 'border-primary bg-primary' : 'border-ink-faint'}">
										{#if selectedModel === model}
											<span class="h-1.5 w-1.5 rounded-full bg-white"></span>
										{/if}
									</span>
									{modelDisplayName(model)}
								</button>
							{/each}
						</div>
					{/each}
				</div>
			{:else}
				<div class="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-ink-muted">
					No API keys configured. Add one to get started.
				</div>
			{/if}
			{#if !showAddKey}
				<button
					onclick={() => showAddKey = true}
					class="mt-2 text-xs text-primary hover:underline"
				>+ Add API key</button>
			{:else}
				<div class="mt-2 rounded-lg border border-border bg-surface-hover p-3">
					<div class="flex gap-2">
						<select bind:value={newKeyName} class="rounded-md border border-border bg-surface px-2 py-1.5 text-sm text-ink">
							{#each keyOptions as opt}
								<option value={opt.value}>{opt.label}</option>
							{/each}
						</select>
						<input type="password" bind:value={newKeyValue} placeholder="Paste API key"
							class="flex-1 rounded-md border border-border bg-surface px-2 py-1.5 text-sm text-ink placeholder:text-ink-faint focus:border-primary focus:outline-none" />
					</div>
					<div class="mt-2 flex gap-2">
						<button onclick={handleAddKey} disabled={addingKey || !newKeyValue.trim()}
							class="rounded-md bg-primary px-3 py-1 text-xs font-medium text-white hover:bg-primary-hover disabled:opacity-50">
							{addingKey ? 'Saving...' : 'Save'}
						</button>
						<button onclick={() => showAddKey = false} class="text-xs text-ink-muted hover:text-ink">Cancel</button>
					</div>
				</div>
			{/if}
		</div>

		{#if error}
			<p class="mb-4 text-sm text-red-400">{error}</p>
		{/if}

		<!-- Actions -->
		<div class="flex items-center justify-between">
			<button onclick={onCancel} class="text-sm text-ink-muted hover:text-ink">Cancel</button>
			<button
				onclick={create}
				disabled={!name.trim() || !selectedModel || creating}
				class="rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-white hover:bg-primary-hover disabled:opacity-50"
			>
				{creating ? 'Creating...' : 'Create'}
			</button>
		</div>
	</div>
</div>
