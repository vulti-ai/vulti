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
			category: 'other',
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
		<h3 class="text-lg font-semibold text-ink">Other Integrations</h3>
		<p class="text-sm text-ink-dim">Additional services and smart home.</p>
	</div>

	<div class="space-y-3">
		<ServiceConnector
			type="spotify" label="Spotify" category="other"
			description="Music control and recommendations"
			status={getService('spotify') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('spotify', 'Spotify')}
			onDisconnect={() => disconnectService('spotify')}
		/>
		<ServiceConnector
			type="homekit" label="HomeKit" category="other"
			description="Apple smart home control"
			status={getService('homekit') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('homekit', 'HomeKit')}
			onDisconnect={() => disconnectService('homekit')}
		/>
		<ServiceConnector
			type="home_assistant" label="Home Assistant" category="other"
			description="Open-source smart home"
			status={getService('home_assistant') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('home_assistant', 'Home Assistant')}
			onDisconnect={() => disconnectService('home_assistant')}
		/>
		<ServiceConnector
			type="webhook" label="Custom Webhooks" category="other"
			description="HTTP endpoints for custom integrations"
			status={getService('webhook') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('webhook', 'Custom Webhooks')}
			onDisconnect={() => disconnectService('webhook')}
		/>
	</div>
</div>
