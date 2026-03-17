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
			category: 'communication',
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
		<h3 class="text-lg font-semibold text-ink">Communication</h3>
		<p class="text-sm text-ink-dim">Connect email and messaging services for this agent.</p>
	</div>

	<div class="space-y-3">
		<h4 class="text-xs font-medium uppercase text-ink-muted">Email</h4>
		<ServiceConnector
			type="gmail" label="Gmail" category="communication"
			description="Google email (OAuth)"
			status={getService('gmail') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('gmail', 'Gmail')}
			onDisconnect={() => disconnectService('gmail')}
		/>
		<ServiceConnector
			type="icloud_mail" label="iCloud Mail" category="communication"
			description="Apple email (app-specific password)"
			status={getService('icloud_mail') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('icloud_mail', 'iCloud Mail')}
			onDisconnect={() => disconnectService('icloud_mail')}
		/>
	</div>

	<div class="space-y-3">
		<h4 class="text-xs font-medium uppercase text-ink-muted">Messaging</h4>
		<ServiceConnector
			type="whatsapp" label="WhatsApp" category="communication"
			description="Link via QR code"
			status={getService('whatsapp') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('whatsapp', 'WhatsApp')}
			onDisconnect={() => disconnectService('whatsapp')}
		/>
		<ServiceConnector
			type="telegram" label="Telegram" category="communication"
			description="Bot token via @BotFather"
			status={getService('telegram') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('telegram', 'Telegram')}
			onDisconnect={() => disconnectService('telegram')}
		/>
		<ServiceConnector
			type="imessage" label="iMessage" category="communication"
			description="Local Mac integration"
			status={getService('imessage') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('imessage', 'iMessage')}
			onDisconnect={() => disconnectService('imessage')}
		/>
		<ServiceConnector
			type="slack" label="Slack" category="communication"
			description="Workspace bot token"
			status={getService('slack') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('slack', 'Slack')}
			onDisconnect={() => disconnectService('slack')}
		/>
		<ServiceConnector
			type="discord" label="Discord" category="communication"
			description="Bot token"
			status={getService('discord') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('discord', 'Discord')}
			onDisconnect={() => disconnectService('discord')}
		/>
	</div>
</div>
