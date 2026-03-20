<script lang="ts">
	import { api, type AuditEvent } from '$lib/api';
	import { store } from '$lib/stores/app.svelte';

	let events = $state<AuditEvent[]>([]);
	let loading = $state(false);
	let filterAgent = $state('');
	let filterType = $state('');
	let filterPlatform = $state('');

	const platforms = ['', 'app', 'telegram', 'discord', 'slack', 'matrix', 'signal', 'email'];

	const eventTypes = [
		'', 'message_received', 'message_response', 'interagent_send', 'interagent_receive',
		'cron_execute', 'rule_trigger', 'permission_request',
		'permission_approved', 'permission_denied',
	];

	const eventLabels: Record<string, string> = {
		message_received: 'Owner Msg',
		message_response: 'Agent Reply',
		interagent_send: 'Agent Send',
		interagent_receive: 'Agent Reply',
		cron_execute: 'Cron',
		rule_trigger: 'Rule',
		permission_request: 'Permission Req',
		permission_approved: 'Approved',
		permission_denied: 'Denied',
	};

	const eventColors: Record<string, string> = {
		message_received: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
		message_response: 'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300',
		interagent_send: 'bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300',
		interagent_receive: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300',
		cron_execute: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
		rule_trigger: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
		permission_request: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300',
		permission_approved: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
		permission_denied: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
	};

	async function load() {
		loading = true;
		try {
			let result = await api.listAuditEvents(
				200,
				filterAgent || undefined,
				undefined,
				filterType || undefined,
			);
			// Client-side platform filter (platform is inside details JSON)
			if (filterPlatform) {
				result = result.filter(ev =>
					ev.details && (ev.details as Record<string, unknown>).platform === filterPlatform
				);
			}
			events = result.reverse();
		} catch {
			events = [];
		}
		loading = false;
	}

	$effect(() => {
		// Re-run when filters change
		const _a = filterAgent;
		const _t = filterType;
		const _p = filterPlatform;
		load();
	});

	function formatTime(ts: string): string {
		try {
			const d = new Date(ts);
			const now = new Date();
			const isToday = d.toDateString() === now.toDateString();
			if (isToday) {
				return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
			}
			return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' +
				d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
		} catch {
			return ts.slice(0, 19);
		}
	}

	function getPreview(details: Record<string, unknown> | undefined): string {
		if (!details) return '';
		const preview = (details.message_preview || details.response_preview || details.prompt_preview || '') as string;
		if (preview) return preview.slice(0, 120).replace(/\n/g, ' ');
		return '';
	}

	function getDetail(details: Record<string, unknown> | undefined): string {
		if (!details) return '';
		const parts: string[] = [];
		if (details.target) parts.push(`to ${details.target}`);
		if (details.sender) parts.push(`from ${details.sender}`);
		if (details.connection) parts.push(`${details.connection}`);
		if (details.job_name) parts.push(`${details.job_name}`);
		if (details.rule_name) parts.push(`${details.rule_name}`);
		return parts.join(' ');
	}

	function getPlatform(details: Record<string, unknown> | undefined): string {
		if (!details?.platform) return '';
		return String(details.platform);
	}
</script>

