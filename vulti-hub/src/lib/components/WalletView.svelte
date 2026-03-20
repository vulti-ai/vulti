<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { api, type Wallet, type WalletData } from '$lib/api';

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

	// Vault info from keyshare file
	let vaultInfo = $state<{ name: string; vault_id: string; file: string } | null>(null);
	let vaultAddresses = $state<Record<string, string>>({});
	let vaultLoading = $state(false);

	async function loadVault() {
		const agentId = store.activeAgentId;
		if (!agentId) return;
		vaultLoading = true;
		try {
			vaultInfo = await api.getAgentVault(agentId);
			if (vaultInfo?.vault_id) {
				try {
					const addrs = await api.vaultAddresses(vaultInfo.vault_id);
					// Flatten the addresses object to {chain: address}
					const flat: Record<string, string> = {};
					if (addrs && typeof addrs === 'object') {
						for (const [chain, val] of Object.entries(addrs)) {
							if (typeof val === 'string') flat[chain] = val;
							else if (val && typeof val === 'object' && 'address' in val) flat[chain] = (val as { address: string }).address;
						}
					}
					vaultAddresses = flat;
				} catch {
					vaultAddresses = {};
				}
			}
		} catch {
			vaultInfo = null;
		} finally {
			vaultLoading = false;
		}
	}

	async function deleteVault() {
		const agentId = store.activeAgentId;
		if (!agentId) return;
		try {
			await api.deleteAgentVault(agentId);
			vaultInfo = null;
			vaultAddresses = {};
		} catch (e: any) {
			console.error('Failed to delete vault:', e);
		}
	}

	// Vultisig fast vault creation state
	type VaultPhase = 'idle' | 'form' | 'creating' | 'verify' | 'verifying';
	let vaultPhase = $state<VaultPhase>('idle');
	let vaultError = $state('');
	let vaultName = $state('');
	let vaultEmail = $state('');
	let vaultPassword = $state('');
	let vaultCode = $state('');
	let pendingVaultId = $state('');
	let vaultFormValid = $derived(
		vaultName.trim() !== '' && vaultEmail.trim() !== '' && vaultPassword.trim().length >= 8
	);

	async function loadWallet() {
		const agentId = store.activeAgentId;
		if (!agentId) return;
		loading = true;
		try {
			const [w] = await Promise.all([
				api.getWallet(agentId),
				loadVault(),
			]);
			wallet = w;
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
		pendingVaultId = '';
		vaultPhase = 'form';
	}

	async function createFastVault() {
		if (!vaultFormValid) return;
		vaultPhase = 'creating';
		vaultError = '';

		try {
			const id = await api.createFastVault(vaultName.trim(), vaultEmail.trim(), vaultPassword.trim());
			pendingVaultId = id;
			vaultPhase = 'verify';
		} catch (e: any) {
			vaultError = e?.message || String(e) || 'Vault creation failed';
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
			const vaultId = await api.verifyFastVault(pendingVaultId, vaultCode.trim(), agentId);
			const data: WalletData = {
				crypto: { vault_id: vaultId, name: vaultName.trim(), email: vaultEmail.trim() }
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
			await api.resendVaultVerification(pendingVaultId, vaultEmail.trim(), vaultPassword.trim());
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

	// Reload when agent sends a message (vault may have been modified via chat)
	let lastMsgCount = $state(0);
	$effect(() => {
		const count = store.messages.length;
		if (count > lastMsgCount && lastMsgCount > 0) {
			loadWallet();
		}
		lastMsgCount = count;
	});
</script>

<div class="flex h-full flex-col">
	<div class="flex shrink-0 items-center justify-end border-b border-border px-6 py-2">
		<div class="flex items-center gap-1 rounded-lg border border-border p-0.5">
			<button
				class="rounded-md px-3 py-1 text-xs font-medium transition-colors {subTab === 'card' ? 'bg-primary text-white' : 'text-ink-muted hover:text-ink-dim'}"
				onclick={() => subTab = 'card'}
			>Card</button>
			<button
				class="rounded-md px-3 py-1 text-xs font-medium transition-colors {subTab === 'crypto' ? 'bg-primary text-white' : 'text-ink-muted hover:text-ink-dim'}"
				onclick={() => subTab = 'crypto'}
			>Crypto</button>
		</div>
	</div>
	<div class="flex-1 overflow-y-auto p-6">

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
						<input id="v-pass" type="text" bind:value={vaultPassword} placeholder="Vault encryption password"
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
				<div class="flex flex-col items-center justify-center py-12 text-center space-y-4">
					<svg class="animate-spin h-8 w-8 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path d="M21 12a9 9 0 1 1-6.219-8.56" stroke-linecap="round" />
					</svg>
					<p class="text-sm text-ink">Creating vault...</p>
					<p class="text-xs text-ink-muted">MPC key generation in progress. This may take a minute.</p>
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

			{:else if vaultLoading}
				<div class="flex items-center justify-center py-12">
					<svg class="animate-spin h-6 w-6 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
						<path d="M21 12a9 9 0 1 1-6.219-8.56" />
					</svg>
				</div>

			{:else if vaultInfo}
				<div class="flex items-center justify-between mb-4">
					<h3 class="text-sm font-medium uppercase text-ink-muted">Vultisig Fast Vault</h3>
					<button
						onclick={deleteVault}
						class="text-xs text-red-400/60 hover:text-red-400 transition-colors"
					>Delete Vault</button>
				</div>
				<div class="rounded-xl border border-border bg-surface p-5 space-y-3">
					<div class="flex justify-between">
						<span class="text-xs text-ink-muted">Vault</span>
						<span class="text-sm text-ink font-medium">{vaultInfo.name}</span>
					</div>
					{#if vaultInfo.vault_id}
						<div class="flex justify-between">
							<span class="text-xs text-ink-muted">Vault ID</span>
							<span class="text-sm text-ink font-mono">{truncateKey(vaultInfo.vault_id)}</span>
						</div>
					{/if}
				</div>

				{#if Object.keys(vaultAddresses).length > 0}
					<div class="mt-4">
						<h3 class="text-sm font-medium uppercase text-ink-muted mb-3">Addresses</h3>
						<div class="rounded-xl border border-border bg-surface p-5 space-y-3">
							{#each Object.entries(vaultAddresses) as [chain, address]}
								<div class="flex justify-between gap-4">
									<span class="text-xs text-ink-muted uppercase shrink-0">{chain}</span>
									<span class="text-xs text-ink font-mono truncate">{address}</span>
								</div>
							{/each}
						</div>
					</div>
				{/if}

			{:else}
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
