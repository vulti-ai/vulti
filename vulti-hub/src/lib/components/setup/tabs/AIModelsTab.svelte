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
			category: 'ai_models',
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
		<h3 class="text-lg font-semibold text-ink">AI Models</h3>
		<p class="text-sm text-ink-dim">Configure which AI models this agent uses.</p>
	</div>

	<div class="space-y-3">
		<h4 class="text-xs font-medium uppercase text-ink-muted">Language Models</h4>
		<ServiceConnector
			type="anthropic" label="Anthropic (Claude)" category="ai_models"
			description="Claude Opus, Sonnet, Haiku"
			status={getService('anthropic') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('anthropic', 'Anthropic')}
			onDisconnect={() => disconnectService('anthropic')}
		/>
		<ServiceConnector
			type="openrouter" label="OpenRouter" category="ai_models"
			description="Access multiple models via one API"
			status={getService('openrouter') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('openrouter', 'OpenRouter')}
			onDisconnect={() => disconnectService('openrouter')}
		/>
		<ServiceConnector
			type="openai" label="OpenAI (GPT)" category="ai_models"
			description="GPT-4, GPT-4o, o1"
			status={getService('openai') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('openai', 'OpenAI')}
			onDisconnect={() => disconnectService('openai')}
		/>
	</div>

	<div class="space-y-3">
		<h4 class="text-xs font-medium uppercase text-ink-muted">Image Models</h4>
		<ServiceConnector
			type="dalle" label="DALL-E" category="ai_models"
			description="OpenAI image generation"
			status={getService('dalle') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('dalle', 'DALL-E')}
			onDisconnect={() => disconnectService('dalle')}
		/>
		<ServiceConnector
			type="stable_diffusion" label="Stable Diffusion" category="ai_models"
			description="Local or API image generation"
			status={getService('stable_diffusion') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('stable_diffusion', 'Stable Diffusion')}
			onDisconnect={() => disconnectService('stable_diffusion')}
		/>
	</div>

	<div class="space-y-3">
		<h4 class="text-xs font-medium uppercase text-ink-muted">Voice</h4>
		<ServiceConnector
			type="elevenlabs" label="ElevenLabs" category="ai_models"
			description="Text-to-speech"
			status={getService('elevenlabs') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('elevenlabs', 'ElevenLabs')}
			onDisconnect={() => disconnectService('elevenlabs')}
		/>
		<ServiceConnector
			type="whisper" label="Whisper" category="ai_models"
			description="Speech-to-text"
			status={getService('whisper') ? 'connected' : 'disconnected'}
			onConnect={() => connectService('whisper', 'Whisper')}
			onDisconnect={() => disconnectService('whisper')}
		/>
	</div>
</div>