<div class="flex h-full flex-col gap-3 p-1">
	<!-- Filters -->
	<div class="flex gap-2">
		<select
			class="audit-select flex-1"
			bind:value={filterAgent}
		>
			<option value="">All agents</option>
			{#each store.agents as agent}
				<option value={agent.id}>{agent.name}</option>
			{/each}
		</select>
		<select
			class="audit-select flex-1"
			bind:value={filterType}
		>
			<option value="">All events</option>
			{#each eventTypes.slice(1) as t}
				<option value={t}>{eventLabels[t] || t}</option>
			{/each}
		</select>
		<select
			class="audit-select flex-1"
			bind:value={filterPlatform}
		>
			<option value="">All platforms</option>
			{#each platforms.slice(1) as p}
				<option value={p}>{p}</option>
			{/each}
		</select>
		<button class="audit-btn" onclick={load} title="Refresh">
			<svg class:animate-spin={loading} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
				<path d="M21 12a9 9 0 1 1-6.219-8.56" />
			</svg>
		</button>
	</div>

	<!-- Event list -->
	<div class="flex-1 overflow-y-auto">
		{#if events.length === 0 && !loading}
			<div class="py-12 text-center text-sm text-ink-muted">No audit events yet.</div>
		{:else}
			<div class="flex flex-col gap-1">
				{#each events as ev}
					<div class="audit-row">
						<div class="flex items-center gap-2">
							<span class="audit-badge {eventColors[ev.event] || 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'}">
								{eventLabels[ev.event] || ev.event}
							</span>
							<span class="text-xs font-medium text-ink-dim">{ev.agent_id}</span>
							{#if getDetail(ev.details)}
								<span class="text-xs text-ink-muted">{getDetail(ev.details)}</span>
							{/if}
							{#if getPlatform(ev.details)}
								<span class="platform-tag">{getPlatform(ev.details)}</span>
							{/if}
							<span class="ml-auto text-[10px] tabular-nums text-ink-muted/60">{formatTime(ev.ts)}</span>
						</div>
						{#if getPreview(ev.details)}
							<p class="mt-0.5 truncate text-[11px] leading-tight text-ink-muted">{getPreview(ev.details)}</p>
						{/if}
						{#if ev.trace_id}
							<span class="mt-0.5 inline-block text-[9px] font-mono text-ink-muted/40">trace:{ev.trace_id}</span>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>

<style>
	.audit-select {
		appearance: none;
		padding: 4px 8px;
		border-radius: 6px;
		border: 1px solid rgba(0, 0, 0, 0.08);
		background: rgba(0, 0, 0, 0.02);
		font-size: 11px;
		color: var(--ink-dim, #555);
		outline: none;
		transition: border-color 150ms;
	}
	.audit-select:focus {
		border-color: rgba(0, 0, 0, 0.2);
	}
	:global(.dark) .audit-select {
		border-color: rgba(255, 255, 255, 0.1);
		background: rgba(255, 255, 255, 0.04);
		color: rgba(255, 255, 255, 0.7);
	}

	.audit-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 28px;
		height: 28px;
		border-radius: 6px;
		border: 1px solid rgba(0, 0, 0, 0.08);
		background: rgba(0, 0, 0, 0.02);
		color: var(--ink-muted, #888);
		transition: all 150ms;
		cursor: pointer;
	}
	.audit-btn:hover {
		background: rgba(0, 0, 0, 0.06);
	}
	:global(.dark) .audit-btn {
		border-color: rgba(255, 255, 255, 0.1);
		background: rgba(255, 255, 255, 0.04);
		color: rgba(255, 255, 255, 0.5);
	}

	.audit-row {
		padding: 6px 8px;
		border-radius: 6px;
		transition: background 100ms;
	}
	.audit-row:hover {
		background: rgba(0, 0, 0, 0.03);
	}
	:global(.dark) .audit-row:hover {
		background: rgba(255, 255, 255, 0.03);
	}

	.audit-badge {
		display: inline-block;
		padding: 1px 6px;
		border-radius: 4px;
		font-size: 10px;
		font-weight: 500;
		white-space: nowrap;
	}

	.platform-tag {
		display: inline-block;
		padding: 0 5px;
		border-radius: 3px;
		font-size: 9px;
		font-weight: 500;
		letter-spacing: 0.02em;
		background: rgba(0, 0, 0, 0.04);
		color: var(--ink-muted, #999);
		white-space: nowrap;
	}
	:global(.dark) .platform-tag {
		background: rgba(255, 255, 255, 0.06);
		color: rgba(255, 255, 255, 0.4);
	}
</style>
