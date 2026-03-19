<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { onMount } from 'svelte';

	let showAddForm = $state(false);
	let newName = $state('');
	let newType = $state('api_key');
	let newDescription = $state('');
	let newTags = $state('');
	let newCredKey = $state('');
	let newCredValue = $state('');
	let credPairs = $state<{ key: string; value: string }[]>([]);
	let saving = $state(false);
	let error = $state('');

	// MCP-specific
	let mcpCommand = $state('');
	let mcpArgs = $state('');

	onMount(() => {
		store.loadConnections();
		store.loadSecrets();
		store.loadProviders();
		store.loadStatus();
		store.loadIntegrations();
	});

	function addCredPair() {
		if (newCredKey.trim() && newCredValue.trim()) {
			credPairs = [...credPairs, { key: newCredKey.trim(), value: newCredValue.trim() }];
			newCredKey = '';
			newCredValue = '';
		}
	}

	function removeCredPair(index: number) {
		credPairs = credPairs.filter((_, i) => i !== index);
	}

	async function handleAdd() {
		if (!newName.trim()) return;
		saving = true;
		error = '';
		try {
			const credentials: Record<string, string> = {};
			for (const pair of credPairs) {
				credentials[pair.key] = pair.value;
			}
			const mcp = newType === 'mcp' && mcpCommand.trim()
				? { command: mcpCommand.trim(), args: mcpArgs.trim().split(/\s+/).filter(Boolean) }
				: undefined;

			await store.addConnection({
				name: newName.trim(),
				connType: newType,
				description: newDescription.trim(),
				tags: newTags.split(',').map(t => t.trim()).filter(Boolean),
				credentials,
				mcp,
			});
			// Reset form
			newName = '';
			newType = 'api_key';
			newDescription = '';
			newTags = '';
			credPairs = [];
			mcpCommand = '';
			mcpArgs = '';
			showAddForm = false;
		} catch (e: any) {
			error = e.message || 'Failed to add connection';
		} finally {
			saving = false;
		}
	}

	async function handleDelete(name: string) {
		try {
			await store.deleteConnection(name);
		} catch {}
	}

	async function handleToggle(name: string, enabled: boolean) {
		try {
			await store.updateConnection(name, { enabled: !enabled });
		} catch {}
	}

	function typeLabel(t: string): string {
		switch (t) {
			case 'mcp': return 'MCP';
			case 'api_key': return 'API Key';
			case 'oauth': return 'OAuth';
			case 'custom': return 'Custom';
			default: return t;
		}
	}
</script>

