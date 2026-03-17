<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import TailscaleStep from './TailscaleStep.svelte';
	import GatewayStep from './GatewayStep.svelte';

	let tailscaleConnected = $derived(store.gatewayGlobal.tailscale.connected);
	let gatewayConnected = $derived(store.gatewayGlobal.gateway?.connected ?? false);

	function handleGatewayComplete() {
		store.updateGlobalSettings({
			gateway: { connected: true }
		});
	}

	function handleTailscaleComplete() {
		store.updateGlobalSettings({
			tailscale: { ...store.gatewayGlobal.tailscale, connected: true }
		});
	}
</script>

<div class="mx-auto max-w-2xl space-y-8 overflow-y-auto p-8">
	<section>
		<GatewayStep
			status={gatewayConnected ? 'connected' : 'pending'}
			onComplete={handleGatewayComplete}
		/>
	</section>

	<hr class="border-border" />

	<section>
		<TailscaleStep
			status={tailscaleConnected ? 'connected' : 'pending'}
			onComplete={handleTailscaleComplete}
		/>
	</section>
</div>
