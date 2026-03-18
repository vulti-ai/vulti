<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { onMount } from 'svelte';

	let days = $state(30);

	// Reload when active agent changes
	$effect(() => {
		const _agentId = store.activeAgentId; // track dependency
		store.loadAnalytics(days);
	});

	function reload() {
		store.loadAnalytics(days);
	}

	function formatTokens(n: number): string {
		if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
		if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
		return String(n);
	}

	function formatCost(n: number): string {
		return '$' + n.toFixed(2);
	}

	const dayLabels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
</script>

<div class="flex h-full flex-col">
	<header class="flex h-14 shrink-0 items-center justify-between border-b border-border px-6">
		<h2 class="font-semibold">Analytics</h2>
		<div class="flex items-center gap-2">
			<select
				bind:value={days}
				onchange={reload}
				class="rounded-lg border border-border bg-slate-800 px-3 py-1.5 text-xs text-white"
			>
				<option value={7}>7 days</option>
				<option value={14}>14 days</option>
				<option value={30}>30 days</option>
				<option value={90}>90 days</option>
			</select>
		</div>
	</header>

	<div class="flex-1 overflow-y-auto p-6">
		<div class="mx-auto max-w-4xl space-y-6">
			{#if !store.analytics || store.analytics.empty}
				<div class="rounded-xl border border-border bg-surface p-8 text-center text-sm text-slate-400">
					{store.analytics?.error || 'No analytics data available.'}
				</div>
			{:else}
				{@const o = store.analytics.overview!}

				<!-- Overview Cards -->
				<div class="grid grid-cols-2 gap-3 md:grid-cols-4">
					<div class="rounded-xl border border-border bg-surface p-4">
						<p class="text-xs text-slate-400">Sessions</p>
						<p class="mt-1 text-2xl font-bold">{o.total_sessions}</p>
					</div>
					<div class="rounded-xl border border-border bg-surface p-4">
						<p class="text-xs text-slate-400">Messages</p>
						<p class="mt-1 text-2xl font-bold">{o.total_messages}</p>
					</div>
					<div class="rounded-xl border border-border bg-surface p-4">
						<p class="text-xs text-slate-400">Tokens</p>
						<p class="mt-1 text-2xl font-bold">{formatTokens(o.total_tokens)}</p>
					</div>
					<div class="rounded-xl border border-border bg-surface p-4">
						<p class="text-xs text-slate-400">Estimated Cost</p>
						<p class="mt-1 text-2xl font-bold">{formatCost(o.estimated_cost)}</p>
					</div>
				</div>

				<!-- Secondary Stats -->
				<div class="grid grid-cols-3 gap-3">
					<div class="rounded-xl border border-border bg-surface p-4">
						<p class="text-xs text-slate-400">Tool Calls</p>
						<p class="mt-1 text-lg font-semibold">{o.total_tool_calls}</p>
					</div>
					<div class="rounded-xl border border-border bg-surface p-4">
						<p class="text-xs text-slate-400">Avg Messages/Session</p>
						<p class="mt-1 text-lg font-semibold">{o.avg_messages_per_session.toFixed(1)}</p>
					</div>
					<div class="rounded-xl border border-border bg-surface p-4">
						<p class="text-xs text-slate-400">Total Hours</p>
						<p class="mt-1 text-lg font-semibold">{o.total_hours.toFixed(1)}h</p>
					</div>
				</div>

				<!-- Models -->
				{#if store.analytics.models?.length}
					<section>
						<h3 class="mb-3 text-sm font-medium uppercase text-slate-400">Models</h3>
						<div class="rounded-xl border border-border bg-surface">
							<table class="w-full text-left text-sm">
								<thead>
									<tr class="border-b border-border text-xs text-slate-400">
										<th class="px-4 py-3">Model</th>
										<th class="px-4 py-3">Sessions</th>
										<th class="px-4 py-3">Tokens</th>
										<th class="px-4 py-3">Cost</th>
									</tr>
								</thead>
								<tbody>
									{#each store.analytics.models as m}
										<tr class="border-b border-border/50">
											<td class="px-4 py-3 font-mono text-xs">{m.model}</td>
											<td class="px-4 py-3">{m.sessions}</td>
											<td class="px-4 py-3">{formatTokens(m.total_tokens)}</td>
											<td class="px-4 py-3">{formatCost(m.cost)}</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
					</section>
				{/if}

				<!-- Platforms -->
				{#if store.analytics.platforms?.length}
					<section>
						<h3 class="mb-3 text-sm font-medium uppercase text-slate-400">Platforms</h3>
						<div class="grid grid-cols-2 gap-3 md:grid-cols-3">
							{#each store.analytics.platforms as p}
								<div class="rounded-xl border border-border bg-surface p-4">
									<p class="text-xs font-medium uppercase text-primary">{p.platform}</p>
									<p class="mt-1 text-lg font-semibold">{p.sessions} sessions</p>
									<p class="text-xs text-slate-400">{p.messages} messages / {formatTokens(p.total_tokens)} tokens</p>
								</div>
							{/each}
						</div>
					</section>
				{/if}

				<!-- Top Tools -->
				{#if store.analytics.tools?.length}
					<section>
						<h3 class="mb-3 text-sm font-medium uppercase text-slate-400">Top Tools</h3>
						<div class="rounded-xl border border-border bg-surface p-4">
							<div class="space-y-2">
								{#each store.analytics.tools.slice(0, 15) as t}
									{@const maxCalls = store.analytics.tools![0].call_count}
									<div class="flex items-center gap-3">
										<span class="w-40 truncate font-mono text-xs text-slate-300">{t.tool_name}</span>
										<div class="flex-1">
											<div
												class="h-4 rounded bg-primary/30"
												style="width: {Math.max(4, (t.call_count / maxCalls) * 100)}%"
											>
												<div
													class="h-full rounded bg-primary"
													style="width: 100%"
												></div>
											</div>
										</div>
										<span class="w-16 text-right text-xs text-slate-400">{t.call_count}</span>
									</div>
								{/each}
							</div>
						</div>
					</section>
				{/if}

				<!-- Daily Activity -->
				{#if store.analytics.activity}
					<section>
						<h3 class="mb-3 text-sm font-medium uppercase text-slate-400">Weekly Activity</h3>
						<div class="rounded-xl border border-border bg-surface p-4">
							<div class="flex items-end gap-2">
								{#each store.analytics.activity.daily_distribution as count, i}
									{@const maxDaily = Math.max(...store.analytics.activity!.daily_distribution, 1)}
									<div class="flex flex-1 flex-col items-center gap-1">
										<div
											class="w-full rounded bg-primary"
											style="height: {Math.max(4, (count / maxDaily) * 120)}px"
										></div>
										<span class="text-xs text-slate-500">{dayLabels[i]}</span>
									</div>
								{/each}
							</div>
						</div>
					</section>
				{/if}
			{/if}
		</div>
	</div>
</div>