<div class="space-y-6">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<p class="text-sm text-ink-muted">External services available to your agents.</p>
		<button
			onclick={() => showAddForm = !showAddForm}
			class="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-hover"
		>
			{showAddForm ? 'Cancel' : '+ Add'}
		</button>
	</div>

	<!-- Add form -->
	{#if showAddForm}
		<div class="rounded-lg border border-border bg-surface-hover p-4 space-y-3">
			<div class="grid grid-cols-2 gap-3">
				<div>
					<label class="block text-xs text-ink-muted mb-1">Name</label>
					<input
						bind:value={newName}
						placeholder="e.g. github"
						class="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-primary focus:outline-none"
					/>
				</div>
				<div>
					<label class="block text-xs text-ink-muted mb-1">Type</label>
					<select
						bind:value={newType}
						class="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none"
					>
						<option value="api_key">API Key</option>
						<option value="mcp">MCP Server</option>
						<option value="oauth">OAuth</option>
						<option value="custom">Custom</option>
					</select>
				</div>
			</div>

			<div>
				<label class="block text-xs text-ink-muted mb-1">Description</label>
				<input
					bind:value={newDescription}
					placeholder="What this connection does"
					class="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-primary focus:outline-none"
				/>
			</div>

			<div>
				<label class="block text-xs text-ink-muted mb-1">Tags (comma-separated)</label>
				<input
					bind:value={newTags}
					placeholder="e.g. web, search, code"
					class="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-primary focus:outline-none"
				/>
			</div>

			{#if newType === 'mcp'}
				<div class="grid grid-cols-2 gap-3">
					<div>
						<label class="block text-xs text-ink-muted mb-1">MCP Command</label>
						<input
							bind:value={mcpCommand}
							placeholder="e.g. npx"
							class="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-primary focus:outline-none"
						/>
					</div>
					<div>
						<label class="block text-xs text-ink-muted mb-1">MCP Args</label>
						<input
							bind:value={mcpArgs}
							placeholder="e.g. -y @modelcontextprotocol/server-github"
							class="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-primary focus:outline-none"
						/>
					</div>
				</div>
			{/if}

			<!-- Credentials -->
			<div>
				<label class="block text-xs text-ink-muted mb-1">Credentials</label>
				{#each credPairs as pair, i}
					<div class="flex items-center gap-2 mb-1">
						<code class="text-xs text-ink-dim bg-surface rounded px-1.5 py-0.5">{pair.key}</code>
						<code class="text-xs text-ink-faint">{pair.value.slice(0, 8)}...</code>
						<button onclick={() => removeCredPair(i)} class="text-xs text-red-400 hover:text-red-300">x</button>
					</div>
				{/each}
				<div class="flex gap-2">
					<input
						bind:value={newCredKey}
						placeholder="ENV_VAR"
						class="flex-1 rounded-md border border-border bg-surface px-2 py-1.5 text-xs font-mono text-ink placeholder:text-ink-faint focus:border-primary focus:outline-none"
					/>
					<input
						bind:value={newCredValue}
						type="password"
						placeholder="value"
						class="flex-1 rounded-md border border-border bg-surface px-2 py-1.5 text-xs text-ink placeholder:text-ink-faint focus:border-primary focus:outline-none"
						onkeydown={(e) => { if (e.key === 'Enter') addCredPair(); }}
					/>
					<button
						onclick={addCredPair}
						disabled={!newCredKey.trim() || !newCredValue.trim()}
						class="rounded-md border border-border px-2 py-1.5 text-xs text-ink-dim hover:bg-surface-hover disabled:opacity-30"
					>+</button>
				</div>
			</div>

			{#if error}
				<p class="text-xs text-red-400">{error}</p>
			{/if}

			<button
				onclick={handleAdd}
				disabled={saving || !newName.trim()}
				class="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-white hover:bg-primary-hover disabled:opacity-50"
			>
				{saving ? 'Saving...' : 'Add Connection'}
			</button>
		</div>
	{/if}

	<!-- Connection list -->
	{#if store.connections.length === 0 && !showAddForm}
		<div class="rounded-lg border border-dashed border-border py-8 text-center">
			<p class="text-sm text-ink-muted">No connections yet.</p>
			<p class="text-xs text-ink-faint mt-1">Add API keys, MCP servers, and other integrations.</p>
		</div>
	{:else}
		<div class="space-y-2">
			{#each store.connections as conn}
				<div class="flex items-center justify-between rounded-lg border border-border bg-surface px-4 py-3">
					<div class="flex items-center gap-3 min-w-0">
						<span class="h-2 w-2 rounded-full flex-shrink-0 {conn.enabled ? 'bg-green-500' : 'bg-ink-faint'}"></span>
						<div class="min-w-0">
							<div class="flex items-center gap-2">
								<p class="text-sm font-medium text-ink">{conn.name}</p>
								<span class="rounded-full bg-ink/5 px-1.5 py-0.5 text-[10px] text-ink-dim">{typeLabel(conn.type)}</span>
								{#each conn.tags as tag}
									<span class="rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary">{tag}</span>
								{/each}
							</div>
							<p class="text-xs text-ink-muted truncate">{conn.description}</p>
							{#if Object.keys(conn.credentials).length > 0}
								<p class="text-[10px] text-ink-faint font-mono mt-0.5">
									{Object.entries(conn.credentials).map(([k, v]) => `${k}=${v}`).join(' ')}
								</p>
							{/if}
						</div>
					</div>
					<div class="flex items-center gap-2 flex-shrink-0">
						<button
							onclick={() => handleToggle(conn.name, conn.enabled)}
							class="text-xs {conn.enabled ? 'text-ink-muted hover:text-amber-500' : 'text-amber-500 hover:text-green-500'}"
						>
							{conn.enabled ? 'Disable' : 'Enable'}
						</button>
						<button
							onclick={() => handleDelete(conn.name)}
							class="text-xs text-red-400 hover:text-red-300"
						>
							Remove
						</button>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>
