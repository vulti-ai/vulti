<script lang="ts">
	import { store } from '$lib/stores/app.svelte';

	let activeTab = $state<'read' | 'write'>('read');

	function statusDot(status: string): string {
		if (status === 'connected') return 'bg-green-500';
		if (status === 'configured') return 'bg-yellow-500';
		return 'bg-red-500';
	}

	// Classify integrations into read vs write
	const readServices: Record<string, string[]> = {
		'Messages & Email': ['Telegram', 'WhatsApp', 'iMessage', 'Discord', 'Slack', 'Email', 'Gmail', 'iCloud Mail'],
		'Files & Storage': ['Google Drive', 'iCloud Drive', 'Dropbox', 'Local Folders', 'Proton Drive'],
		'Calendar & Contacts': ['Google Calendar', 'iCloud Calendar', 'Google Contacts', 'iCloud Contacts'],
		'Knowledge': ['Apple Notes', 'Notion', 'Obsidian', 'Web', 'Web Search'],
		'Code': ['GitHub', 'GitLab'],
		'Other': ['Spotify', 'HomeKit', 'Home Assistant'],
	};

	const writeServices: Record<string, string[]> = {
		'Send Messages & Email': ['Telegram', 'WhatsApp', 'iMessage', 'Discord', 'Slack', 'Email', 'Gmail', 'iCloud Mail'],
		'Write to Storage': ['Google Drive', 'iCloud Drive', 'Dropbox', 'Local Folders', 'Proton Drive'],
		'Manage Calendar & Contacts': ['Google Calendar', 'iCloud Calendar', 'Google Contacts', 'iCloud Contacts'],
		'Write to Knowledge': ['Apple Notes', 'Notion', 'Obsidian'],
		'Push Code': ['GitHub', 'GitLab'],
		'Control': ['Spotify', 'HomeKit', 'Home Assistant'],
	};

	function getIntegration(name: string) {
		return store.integrations.find(i =>
			i.name.toLowerCase().includes(name.toLowerCase()) ||
			name.toLowerCase().includes(i.name.toLowerCase())
		);
	}

	function matchesAny(names: string[]) {
		return names.some(n => getIntegration(n));
	}

	let readCount = $derived(
		store.integrations.filter(i => i.status === 'connected').length
	);

	let writeCount = $derived(
		store.integrations.filter(i => i.status === 'connected').length
	);

	let serviceMap = $derived(activeTab === 'read' ? readServices : writeServices);
	let allMapped = $derived(Object.values(serviceMap).flat());
	let unmapped = $derived(store.integrations.filter(i => !allMapped.some(n => i.name.toLowerCase().includes(n.toLowerCase()) || n.toLowerCase().includes(i.name.toLowerCase()))));

	let authenticatedProviders = $derived(
		store.providers.filter(p => p.authenticated)
	);

	// Collect env_keys from all known AI providers to filter secrets
	let aiKeyNames = $derived(
		new Set(store.providers.flatMap(p => p.env_keys))
	);

	let otherSecrets = $derived(
		store.secrets.filter(s => s.is_set && !aiKeyNames.has(s.key))
	);
</script>

