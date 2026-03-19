<script lang="ts">
	import { api, type Skill } from '$lib/api';
	import { store } from '$lib/stores/app.svelte';
	import { onMount } from 'svelte';

	let agentSkills = $state<Skill[]>([]);
	let availableSkills = $state<Skill[]>([]);
	let loading = $state(false);
	let showBrowser = $state(false);
	let searchQuery = $state('');
	let selectedCategory = $state('');

	let agentId = $derived(store.activeAgentId);

	async function load() {
		if (!agentId) return;
		loading = true;
		try {
			const [agent, available] = await Promise.all([
				api.listAgentSkills(agentId),
				api.listAvailableSkills(),
			]);
			agentSkills = agent;
			availableSkills = available;
		} catch {
			agentSkills = [];
			availableSkills = [];
		}
		loading = false;
	}

	onMount(load);

	$effect(() => {
		const _id = agentId;
		const _v = store.skillsVersion;
		load();
	});

	// Skills not yet installed for this agent
	let installable = $derived(() => {
		const installed = new Set(agentSkills.map(s => s.name));
		let filtered = availableSkills.filter(s => !installed.has(s.name));
		if (searchQuery) {
			const q = searchQuery.toLowerCase();
			filtered = filtered.filter(s =>
				s.name.toLowerCase().includes(q) ||
				s.description.toLowerCase().includes(q) ||
				s.category.toLowerCase().includes(q)
			);
		}
		if (selectedCategory) {
			filtered = filtered.filter(s => s.category === selectedCategory);
		}
		return filtered;
	});

	let categories = $derived(() => {
		const cats = new Set(availableSkills.map(s => s.category).filter(Boolean));
		return [...cats].sort();
	});

	async function install(skillName: string) {
		if (!agentId) return;
		try {
			const skill = await api.installAgentSkill(agentId, skillName);
			agentSkills = [...agentSkills, skill];
		} catch (e) {
			console.error('Failed to install skill:', e);
		}
	}

	async function remove(skillName: string) {
		if (!agentId) return;
		try {
			await api.removeAgentSkill(agentId, skillName);
			agentSkills = agentSkills.filter(s => s.name !== skillName);
		} catch (e) {
			console.error('Failed to remove skill:', e);
		}
	}
</script>

<div class="flex h-full flex-col">
	<div class="flex shrink-0 items-center justify-end border-b border-border px-6 py-2">
		<button
			class="rounded-lg bg-primary animate-rainbow px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-hover"
			onclick={() => showBrowser = !showBrowser}
		>
			{showBrowser ? 'Done' : '+ Add Skills'}
		</button>
	</div>

	<div class="flex-1 overflow-y-auto">
		{#if showBrowser}
			<!-- Skill browser -->
			<div class="border-b border-border px-6 py-2">
				<div class="flex gap-2">
					<input
						type="text"
						placeholder="Search skills..."
						class="skill-input flex-1"
						bind:value={searchQuery}
					/>
					<select class="skill-select" bind:value={selectedCategory}>
						<option value="">All categories</option>
						{#each categories() as cat}
							<option value={cat}>{cat}</option>
						{/each}
					</select>
				</div>
			</div>
			<div class="px-6 py-2">
				{#each installable() as skill}
					<div class="skill-row">
						<div class="flex-1 min-w-0">
							<div class="flex items-center gap-2">
								<span class="text-sm font-medium text-ink">{skill.name}</span>
								{#if skill.category}
									<span class="text-[10px] rounded bg-ink/5 px-1.5 py-0.5 text-ink-muted">{skill.category}</span>
								{/if}
							</div>
							{#if skill.description}
								<p class="mt-0.5 text-xs text-ink-muted truncate">{skill.description}</p>
							{/if}
						</div>
						<button
							class="shrink-0 rounded-md bg-primary animate-rainbow px-3 py-1 text-xs font-semibold text-white transition-all hover:shadow-sm"
							onclick={() => install(skill.name)}
						>Install</button>
					</div>
				{:else}
					<p class="py-6 text-center text-xs text-ink-muted">
						{searchQuery || selectedCategory ? 'No matching skills found.' : 'All skills installed.'}
					</p>
				{/each}
			</div>

		{:else}
			<!-- Installed skills list -->
			{#if loading}
				<div class="py-12 text-center text-xs text-ink-muted">Loading...</div>
			{:else if agentSkills.length === 0}
				<div class="flex flex-col items-center justify-center py-16 px-6">
					<div class="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-ink/5">
						<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="text-ink-muted">
							<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
							<path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
						</svg>
					</div>
					<p class="text-sm font-medium text-ink-dim">No skills installed</p>
					<p class="mt-1 text-xs text-ink-muted">Add skills to give this agent specialized abilities</p>
				</div>
			{:else}
				<div class="px-6 py-2">
					{#each agentSkills as skill}
						<div class="skill-row">
							<div class="flex-1 min-w-0">
								<div class="flex items-center gap-2">
									<span class="text-sm font-medium text-ink">{skill.name}</span>
									{#if skill.category}
										<span class="text-[10px] rounded bg-ink/5 px-1.5 py-0.5 text-ink-muted">{skill.category}</span>
									{/if}
								</div>
								{#if skill.description}
									<p class="mt-0.5 text-xs text-ink-muted truncate">{skill.description}</p>
								{/if}
							</div>
							<button
								class="shrink-0 rounded-md px-2 py-1 text-xs text-ink-muted hover:bg-red-50 hover:text-red-600 transition-colors"
								onclick={() => remove(skill.name)}
								title="Remove skill"
							>
								<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
									<path d="M18 6 6 18M6 6l12 12" />
								</svg>
							</button>
						</div>
					{/each}
				</div>
			{/if}
		{/if}
	</div>
</div>

<style>
	.skill-row {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 8px 0;
		border-bottom: 1px solid rgba(0, 0, 0, 0.04);
	}
	.skill-row:last-child {
		border-bottom: none;
	}
	:global(.dark) .skill-row {
		border-bottom-color: rgba(255, 255, 255, 0.04);
	}

	.skill-input {
		padding: 5px 10px;
		border-radius: 6px;
		border: 1px solid rgba(0, 0, 0, 0.08);
		background: rgba(0, 0, 0, 0.02);
		font-size: 12px;
		color: var(--ink, #333);
		outline: none;
	}
	.skill-input:focus {
		border-color: rgba(0, 0, 0, 0.2);
	}
	:global(.dark) .skill-input {
		border-color: rgba(255, 255, 255, 0.1);
		background: rgba(255, 255, 255, 0.04);
		color: rgba(255, 255, 255, 0.8);
	}

	.skill-select {
		appearance: none;
		padding: 5px 10px;
		border-radius: 6px;
		border: 1px solid rgba(0, 0, 0, 0.08);
		background: rgba(0, 0, 0, 0.02);
		font-size: 12px;
		color: var(--ink-dim, #555);
		outline: none;
	}
	:global(.dark) .skill-select {
		border-color: rgba(255, 255, 255, 0.1);
		background: rgba(255, 255, 255, 0.04);
		color: rgba(255, 255, 255, 0.7);
	}
</style>
