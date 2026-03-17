<script lang="ts">
	import { store, type GatewayAgent } from '$lib/stores/app.svelte';
	import ServiceConnector from '../ServiceConnector.svelte';

	let { agent }: { agent: GatewayAgent } = $props();

	function getService(type: string) {
		return agent.services.find(s => s.type === type);
	}

	function connectService(type: string, label: string) {
		store.addServiceToAgent(agent.id, {
			id: crypto.randomUUID(),
			category: 'knowledge',
			type,
			label,
			status: 'connected',
			config: {}
		});
	}

	function disconnectService(type: string) {
		const svc = getService(type);
		if (svc) store.removeServiceFromAgent(agent.id, svc.id);
	}
</script>

<div class="space-y-6">
	<div>
		<h3 class="text-lg font-semibold text-ink">Knowledge</h3>
		<p class="text-sm text-ink-dim">Connect knowledge bases and note-taking apps.</p>
	</div>

	<div class="space-y-3">
		<ServiceConnector
			type="apple_notes" label="Apple Notes" category="knowledge"
			description="Read and create notes"
			status={getService('apple_notes') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('apple_notes', 'Apple Notes')}
			onDisconnect={() => disconnectService('apple_notes')}
		/>
		<ServiceConnector
			type="notion" label="Notion" category="knowledge"
			description="Workspace and docs (API key)"
			status={getService('notion') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('notion', 'Notion')}
			onDisconnect={() => disconnectService('notion')}
		/>
		<ServiceConnector
			type="obsidian" label="Obsidian" category="knowledge"
			description="Local vault (folder path)"
			status={getService('obsidian') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('obsidian', 'Obsidian')}
			onDisconnect={() => disconnectService('obsidian')}
		/>
		<ServiceConnector
			type="web_search" label="Web Search" category="knowledge"
			description="Search the internet"
			status={getService('web_search') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('web_search', 'Web Search')}
			onDisconnect={() => disconnectService('web_search')}
		/>
	</div>
</div>
