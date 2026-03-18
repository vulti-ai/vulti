<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { api } from '$lib/api';
	import { onMount } from 'svelte';

	let gatewayConnected = $derived(store.gatewayGlobal.gateway?.connected ?? false);
	let matrixStatus = $derived(store.systemStatus.platforms?.matrix);
	let matrixConnected = $derived(matrixStatus?.state === 'connected');
	let matrixIntegration = $derived(store.integrations.find(i => i.id === 'matrix'));

	let showAddKey = $state(false);
	let newKeyName = $state('OPENROUTER_API_KEY');
	let newKeyValue = $state('');
	let addingKey = $state(false);
	let error = $state('');

	// Matrix owner account setup
	let hasOwnerAccount = $derived(!!matrixIntegration?.details?.owner_username);
	let matrixUsername = $state('');
	let matrixPassword = $state('');
	let matrixDisplayName = $state('');
	let registeringMatrix = $state(false);
	let matrixError = $state('');

	async function handleMatrixRegister() {
		if (!matrixUsername.trim() || !matrixPassword.trim()) return;
		registeringMatrix = true;
		matrixError = '';
		try {
			await api.registerMatrixOwner(
				matrixUsername.trim(),
				matrixPassword.trim(),
				matrixDisplayName.trim() || matrixUsername.trim()
			);
			// Reload integrations to get the new credentials
			await store.loadIntegrations();
		} catch (e: any) {
			matrixError = e.message || 'Registration failed';
		} finally {
			registeringMatrix = false;
		}
	}

	const providerOptions = [
		{ id: 'openrouter', name: 'OpenRouter', key: 'OPENROUTER_API_KEY', desc: '200+ models via one API key' },
		{ id: 'anthropic', name: 'Anthropic', key: 'ANTHROPIC_API_KEY', desc: 'Claude Opus, Sonnet, Haiku' },
		{ id: 'openai', name: 'OpenAI', key: 'OPENAI_API_KEY', desc: 'GPT-4o, o1, o3' },
		{ id: 'deepseek', name: 'DeepSeek', key: 'DEEPSEEK_API_KEY', desc: 'DeepSeek R1, V3' },
		{ id: 'google', name: 'Google AI', key: 'GOOGLE_API_KEY', desc: 'Gemini 2.5' },
	];

	const toolKeys = [
		{ key: 'FIRECRAWL_API_KEY', label: 'Firecrawl', desc: 'Web search & extraction', category: 'Tools' },
		{ key: 'FAL_KEY', label: 'FAL', desc: 'Image generation', category: 'Tools' },
		{ key: 'ELEVENLABS_API_KEY', label: 'ElevenLabs', desc: 'Text-to-speech', category: 'Tools' },
		{ key: 'BROWSERBASE_API_KEY', label: 'Browserbase', desc: 'Cloud browser automation', category: 'Tools' },
		{ key: 'GITHUB_TOKEN', label: 'GitHub', desc: 'Repository access', category: 'Tools' },
		{ key: 'WANDB_API_KEY', label: 'Weights & Biases', desc: 'ML experiment tracking', category: 'Tools' },
	];

	let llmSecrets = $derived(
		store.secrets.filter(s => s.category === 'LLM Providers' && s.is_set)
	);

	let toolSecrets = $derived(
		store.secrets.filter(s => toolKeys.some(t => t.key === s.key))
	);

	// Default model selection
	let selectedProvider = $state('');
	let selectedModel = $state('');
	let providerModels = $derived(
		selectedProvider ? (store.providers.find(p => p.id === selectedProvider)?.models ?? []) : []
	);

	// Tool key being added
	let addingToolKey = $state('');
	let toolKeyValue = $state('');
	let savingTool = $state(false);
	let toolError = $state('');

	async function handleAddToolKey() {
		if (!addingToolKey || !toolKeyValue.trim()) return;
		savingTool = true;
		toolError = '';
		try {
			await store.addSecret(addingToolKey, toolKeyValue.trim());
			toolKeyValue = '';
			addingToolKey = '';
		} catch (e: any) {
			toolError = e.message || 'Failed to save';
		} finally {
			savingTool = false;
		}
	}

	async function handleRemoveToolKey(key: string) {
		try { await store.deleteSecret(key); } catch {}
	}

	onMount(() => {
		store.loadSecrets();
		store.loadProviders();
		store.loadStatus();
		store.loadIntegrations();
	});

	function handleGatewayComplete() {
		store.updateGlobalSettings({ gateway: { connected: true } });
	}

	async function handleAddKey() {
		if (!newKeyName || !newKeyValue.trim()) return;
		addingKey = true;
		error = '';
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

	async function handleRemoveKey(key: string) {
		try {
			await store.deleteSecret(key);
		} catch (e: any) {
			error = e.message || 'Failed to remove';
		}
	}
</script>

<div class="mx-auto max-w-2xl space-y-8 overflow-y-auto p-8">
	<!-- 1. Gateway -->
	<section>
		<h3 class="mb-1 text-base font-semibold text-ink">Gateway</h3>
		<p class="mb-4 text-sm text-ink-muted">Local agent runtime that processes messages and runs tools.</p>
		<div class="flex items-center justify-between rounded-lg border border-border bg-surface px-4 py-3">
			<div class="flex items-center gap-3">
				<span class="h-2 w-2 rounded-full {gatewayConnected ? 'bg-green-500' : 'bg-amber-500'}"></span>
				<div>
					<p class="text-sm font-medium text-ink">Gateway</p>
					<p class="text-xs text-ink-muted font-mono">{gatewayConnected ? 'Connected' : 'Not connected'}{gatewayConnected ? ' · port 8080' : ''}</p>
				</div>
			</div>
			{#if !gatewayConnected}
				<button
					onclick={handleGatewayComplete}
					class="text-xs text-primary hover:underline"
				>
					Connect
				</button>
			{/if}
		</div>
	</section>

	<!-- 2. Matrix -->
	<section>
		<h3 class="mb-1 text-base font-semibold text-ink">Matrix</h3>
		<p class="mb-4 text-sm text-ink-muted">Chat with your agents from any device.</p>
		<div class="flex items-center justify-between rounded-lg border border-border bg-surface px-4 py-3">
			<div class="flex items-center gap-3">
				<span class="h-2 w-2 rounded-full {matrixConnected ? 'bg-green-500' : 'bg-amber-500'}"></span>
				<div>
					<p class="text-sm font-medium text-ink">Homeserver</p>
					<p class="text-xs text-ink-muted font-mono">
						{matrixConnected ? 'Connected' : 'Not connected'}{matrixConnected ? ' · port 6167' : ''}
					</p>
				</div>
			</div>
			{#if matrixConnected}
				<span class="text-xs text-green-500">Ready</span>
			{/if}
		</div>

		{#if matrixConnected && matrixIntegration?.details}
			{#if !hasOwnerAccount}
				<!-- Setup form: create your Matrix account -->
				<div class="mt-4 rounded-lg border border-border bg-surface-hover p-4 space-y-3">
					<p class="text-sm font-medium text-ink">Create your Matrix account</p>
					<p class="text-xs text-ink-muted">Pick a username and password to chat with your agents from Element.</p>
					<div class="space-y-2">
						<input
							type="text"
							bind:value={matrixDisplayName}
							placeholder="Display name (e.g., JP)"
							class="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-primary focus:outline-none"
						/>
						<div class="flex gap-2">
							<input
								type="text"
								bind:value={matrixUsername}
								placeholder="Username"
								class="flex-1 rounded-md border border-border bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-primary focus:outline-none"
							/>
							<input
								type="text"
								bind:value={matrixPassword}
								placeholder="Password"
								class="flex-1 rounded-md border border-border bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-primary focus:outline-none"
								onkeydown={(e) => { if (e.key === 'Enter') handleMatrixRegister(); }}
							/>
						</div>
					</div>
					{#if matrixError}
						<p class="text-xs text-red-400">{matrixError}</p>
					{/if}
					<button
						onclick={handleMatrixRegister}
						disabled={registeringMatrix || !matrixUsername.trim() || !matrixPassword.trim()}
						class="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-white hover:bg-primary-hover disabled:opacity-50"
					>
						{registeringMatrix ? 'Creating...' : 'Create Account'}
					</button>
				</div>
			{:else}
				<!-- Show credentials and connection instructions -->
				<div class="mt-4 rounded-lg border border-border bg-surface-hover p-4 space-y-3">
					<p class="text-sm font-medium text-ink">Connect from your phone</p>
					<ol class="text-xs text-ink-muted space-y-2 list-decimal list-inside">
						<li>Download <strong>Element X</strong> from the App Store</li>
						<li>Tap <strong>"I already have an account"</strong></li>
						<li>Enter your server and credentials:</li>
					</ol>
					<div class="space-y-2">
						<div class="rounded-md bg-surface px-3 py-2">
							<p class="text-xs text-ink-faint mb-0.5">Server</p>
							<code class="text-sm text-ink font-mono select-all">{matrixIntegration.details.homeserver_url}</code>
						</div>
						<div class="flex gap-2">
							<div class="flex-1 rounded-md bg-surface px-3 py-2">
								<p class="text-xs text-ink-faint mb-0.5">Username</p>
								<code class="text-sm text-ink font-mono select-all">{matrixIntegration.details.owner_username}</code>
							</div>
							<div class="flex-1 rounded-md bg-surface px-3 py-2">
								<p class="text-xs text-ink-faint mb-0.5">Password</p>
								<code class="text-sm text-ink font-mono select-all">{matrixIntegration.details.owner_password}</code>
							</div>
						</div>
					</div>
				</div>
			{/if}
		{/if}
	</section>

	<!-- 4. AI Provider -->
	<section>
		<h3 class="mb-1 text-base font-semibold text-ink">AI Provider</h3>
		<p class="mb-4 text-sm text-ink-muted">Add API keys and choose a default model. All agents inherit this.</p>

		<!-- Connected providers -->
		<div class="space-y-2 mb-4">
			{#each providerOptions as prov}
				{@const secret = store.secrets.find(s => s.key === prov.key && s.is_set)}
				{@const providerData = store.providers.find(p => p.id === prov.id)}
				<div class="flex items-center justify-between rounded-lg border border-border bg-surface px-4 py-3">
					<div class="flex items-center gap-3">
						<span class="h-2 w-2 rounded-full {secret ? 'bg-green-500' : 'bg-ink-faint'}"></span>
						<div>
							<p class="text-sm font-medium text-ink">{prov.name}</p>
							<p class="text-xs text-ink-muted">{prov.desc}</p>
						</div>
					</div>
					{#if secret}
						<div class="flex items-center gap-2">
							<code class="text-xs text-ink-faint">{secret.masked_value}</code>
							<button onclick={() => handleRemoveKey(prov.key)} class="text-xs text-red-400 hover:text-red-300">Remove</button>
						</div>
					{:else}
						<button
							onclick={() => { showAddKey = true; newKeyName = prov.key; }}
							class="text-xs text-primary hover:underline"
						>
							Add Key
						</button>
					{/if}
				</div>
			{/each}
		</div>

		<!-- Add key form (reusable) -->
		{#if showAddKey}
			<div class="rounded-lg border border-border bg-surface-hover p-4 mb-4">
				<p class="mb-2 text-xs text-ink-muted">Adding: <strong>{providerOptions.find(p => p.key === newKeyName)?.name || newKeyName}</strong></p>
				<div class="flex gap-2 mb-3">
					<input
						type="password"
						bind:value={newKeyValue}
						placeholder="Paste API key"
						class="flex-1 rounded-md border border-border bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-primary focus:outline-none"
						onkeydown={(e) => { if (e.key === 'Enter') handleAddKey(); }}
					/>
				</div>
				{#if error}
					<p class="mb-2 text-xs text-red-400">{error}</p>
				{/if}
				<div class="flex gap-2">
					<button
						onclick={handleAddKey}
						disabled={addingKey || !newKeyValue.trim()}
						class="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-white hover:bg-primary-hover disabled:opacity-50"
					>
						{addingKey ? 'Saving...' : 'Save'}
					</button>
					<button onclick={() => { showAddKey = false; error = ''; }} class="text-sm text-ink-muted hover:text-ink">
						Cancel
					</button>
				</div>
			</div>
		{/if}
	</section>

</div>
