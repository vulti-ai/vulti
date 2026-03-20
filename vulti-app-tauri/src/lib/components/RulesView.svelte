<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { onMount } from 'svelte';

	onMount(() => { store.loadRules(); });

	let showCreate = $state(false);
	let newName = $state('');
	let newCondition = $state('');
	let newAction = $state('');
	let newPriority = $state(0);
	let newCooldown = $state('');

	async function createRule() {
		if (!newCondition.trim() || !newAction.trim()) return;
		store.createRule({
			name: newName || undefined,
			condition: newCondition,
			action: newAction,
			priority: newPriority,
			cooldown_minutes: newCooldown ? parseInt(newCooldown) : undefined,
		});
		newName = '';
		newCondition = '';
		newAction = '';
		newPriority = 0;
		newCooldown = '';
		showCreate = false;
	}

	function toggleRule(id: string, enabled: boolean) {
		store.updateRule(id, { enabled: !enabled });
	}

	function deleteRule(id: string) {
		store.deleteRule(id);
	}
</script>

<div>
		<div class="flex justify-end px-6 py-2">
			<button
				onclick={() => (showCreate = !showCreate)}
				class="rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-hover"
			>
				{showCreate ? 'Cancel' : '+ New Rule'}
			</button>
		</div>
		<!-- Create form -->
		{#if showCreate}
			<div class="border-b border-border p-4">
				<div class="space-y-3">
					<input
						type="text"
						bind:value={newName}
						placeholder="Rule name (optional)"
						class="w-full rounded-lg border border-border bg-surface px-4 py-2 text-sm text-white placeholder-slate-500 focus:border-primary focus:outline-none"
					/>
					<textarea
						bind:value={newCondition}
						placeholder="IF... (e.g. 'message looks like a receipt')"
						rows="2"
						class="w-full resize-none rounded-lg border border-border bg-surface px-4 py-2 text-sm text-white placeholder-slate-500 focus:border-primary focus:outline-none"
					></textarea>
					<textarea
						bind:value={newAction}
						placeholder="THEN... (e.g. 'save to Google Drive and log the amount')"
						rows="2"
						class="w-full resize-none rounded-lg border border-border bg-surface px-4 py-2 text-sm text-white placeholder-slate-500 focus:border-primary focus:outline-none"
					></textarea>
					<div class="flex gap-3">
						<input
							type="number"
							bind:value={newPriority}
							placeholder="Priority (0)"
							class="w-32 rounded-lg border border-border bg-surface px-4 py-2 text-sm text-white placeholder-slate-500 focus:border-primary focus:outline-none"
						/>
						<input
							type="text"
							bind:value={newCooldown}
							placeholder="Cooldown (minutes)"
							class="w-40 rounded-lg border border-border bg-surface px-4 py-2 text-sm text-white placeholder-slate-500 focus:border-primary focus:outline-none"
						/>
					</div>
					<button
						onclick={createRule}
						class="rounded-lg bg-primary px-4 py-2 text-sm text-white hover:bg-primary-hover"
					>
						Create Rule
					</button>
				</div>
			</div>
		{/if}

		<!-- Rules list -->
		{#if store.rules.length === 0}
			<div class="flex h-full flex-col items-center justify-center text-slate-400">
				<svg class="mb-3 h-12 w-12 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1">
					<path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
				</svg>
				<p class="text-sm font-medium">No rules configured</p>
				<p class="text-xs text-slate-500 mt-1">Create rules to automate actions when conditions match</p>
			</div>
		{:else}
			<div class="divide-y divide-border">
				{#each store.rules as rule}
					<div class="p-4 hover:bg-surface-hover transition-colors">
						<div class="flex items-center justify-between mb-2">
							<div class="flex items-center gap-2">
								<span
									class="h-2 w-2 rounded-full"
									class:bg-green-500={rule.enabled}
									class:bg-yellow-500={!rule.enabled}
								></span>
								<span class="font-medium text-sm">{rule.name}</span>
								<span class="text-xs text-slate-500">p={rule.priority}</span>
							</div>
							<div class="flex items-center gap-2">
								<button
									onclick={() => toggleRule(rule.id, rule.enabled)}
									class="rounded bg-surface px-2.5 py-1 text-xs hover:bg-surface-active"
									class:text-yellow-400={rule.enabled}
									class:text-green-400={!rule.enabled}
								>
									{rule.enabled ? 'Disable' : 'Enable'}
								</button>
								<button
									onclick={() => deleteRule(rule.id)}
									class="rounded bg-surface px-2.5 py-1 text-xs text-red-400 hover:bg-surface-active"
								>
									Delete
								</button>
							</div>
						</div>
						<div class="space-y-1 text-sm">
							<p class="text-slate-400"><span class="text-slate-500 font-medium">IF</span> {rule.condition}</p>
							<p class="text-slate-300"><span class="text-slate-500 font-medium">THEN</span> {rule.action}</p>
						</div>
						<div class="flex items-center gap-4 text-xs text-slate-500 mt-2">
							<span>Triggers: {rule.trigger_count}{rule.max_triggers ? `/${rule.max_triggers}` : ''}</span>
							{#if rule.cooldown_minutes}
								<span>Cooldown: {rule.cooldown_minutes}m</span>
							{/if}
							{#if rule.last_triggered_at}
								<span>Last: {new Date(rule.last_triggered_at).toLocaleString()}</span>
							{/if}
							{#if rule.tags?.length}
								<span>{rule.tags.join(', ')}</span>
							{/if}
						</div>
					</div>
				{/each}
			</div>
		{/if}
</div>
