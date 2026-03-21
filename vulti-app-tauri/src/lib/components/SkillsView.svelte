<script lang="ts">
	import { api, type Skill } from '$lib/api';
	import { store } from '$lib/stores/app.svelte';
	import { onMount } from 'svelte';

	let agentSkills = $state<Skill[]>([]);
	let availableSkills = $state<Skill[]>([]);
	let loading = $state(false);
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
	<!-- Header -->
	<div class="flex shrink-0 items-center justify-between border-b border-border px-6 py-2">
		<p class="text-xs text-ink-muted">Manage skills for this agent.</p>
		<div class="flex items-center gap-3">
			{#if agentSkills.length > 0}
				<span class="rounded-full bg-green-500/15 px-2 py-0.5 text-[10px] font-medium text-green-600">{agentSkills.length} installed</span>
			{/if}
			<span class="text-[10px] text-ink-faint">{availableSkills.length} available</span>
		</div>
	</div>

	{#if loading}
		<div class="flex-1 flex items-center justify-center">
			<p class="text-xs text-ink-muted">Loading...</p>
		</div>
	{:else}
		<!-- Two-column layout -->
		<div class="flex flex-1 overflow-hidden">
			<!-- Left: Installed -->
			<div class="col installed-col">
				<div class="col-header">
					<span class="col-title">Installed</span>
					<span class="col-count">{agentSkills.length}</span>
				</div>
				<div class="col-body">
					{#if agentSkills.length === 0}
						<div class="empty-state">
							<p class="text-xs text-ink-muted">No skills installed</p>
							<p class="text-[10px] text-ink-faint mt-1">Add from available skills &rarr;</p>
						</div>
					{:else}
						{#each agentSkills as skill (skill.name)}
							<div class="skill-row installed">
								<div class="min-w-0 flex-1">
									<div class="flex items-center gap-2">
										<span class="text-sm font-medium text-ink">{skill.name}</span>
										{#if skill.category}
											<span class="cat-badge">{skill.category}</span>
										{/if}
									</div>
									{#if skill.description}
										<p class="mt-0.5 text-xs text-ink-muted truncate">{skill.description}</p>
									{/if}
								</div>
								<button
									class="action-btn remove"
									onclick={() => remove(skill.name)}
									title="Remove skill"
								>
									<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
										<path d="M5 12h14" />
									</svg>
								</button>
							</div>
						{/each}
					{/if}
				</div>
			</div>

			<!-- Divider -->
			<div class="col-divider"></div>

			<!-- Right: Available -->
			<div class="col available-col">
				<div class="col-header">
					<span class="col-title">Available</span>
					<span class="col-count">{installable().length}</span>
				</div>
				<!-- Search/filter -->
				<div class="filter-bar">
					<input
						type="text"
						placeholder="Search..."
						class="filter-input"
						bind:value={searchQuery}
					/>
					<select class="filter-select" bind:value={selectedCategory}>
						<option value="">All</option>
						{#each categories() as cat}
							<option value={cat}>{cat}</option>
						{/each}
					</select>
				</div>
				<div class="col-body">
					{#each installable() as skill (skill.name)}
						<div class="skill-row available">
							<button
								class="action-btn add"
								onclick={() => install(skill.name)}
								title="Install skill"
							>
								<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
									<path d="M12 5v14M5 12h14" />
								</svg>
							</button>
							<div class="min-w-0 flex-1">
								<div class="flex items-center gap-2">
									<span class="text-sm font-medium text-ink-dim">{skill.name}</span>
									{#if skill.category}
										<span class="cat-badge">{skill.category}</span>
									{/if}
								</div>
								{#if skill.description}
									<p class="mt-0.5 text-xs text-ink-faint truncate">{skill.description}</p>
								{/if}
							</div>
						</div>
					{:else}
						<div class="empty-state">
							<p class="text-xs text-ink-muted">
								{searchQuery || selectedCategory ? 'No matching skills.' : 'All skills installed.'}
							</p>
						</div>
					{/each}
				</div>
			</div>
		</div>
	{/if}
</div>

<style>
	.col {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-width: 0;
		overflow: hidden;
	}

	.col-divider {
		width: 1px;
		flex-shrink: 0;
		background: var(--color-border);
	}

	.col-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.5rem 0.75rem;
		border-bottom: 1px solid var(--color-border);
		flex-shrink: 0;
	}

	.col-title {
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--color-ink-muted);
	}

	.col-count {
		font-size: 0.625rem;
		font-weight: 500;
		color: var(--color-ink-faint);
		background: var(--color-ink-faint, rgba(0,0,0,0.05));
		background: rgba(128, 128, 128, 0.1);
		padding: 0.125rem 0.375rem;
		border-radius: 9999px;
	}

	.filter-bar {
		display: flex;
		gap: 0.375rem;
		padding: 0.375rem 0.75rem;
		border-bottom: 1px solid var(--color-border);
		flex-shrink: 0;
	}

	.filter-input {
		flex: 1;
		padding: 0.25rem 0.5rem;
		border-radius: 0.375rem;
		border: 1px solid var(--color-border);
		background: transparent;
		font-size: 0.6875rem;
		color: var(--color-ink);
		outline: none;
	}
	.filter-input:focus {
		border-color: var(--color-primary);
	}

	.filter-select {
		appearance: none;
		padding: 0.25rem 0.5rem;
		border-radius: 0.375rem;
		border: 1px solid var(--color-border);
		background: transparent;
		font-size: 0.6875rem;
		color: var(--color-ink-dim);
		outline: none;
		max-width: 7rem;
	}

	.col-body {
		flex: 1;
		overflow-y: auto;
		padding: 0.375rem;
	}

	.skill-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 0.5rem;
		border-radius: 0.375rem;
		transition: background 100ms ease;
	}
	.skill-row:hover {
		background: var(--color-surface-hover);
	}

	.skill-row.installed {
		border-bottom: 1px solid rgba(128, 128, 128, 0.06);
	}

	.cat-badge {
		font-size: 0.5625rem;
		padding: 0.0625rem 0.375rem;
		border-radius: 9999px;
		background: rgba(128, 128, 128, 0.08);
		color: var(--color-ink-faint);
		white-space: nowrap;
	}

	.action-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 1.5rem;
		height: 1.5rem;
		border-radius: 0.375rem;
		flex-shrink: 0;
		transition: all 100ms ease;
	}

	.action-btn.add {
		color: #22c55e;
		border: 1px solid #22c55e40;
		background: #22c55e08;
	}
	.action-btn.add:hover {
		background: #22c55e20;
		border-color: #22c55e80;
	}

	.action-btn.remove {
		color: var(--color-ink-faint);
		border: 1px solid transparent;
	}
	.action-btn.remove:hover {
		color: #ef4444;
		border-color: #ef444440;
		background: #ef444410;
	}

	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 2rem 1rem;
		text-align: center;
	}
</style>
