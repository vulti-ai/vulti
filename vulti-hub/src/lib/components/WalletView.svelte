<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { api, type Wallet, type WalletData } from '$lib/api';
	import { Vultisig } from '@vultisig/sdk';

	let wallet = $state<Wallet>({ creditCard: undefined, crypto: undefined });
	let loading = $state(true);
	let subTab = $state<'card' | 'crypto'>('card');

	// Credit card edit state
	let editingCard = $state(false);
	let savingCard = $state(false);
	let cardError = $state('');
	let cardName = $state('');
	let cardNumber = $state('');
	let cardExpiry = $state('');
	let cardCode = $state('');
	let cardValid = $derived(
		cardName.trim() !== '' && cardNumber.trim() !== '' && cardExpiry.trim() !== '' && cardCode.trim() !== ''
	);

	// Vultisig fast vault state
	type VaultPhase = 'idle' | 'form' | 'creating' | 'verify' | 'verifying';
	let vaultPhase = $state<VaultPhase>('idle');
	let vaultError = $state('');
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

	async function loadWallet() {
		const agentId = store.activeAgentId;
		if (!agentId) return;
		loading = true;
		try {
			wallet = await api.getWallet(agentId);
		} catch {
			wallet = { creditCard: undefined, crypto: undefined };
		} finally {
			loading = false;
		}
	}

	function startEditCard() {
		cardName = wallet.creditCard?.name || '';
		cardNumber = wallet.creditCard?.number || '';
		cardExpiry = wallet.creditCard?.expiry || '';
		cardCode = wallet.creditCard?.code || '';
		editingCard = true;
	}

	async function saveCard() {
		const agentId = store.activeAgentId;
		if (!agentId || !cardValid) return;
		savingCard = true;
		cardError = '';
		try {
			const data: WalletData = {
				credit_card: { name: cardName.trim(), number: cardNumber.trim(), expiry: cardExpiry.trim(), code: cardCode.trim() }
			};
			wallet = await api.saveWallet(agentId, data);
			editingCard = false;
		} catch (e: any) {
			cardError = e?.message || 'Failed to save';
		} finally {
			savingCard = false;
		}
	}

	function startCreateVault() {
		vaultName = (store.activeAgent?.name || 'Agent') + ' Vault';
		vaultEmail = '';
		vaultPassword = '';
		vaultCode = '';
		vaultError = '';
		vaultProgress = '';
		pendingVaultId = '';
		vaultPhase = 'form';
	}

	async function createFastVault() {
		if (!vaultFormValid) return;
		vaultPhase = 'creating';
		vaultError = '';
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
			vaultError = e?.message || 'Vault creation failed';
			vaultPhase = 'form';
		}
	}

	async function verifyVault() {
		if (!vaultCode.trim() || !pendingVaultId) return;
		const agentId = store.activeAgentId;
		if (!agentId) return;
		vaultPhase = 'verifying';
		vaultError = '';

		try {
			const vSdk = await getSDK();
			await vSdk.verifyVault(pendingVaultId, vaultCode.trim());

			// Save vault reference to agent's wallet.json
			const data: WalletData = {
				crypto: { vault_id: pendingVaultId, name: vaultName.trim(), email: vaultEmail.trim() }
			};
			wallet = await api.saveWallet(agentId, data);
			vaultPhase = 'idle';
		} catch (e: any) {
			vaultError = e?.message || 'Verification failed';
			vaultPhase = 'verify';
		}
	}

	async function resendCode() {
		if (!pendingVaultId) return;
		vaultError = '';
		try {
			const vSdk = await getSDK();
			await vSdk.resendVaultVerification({
				vaultId: pendingVaultId,
				email: vaultEmail.trim(),
				password: vaultPassword.trim(),
			});
		} catch (e: any) {
			vaultError = e?.message || 'Failed to resend code';
		}
	}

	function maskCard(num: string): string {
		if (num.length <= 4) return num;
		return '*'.repeat(num.length - 4) + num.slice(-4);
	}

	function truncateKey(key: string): string {
		if (key.length <= 16) return key;
		return key.slice(0, 8) + '...' + key.slice(-8);
	}

	$effect(() => {
		store.activeAgentId;
		loadWallet();
	});
</script>