<div class="h-full overflow-y-auto">
	<div class="mx-auto max-w-3xl space-y-6 p-6">

		<!-- AI Providers & Keys -->
		<section>
			<h4 class="mb-2 text-xs font-medium uppercase text-ink-muted">AI Providers</h4>
			<div class="grid gap-2">
				{#if authenticatedProviders.length > 0}
					{#each authenticatedProviders as provider}
						{@const secret = store.secrets.find(s => s.is_set && provider.env_keys.includes(s.key))}
						<div class="flex items-center gap-3 rounded-lg border border-border bg-surface px-4 py-3">
							<span class="h-2 w-2 shrink-0 rounded-full bg-green-500"></span>
							<span class="text-sm font-medium text-ink">{provider.name}</span>
							{#if secret}
								<code class="ml-auto text-xs text-ink-faint">{secret.masked_value}</code>
							{/if}
						</div>
					{/each}
				{:else}
					<div class="flex items-center gap-3 rounded-lg border border-border bg-surface px-4 py-3">
						<span class="h-2 w-2 shrink-0 rounded-full bg-red-500"></span>
						<span class="text-sm text-ink-faint">No AI provider configured</span>
					</div>
				{/if}
			</div>
		</section>

		<!-- Gateway status bar -->
		<div class="flex items-center gap-2">
			<div class="h-2.5 w-2.5 rounded-full {store.systemStatus.gateway_state === 'running' ? 'bg-green-500' : 'bg-red-500'}"></div>
			<span class="text-sm font-medium uppercase text-ink-muted">Gateway</span>
			<span class="text-xs text-ink-faint capitalize">{store.systemStatus.gateway_state}</span>
			{#if Object.keys(store.systemStatus.platforms).length > 0}
				<div class="ml-auto flex flex-wrap gap-2">
					{#each Object.entries(store.systemStatus.platforms) as [name, info]}
						<span class="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-0.5 text-xs">
							<span class="h-1.5 w-1.5 rounded-full {info.state === 'connected' ? 'bg-green-500' : 'bg-red-500'}"></span>
							<span class="capitalize text-ink">{name}</span>
						</span>
					{/each}
				</div>
			{/if}
		</div>

		<!-- Read / Write tabs -->
		<div class="flex gap-1 border-b border-border">
			<button
				onclick={() => activeTab = 'read'}
				class="border-b-2 px-4 py-3 text-sm transition-colors
					{activeTab === 'read' ? 'border-primary text-ink font-medium' : 'border-transparent text-ink-dim hover:text-ink'}"
			>
				Read
			</button>
			<button
				onclick={() => activeTab = 'write'}
				class="border-b-2 px-4 py-3 text-sm transition-colors
					{activeTab === 'write' ? 'border-primary text-ink font-medium' : 'border-transparent text-ink-dim hover:text-ink'}"
			>
				Write
			</button>
		</div>

		<!-- Tab content -->
		{#each Object.entries(serviceMap) as [group, names]}
			{#if matchesAny(names)}
				<section>
					<h4 class="mb-2 text-xs font-medium uppercase text-ink-muted">{group}</h4>
					<div class="grid gap-2">
						{#each names as name}
							{@const integ = getIntegration(name)}
							{#if integ}
								<div class="flex items-center gap-3 rounded-lg border border-border bg-surface px-4 py-3">
									<span class="h-2 w-2 shrink-0 rounded-full {statusDot(integ.status)}"></span>
									<div class="flex-1 min-w-0">
										<span class="text-sm font-medium text-ink">{integ.name}</span>
										{#if integ.details}
											{#each Object.entries(integ.details).slice(0, 2) as [key, value]}
												{#if value && key !== 'registration_token'}
													<span class="ml-2 text-xs text-ink-faint">
														{#if Array.isArray(value)}{value.join(', ')}{:else}{value}{/if}
													</span>
												{/if}
											{/each}
										{/if}
									</div>
									<span class="text-xs capitalize {integ.status === 'connected' ? 'text-green-500' : 'text-ink-faint'}">{integ.status}</span>
								</div>
							{/if}
						{/each}
					</div>
				</section>
			{/if}
		{/each}

		<!-- Show remaining integrations not in the map -->
		{#if unmapped.length > 0}
			<section>
				<h4 class="mb-2 text-xs font-medium uppercase text-ink-muted">Other</h4>
				<div class="grid gap-2">
					{#each unmapped as integ}
						<div class="flex items-center gap-3 rounded-lg border border-border bg-surface px-4 py-3">
							<span class="h-2 w-2 shrink-0 rounded-full {statusDot(integ.status)}"></span>
							<span class="text-sm font-medium text-ink">{integ.name}</span>
							<span class="ml-auto text-xs capitalize {integ.status === 'connected' ? 'text-green-500' : 'text-ink-faint'}">{integ.status}</span>
						</div>
					{/each}
				</div>
			</section>
		{/if}

		<!-- API Keys (non-AI keys only, AI keys shown at top) -->
		{#if otherSecrets.length > 0}
			<section class="border-t border-border pt-6">
				<h4 class="mb-2 text-xs font-medium uppercase text-ink-muted">API Keys</h4>
				<div class="grid gap-1">
					{#each otherSecrets as secret}
						<div class="flex items-center gap-3 rounded-md bg-surface px-3 py-2">
							<span class="h-1.5 w-1.5 rounded-full bg-green-500"></span>
							<span class="flex-1 text-sm text-ink">{secret.key}</span>
							<code class="text-xs text-ink-faint">{secret.masked_value}</code>
						</div>
					{/each}
				</div>
			</section>
		{/if}

	</div>
</div>
