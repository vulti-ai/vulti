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
			category: 'calendar_contacts',
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
		<h3 class="text-lg font-semibold text-ink">Calendar & Contacts</h3>
		<p class="text-sm text-ink-dim">Let this agent manage your schedule and contacts.</p>
	</div>

	<div class="space-y-3">
		<h4 class="text-xs font-medium uppercase text-ink-muted">Calendar</h4>
		<ServiceConnector
			type="google_calendar" label="Google Calendar" category="calendar_contacts"
			description="View and manage events"
			status={getService('google_calendar') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('google_calendar', 'Google Calendar')}
			onDisconnect={() => disconnectService('google_calendar')}
		/>
		<ServiceConnector
			type="icloud_calendar" label="iCloud Calendar" category="calendar_contacts"
			description="Apple calendar"
			status={getService('icloud_calendar') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('icloud_calendar', 'iCloud Calendar')}
			onDisconnect={() => disconnectService('icloud_calendar')}
		/>
	</div>

	<div class="space-y-3">
		<h4 class="text-xs font-medium uppercase text-ink-muted">Contacts</h4>
		<ServiceConnector
			type="google_contacts" label="Google Contacts" category="calendar_contacts"
			description="Address book"
			status={getService('google_contacts') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('google_contacts', 'Google Contacts')}
			onDisconnect={() => disconnectService('google_contacts')}
		/>
		<ServiceConnector
			type="icloud_contacts" label="iCloud Contacts" category="calendar_contacts"
			description="Apple address book"
			status={getService('icloud_contacts') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('icloud_contacts', 'iCloud Contacts')}
			onDisconnect={() => disconnectService('icloud_contacts')}
		/>
	</div>
</div>