<div class="h-full overflow-y-auto">
	<div class="mx-auto max-w-4xl p-6">

		<!-- Sub-tabs -->
		<div class="flex border-b border-ink/5 mb-6">
			<button
				class="flex-1 py-2 text-xs font-medium transition-colors {subTab === 'card' ? 'border-b-2 border-primary text-primary' : 'text-ink-muted hover:text-ink-dim'}"
				onclick={() => subTab = 'card'}
			>Credit Card</button>
			<button
				class="flex-1 py-2 text-xs font-medium transition-colors {subTab === 'crypto' ? 'border-b-2 border-primary text-primary' : 'text-ink-muted hover:text-ink-dim'}"
				onclick={() => subTab = 'crypto'}
			>Crypto Vault</button>
		</div>

		{#if loading}
			<p class="text-sm text-ink-muted">Loading...</p>

		{:else if subTab === 'card'}
			<!-- Credit Card -->
			{#if editingCard}
				<div class="space-y-4">
					<div>
						<label for="w-name" class="block text-xs font-medium text-ink-muted mb-1">Name on card</label>
						<input id="w-name" type="text" bind:value={cardName} placeholder="J. Smith"
							class="w-full rounded-lg border border-border bg-canvas px-3 py-2 text-sm text-ink placeholder:text-ink-muted/50 focus:border-primary focus:outline-none" />
					</div>
					<div>
						<label for="w-number" class="block text-xs font-medium text-ink-muted mb-1">Card number</label>
						<input id="w-number" type="text" bind:value={cardNumber} placeholder="4242 4242 4242 4242" maxlength="19"
							class="w-full rounded-lg border border-border bg-canvas px-3 py-2 text-sm text-ink placeholder:text-ink-muted/50 focus:border-primary focus:outline-none font-mono" />
					</div>
					<div class="flex gap-3">
						<div class="flex-1">
							<label for="w-expiry" class="block text-xs font-medium text-ink-muted mb-1">Expiry</label>
							<input id="w-expiry" type="text" bind:value={cardExpiry} placeholder="MM/YY" maxlength="5"
								class="w-full rounded-lg border border-border bg-canvas px-3 py-2 text-sm text-ink placeholder:text-ink-muted/50 focus:border-primary focus:outline-none font-mono" />
						</div>
						<div class="flex-1">
							<label for="w-code" class="block text-xs font-medium text-ink-muted mb-1">Security code</label>
							<input id="w-code" type="text" bind:value={cardCode} placeholder="123" maxlength="4"
								class="w-full rounded-lg border border-border bg-canvas px-3 py-2 text-sm text-ink placeholder:text-ink-muted/50 focus:border-primary focus:outline-none font-mono" />
						</div>
					</div>
					{#if cardError}
						<p class="text-xs text-red-500">{cardError}</p>
					{/if}
					<div class="flex gap-2">
						<button onclick={saveCard} disabled={!cardValid || savingCard}
							class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed">
							{savingCard ? 'Saving...' : 'Save'}
						</button>
						<button onclick={() => editingCard = false} class="rounded-lg px-4 py-2 text-sm text-ink-muted hover:text-ink">Cancel</button>
					</div>
				</div>
			{:else if wallet.creditCard}
				<div class="flex items-center justify-between mb-4">
					<h3 class="text-sm font-medium uppercase text-ink-muted">Credit Card</h3>
					<button onclick={startEditCard} class="text-xs text-primary hover:text-primary-hover">Edit</button>
				</div>
				<div class="rounded-xl border border-border bg-surface p-5 space-y-3">
					<div class="flex justify-between">
						<span class="text-xs text-ink-muted">Name</span>
						<span class="text-sm text-ink font-medium">{wallet.creditCard.name}</span>
					</div>
					<div class="flex justify-between">
						<span class="text-xs text-ink-muted">Number</span>
						<span class="text-sm text-ink font-mono">{maskCard(wallet.creditCard.number)}</span>
					</div>
					<div class="flex justify-between">
						<span class="text-xs text-ink-muted">Expiry</span>
						<span class="text-sm text-ink font-mono">{wallet.creditCard.expiry}</span>
					</div>
					<div class="flex justify-between">
						<span class="text-xs text-ink-muted">Code</span>
						<span class="text-sm text-ink font-mono">***</span>
					</div>
				</div>
			{:else}
				<div class="flex flex-col items-center justify-center py-12 text-center">
					<p class="text-sm text-ink-muted mb-4">No credit card configured.</p>
					<button onclick={startEditCard}
						class="rounded-lg bg-primary px-5 py-2 text-sm font-medium text-white hover:bg-primary-hover">
						Add Credit Card
					</button>
				</div>
			{/if}

		{:else}
			<!-- Crypto Vault (Vultisig Fast Vault) -->
			{#if vaultPhase === 'form'}
				<!-- Step 1: Enter email + password -->
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
					{#if vaultError}
						<p class="text-xs text-red-500">{vaultError}</p>
					{/if}
					<div class="flex gap-2">
						<button onclick={createFastVault} disabled={!vaultFormValid}
							class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed">
							Create Vault
						</button>
						<button onclick={() => vaultPhase = 'idle'} class="rounded-lg px-4 py-2 text-sm text-ink-muted hover:text-ink">Cancel</button>
					</div>
				</div>

			{:else if vaultPhase === 'creating'}
				<!-- Step 2: MPC keygen in progress -->
				<div class="flex flex-col items-center justify-center py-12 text-center space-y-4">
					<svg class="animate-spin h-8 w-8 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path d="M21 12a9 9 0 1 1-6.219-8.56" stroke-linecap="round" />
					</svg>
					<p class="text-sm text-ink">{vaultProgress}</p>
					<p class="text-xs text-ink-muted">This may take a moment. MPC key generation is in progress.</p>
				</div>

			{:else if vaultPhase === 'verify' || vaultPhase === 'verifying'}
				<!-- Step 3: Enter verification code -->
				<div class="space-y-4">
					<div class="rounded-lg bg-surface p-4 text-center">
						<p class="text-sm text-ink">A verification code was sent to <strong>{vaultEmail}</strong></p>
					</div>
					<div>
						<label for="v-code" class="block text-xs font-medium text-ink-muted mb-1">Verification code</label>
						<input id="v-code" type="text" bind:value={vaultCode} placeholder="123456" maxlength="6"
							class="w-full rounded-lg border border-border bg-canvas px-3 py-2.5 text-center text-lg text-ink placeholder:text-ink-muted/50 focus:border-primary focus:outline-none font-mono tracking-widest" />
					</div>
					{#if vaultError}
						<p class="text-xs text-red-500">{vaultError}</p>
					{/if}
					<div class="flex gap-2">
						<button onclick={verifyVault} disabled={!vaultCode.trim() || vaultPhase === 'verifying'}
							class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed">
							{vaultPhase === 'verifying' ? 'Verifying...' : 'Verify'}
						</button>
						<button onclick={resendCode} disabled={vaultPhase === 'verifying'}
							class="rounded-lg px-4 py-2 text-sm text-ink-muted hover:text-ink disabled:opacity-50">
							Resend code
						</button>
					</div>
				</div>

			{:else if wallet.crypto}
				<!-- Display existing vault -->
				<div class="flex items-center justify-between mb-4">
					<h3 class="text-sm font-medium uppercase text-ink-muted">Vultisig Fast Vault</h3>
				</div>
				<div class="rounded-xl border border-border bg-surface p-5 space-y-3">
					<div class="flex justify-between">
						<span class="text-xs text-ink-muted">Vault</span>
						<span class="text-sm text-ink font-medium">{wallet.crypto.name}</span>
					</div>
					<div class="flex justify-between">
						<span class="text-xs text-ink-muted">Email</span>
						<span class="text-sm text-ink">{wallet.crypto.email}</span>
					</div>
					<div class="flex justify-between">
						<span class="text-xs text-ink-muted">Vault ID</span>
						<span class="text-sm text-ink font-mono">{truncateKey(wallet.crypto.vaultId)}</span>
					</div>
				</div>

			{:else}
				<!-- No vault — prompt to create -->
				<div class="flex flex-col items-center justify-center py-12 text-center">
					<p class="text-sm text-ink-muted mb-1">No crypto vault configured.</p>
					<p class="text-xs text-ink-faint mb-4">Create a Vultisig fast vault for this agent.</p>
					<button onclick={startCreateVault}
						class="rounded-lg bg-primary px-5 py-2 text-sm font-medium text-white hover:bg-primary-hover">
						Create Fast Vault
					</button>
				</div>
			{/if}
		{/if}

	</div>
</div>
