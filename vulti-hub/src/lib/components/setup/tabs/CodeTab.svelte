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
			category: 'code',
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
		<h3 class="text-lg font-semibold text-ink">Code</h3>
		<p class="text-sm text-ink-dim">Connect code repositories and dev tools.</p>
	</div>

	<div class="space-y-3">
		<ServiceConnector
			type="github" label="GitHub" category="code"
			description="Repos, issues, PRs (PAT or OAuth)"
			status={getService('github') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('github', 'GitHub')}
			onDisconnect={() => disconnectService('github')}
		/>
		<ServiceConnector
			type="gitlab" label="GitLab" category="code"
			description="Repos, issues, MRs (PAT)"
			status={getService('gitlab') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('gitlab', 'GitLab')}
			onDisconnect={() => disconnectService('gitlab')}
		/>
	</div>
</div>
