<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { api, type WalletData } from '$lib/api';
	import { Vultisig } from '@vultisig/sdk';

	let { onsave }: { onsave: () => void } = $props();

	let walletType = $state<'credit_card' | 'crypto'>('credit_card');
	let saving = $state(false);
	let error = $state('');

	// Credit card fields
	let cardName = $state('');
	let cardNumber = $state('');
	let cardExpiry = $state('');
	let cardCode = $state('');
	let cardValid = $derived(
		cardName.trim() !== '' && cardNumber.trim() !== '' && cardExpiry.trim() !== '' && cardCode.trim() !== ''
	);

	// Vultisig fast vault fields
	type VaultPhase = 'form' | 'creating' | 'verify' | 'verifying';
	let vaultPhase = $state<VaultPhase>('form');
	let vaultName = $state('');
	let vaultEmail = $state('');
	let vaultPassword = $state('');
	let vaultCode = $state('');
	let vaultProgress = $state('');
	let pendingVaultId = $state('');
	let vaultFormValid = $derived(
		vaultName.trim() !== '' && vaultEmail.trim() !== '' && vaultPassword.trim().length >= 8
	);

	let sdk: Vultisig | null = null;

	async function getSDK(): Promise<Vultisig> {
		if (!sdk) {
			sdk = new Vultisig();
			await sdk.initialize();
		}
		return sdk;
	}

	// Set default vault name from agent name
	$effect(() => {
		if (!vaultName) {
			vaultName = (store.activeAgent?.name || 'Agent') + ' Vault';
		}
	});

	async function saveCard() {
		const agentId = store.activeAgentId;
		if (!agentId || !cardValid) return;
		saving = true;
		error = '';
		try {
			const data: WalletData = {
				credit_card: { name: cardName.trim(), number: cardNumber.trim(), expiry: cardExpiry.trim(), code: cardCode.trim() }
			};
			await api.saveWallet(agentId, data);
			onsave();
		} catch (e: any) {
			error = e?.message || 'Failed to save';
		} finally {
			saving = false;
		}
	}

	async function createFastVault() {
		if (!vaultFormValid) return;
		vaultPhase = 'creating';
		error = '';
		vaultProgress = 'Initializing...';

		try {
			const vSdk = await getSDK();
			const vaultId = await vSdk.createFastVault({
				name: vaultName.trim(),
				email: vaultEmail.trim(),
				password: vaultPassword.trim(),
				onProgress: (step: { message: string }) => {
					vaultProgress = step.message;
				},
			});
			pendingVaultId = vaultId;
			vaultPhase = 'verify';
		} catch (e: any) {
			error = e?.message || 'Vault creation failed';
			vaultPhase = 'form';
		}
	}

	async function verifyVault() {
		if (!vaultCode.trim() || !pendingVaultId) return;
		const agentId = store.activeAgentId;
		if (!agentId) return;
		vaultPhase = 'verifying';
		error = '';

		try {
			const vSdk = await getSDK();
			await vSdk.verifyVault(pendingVaultId, vaultCode.trim());

			const data: WalletData = {
				crypto: { vault_id: pendingVaultId, name: vaultName.trim(), email: vaultEmail.trim() }
			};
			await api.saveWallet(agentId, data);
			onsave();
		} catch (e: any) {
			error = e?.message || 'Verification failed';
			vaultPhase = 'verify';
		}
	}

	async function resendCode() {
		error = '';
		try {
			const vSdk = await getSDK();
			await vSdk.resendVaultVerification({
				vaultId: pendingVaultId,
				email: vaultEmail.trim(),
				password: vaultPassword.trim(),
			});
		} catch (e: any) {
			error = e?.message || 'Failed to resend code';
		}
	}
</script>

