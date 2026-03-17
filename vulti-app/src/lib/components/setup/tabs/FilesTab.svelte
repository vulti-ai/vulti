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
			category: 'files',
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
		<h3 class="text-lg font-semibold text-ink">File Systems</h3>
		<p class="text-sm text-ink-dim">Give this agent access to cloud drives and local folders.</p>
	</div>

	<div class="space-y-3">
		<ServiceConnector
			type="google_drive" label="Google Drive" category="files"
			description="Cloud storage (OAuth)"
			status={getService('google_drive') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('google_drive', 'Google Drive')}
			onDisconnect={() => disconnectService('google_drive')}
		/>
		<ServiceConnector
			type="icloud_drive" label="iCloud Drive" category="files"
			description="Apple cloud storage"
			status={getService('icloud_drive') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('icloud_drive', 'iCloud Drive')}
			onDisconnect={() => disconnectService('icloud_drive')}
		/>
		<ServiceConnector
			type="dropbox" label="Dropbox" category="files"
			description="Cloud storage (OAuth)"
			status={getService('dropbox') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('dropbox', 'Dropbox')}
			onDisconnect={() => disconnectService('dropbox')}
		/>
		<ServiceConnector
			type="proton_drive" label="Proton Drive" category="files"
			description="Encrypted cloud storage"
			status={getService('proton_drive') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('proton_drive', 'Proton Drive')}
			onDisconnect={() => disconnectService('proton_drive')}
		/>
		<ServiceConnector
			type="local_folder" label="Local Folders" category="files"
			description="Folders on this Mac"
			status={getService('local_folder') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('local_folder', 'Local Folders')}
			onDisconnect={() => disconnectService('local_folder')}
		/>
	</div>
</div>
