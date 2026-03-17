<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import TailscaleStep from './TailscaleStep.svelte';

	let tailscaleConnected = $derived(store.gatewayGlobal.tailscale.connected);

	function handleTailscaleComplete() {
		store.updateGlobalSettings({
			tailscale: { ...store.gatewayGlobal.tailscale, connected: true }
		});
	}
</script>

<div class="mx-auto max-w-2xl p-8">
	<h2 class="mb-6 text-2xl font-bold text-ink">Global Settings</h2>

	<!-- Tailscale -->
	<section class="mb-8">
		<TailscaleStep
			status={tailscaleConnected ? 'connected' : 'pending'}
			onComplete={handleTailscaleComplete}
		/>
	</section>
</div>