<div class="flex h-full flex-col items-center justify-center p-8">
	<div class="w-full max-w-md space-y-6">
		<div class="text-center">
			<h2 class="text-lg font-semibold text-ink">Agent Wallet</h2>
			<p class="mt-1 text-sm text-ink-muted">Give this agent a payment method for autonomous spending.</p>
		</div>

		<!-- Wallet type selector -->
		<div class="flex gap-2 rounded-lg bg-surface p-1">
			<button
				onclick={() => walletType = 'credit_card'}
				class="flex-1 rounded-md px-3 py-2 text-sm font-medium transition-colors
					{walletType === 'credit_card' ? 'bg-canvas text-ink shadow-sm' : 'text-ink-muted hover:text-ink'}"
			>Credit Card</button>
			<button
				onclick={() => walletType = 'crypto'}
				class="flex-1 rounded-md px-3 py-2 text-sm font-medium transition-colors
					{walletType === 'crypto' ? 'bg-canvas text-ink shadow-sm' : 'text-ink-muted hover:text-ink'}"
			>Crypto Vault</button>
		</div>

		<!-- Credit card form -->
		{#if walletType === 'credit_card'}
			<div class="space-y-4">
				<div>
					<label for="card-name" class="block text-xs font-medium text-ink-muted mb-1">Name on card</label>
					<input id="card-name" type="text" bind:value={cardName} placeholder="J. Smith"
						class="w-full rounded-lg border border-border bg-canvas px-3 py-2 text-sm text-ink placeholder:text-ink-muted/50 focus:border-primary focus:outline-none" />
				</div>
				<div>
					<label for="card-number" class="block text-xs font-medium text-ink-muted mb-1">Card number</label>
					<input id="card-number" type="text" bind:value={cardNumber} placeholder="4242 4242 4242 4242" maxlength="19"
						class="w-full rounded-lg border border-border bg-canvas px-3 py-2 text-sm text-ink placeholder:text-ink-muted/50 focus:border-primary focus:outline-none font-mono" />
				</div>
				<div class="flex gap-3">
					<div class="flex-1">
						<label for="card-expiry" class="block text-xs font-medium text-ink-muted mb-1">Expiry</label>
						<input id="card-expiry" type="text" bind:value={cardExpiry} placeholder="MM/YY" maxlength="5"
							class="w-full rounded-lg border border-border bg-canvas px-3 py-2 text-sm text-ink placeholder:text-ink-muted/50 focus:border-primary focus:outline-none font-mono" />
					</div>
					<div class="flex-1">
						<label for="card-code" class="block text-xs font-medium text-ink-muted mb-1">Security code</label>
						<input id="card-code" type="text" bind:value={cardCode} placeholder="123" maxlength="4"
							class="w-full rounded-lg border border-border bg-canvas px-3 py-2 text-sm text-ink placeholder:text-ink-muted/50 focus:border-primary focus:outline-none font-mono" />
					</div>
				</div>
			</div>

			{#if error}
				<p class="text-xs text-red-500">{error}</p>
			{/if}

			<button onclick={saveCard} disabled={!cardValid || saving}
				class="w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed">
				{saving ? 'Saving...' : 'Save Credit Card'}
			</button>

		<!-- Vultisig Fast Vault -->
		{:else if vaultPhase === 'form'}
			<div class="space-y-4">
				<div>
					<label for="v-name" class="block text-xs font-medium text-ink-muted mb-1">Vault name</label>
					<input id="v-name" type="text" bind:value={vaultName}
						class="w-full rounded-lg border border-border bg-canvas px-3 py-2 text-sm text-ink placeholder:text-ink-muted/50 focus:border-primary focus:outline-none" />
				</div>
				<div>
					<label for="v-email" class="block text-xs font-medium text-ink-muted mb-1">Email</label>
					<input id="v-email" type="email" bind:value={vaultEmail} placeholder="agent@example.com"
						class="w-full rounded-lg border border-border bg-canvas px-3 py-2 text-sm text-ink placeholder:text-ink-muted/50 focus:border-primary focus:outline-none" />
				</div>
				<div>
					<label for="v-pass" class="block text-xs font-medium text-ink-muted mb-1">Password (min 8 characters)</label>
					<input id="v-pass" type="password" bind:value={vaultPassword} placeholder="Vault encryption password"
						class="w-full rounded-lg border border-border bg-canvas px-3 py-2 text-sm text-ink placeholder:text-ink-muted/50 focus:border-primary focus:outline-none" />
				</div>
			</div>

			{#if error}
				<p class="text-xs text-red-500">{error}</p>
			{/if}

			<button onclick={createFastVault} disabled={!vaultFormValid}
				class="w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed">
				Create Fast Vault
			</button>

		{:else if vaultPhase === 'creating'}
			<div class="flex flex-col items-center justify-center py-8 text-center space-y-4">
				<svg class="animate-spin h-8 w-8 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<path d="M21 12a9 9 0 1 1-6.219-8.56" stroke-linecap="round" />
				</svg>
				<p class="text-sm text-ink">{vaultProgress}</p>
				<p class="text-xs text-ink-muted">MPC key generation in progress.</p>
			</div>

		{:else if vaultPhase === 'verify' || vaultPhase === 'verifying'}
			<div class="space-y-4">
				<div class="rounded-lg bg-surface p-4 text-center">
					<p class="text-sm text-ink">A verification code was sent to <strong>{vaultEmail}</strong></p>
				</div>
				<div>
					<label for="v-code" class="block text-xs font-medium text-ink-muted mb-1">Verification code</label>
					<input id="v-code" type="text" bind:value={vaultCode} placeholder="123456" maxlength="6"
						class="w-full rounded-lg border border-border bg-canvas px-3 py-2.5 text-center text-lg text-ink placeholder:text-ink-muted/50 focus:border-primary focus:outline-none font-mono tracking-widest" />
				</div>
				{#if error}
					<p class="text-xs text-red-500">{error}</p>
				{/if}
				<button onclick={verifyVault} disabled={!vaultCode.trim() || vaultPhase === 'verifying'}
					class="w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed">
					{vaultPhase === 'verifying' ? 'Verifying...' : 'Verify & Save'}
				</button>
				<button onclick={resendCode} disabled={vaultPhase === 'verifying'}
					class="w-full text-center text-xs text-ink-muted hover:text-ink disabled:opacity-50">
					Resend code
				</button>
			</div>
		{/if}
	</div>
</div>
