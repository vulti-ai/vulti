<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { api } from '$lib/api';
	import { onMount } from 'svelte';

	let name = $state(store.owner.name);
	let about = $state(store.owner.about || '');
	let saving = $state(false);

	// Load integrations on mount so matrix details are available
	onMount(() => {
		store.loadIntegrations();
	});

	// Matrix
	let matrixIntegration = $derived(store.integrations.find(i => i.id === 'matrix'));
	let hasOwnerAccount = $derived(!!matrixIntegration?.details?.owner_username);
	let matrixAvailable = $derived(!!matrixIntegration);

	let matrixPassword = $state('');
	let matrixError = $state('');

	let isDirty = $derived(
		name !== store.owner.name
		|| about !== (store.owner.about || '')
	);

	async function save() {
		saving = true;
		try {
			await store.updateOwner(name, undefined, about || undefined);
		} catch (e: any) {
			matrixError = e.message || 'Save failed';
		} finally {
			saving = false;
		}
	}

	async function createMatrixAccount() {
		if (!matrixPassword.trim()) return;
		saving = true;
		matrixError = '';
		try {
			const username = name.trim().toLowerCase().replace(/[^a-z0-9]/g, '');
			await api.registerMatrixOwner(username, matrixPassword.trim(), name.trim());
			await store.loadIntegrations();
			matrixPassword = '';
		} catch (e: any) {
			// If account already exists, just reload integrations to show the details
			if (e.message?.includes('409') || e.message?.includes('already exists')) {
				await store.loadIntegrations();
				matrixPassword = '';
			} else {
				matrixError = e.message || 'Registration failed';
			}
		} finally {
			saving = false;
		}
	}
</script>

<div class="space-y-6 p-4">
	<!-- Identity -->
	<div class="space-y-3">
		<label class="block text-sm font-medium text-ink/60">Name</label>
		<input
			type="text"
			bind:value={name}
			class="w-full rounded-lg border border-ink/10 bg-paper px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none"
			placeholder="Your name"
			onkeydown={(e) => e.key === 'Enter' && save()}
		/>
	</div>

	<div class="space-y-3">
		<label class="block text-sm font-medium text-ink/60">About You</label>
		<textarea
			bind:value={about}
			placeholder="Tell your agents about yourself — background, preferences, how you like to work..."
			rows={3}
			class="w-full rounded-lg border border-ink/10 bg-paper px-3 py-2 text-sm text-ink placeholder:text-ink/30 focus:border-primary focus:outline-none resize-none"
		></textarea>
		<p class="text-xs text-ink/40">All agents will know this about you by default.</p>
	</div>

	<button
		class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
		disabled={saving || !isDirty}
		onclick={save}
	>
		{saving ? 'Saving...' : 'Save'}
	</button>

	<!-- Matrix Connection -->
	{#if matrixAvailable}
		<hr class="border-ink/10" />

		<div class="space-y-3">
			<h3 class="text-sm font-semibold text-ink">Matrix Connection</h3>
			<p class="text-xs text-ink/50">Chat with your agents from any device using Element X.</p>

			{#if hasOwnerAccount && matrixIntegration?.details}
				<!-- Connected — show login steps -->
				<div class="rounded-lg border border-green-500/20 bg-green-500/5 p-3 space-y-3">
					<div class="flex items-center gap-2">
						<span class="h-2 w-2 rounded-full bg-green-500"></span>
						<p class="text-sm font-medium text-ink">Account created</p>
					</div>

					<p class="text-xs font-medium text-ink/60">Connect from your phone or desktop:</p>
					<ol class="text-xs text-ink/50 space-y-1 list-decimal list-inside">
						<li>Download <strong class="text-ink/70">Element X</strong> from the App Store or Play Store</li>
						<li>Tap <strong class="text-ink/70">"I already have an account"</strong></li>
						<li>Enter <strong class="text-ink/70">"Other"</strong> for the server, then type the address below</li>
						<li>Sign in with your username and password</li>
					</ol>

					<div class="grid grid-cols-[5rem_1fr] gap-y-2 text-sm mt-2">
						<span class="text-ink/40">Server</span>
						<code class="text-ink font-mono select-all break-all">{matrixIntegration.details.homeserver_url}</code>
						<span class="text-ink/40">Username</span>
						<code class="text-ink font-mono select-all">{matrixIntegration.details.owner_username}</code>
						<span class="text-ink/40">Password</span>
						<code class="text-ink font-mono select-all">{matrixIntegration.details.owner_password}</code>
					</div>
				</div>
			{:else}
				<!-- Not connected — registration form -->
				<div class="rounded-lg border border-ink/10 bg-paper/50 p-3 space-y-3">
					<p class="text-xs text-ink/50">Create your Matrix account to message agents from Element X on any device.</p>
					<div class="space-y-2">
						<label class="block text-xs font-medium text-ink/50">Choose a password</label>
						<input
							type="text"
							bind:value={matrixPassword}
							placeholder="Password for your Matrix account"
							class="w-full rounded-lg border border-ink/10 bg-paper px-3 py-2 text-sm text-ink placeholder:text-ink/30 focus:border-primary focus:outline-none"
							onkeydown={(e) => { if (e.key === 'Enter') createMatrixAccount(); }}
						/>
					</div>
					<button
						class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
						disabled={saving || !matrixPassword.trim()}
						onclick={createMatrixAccount}
					>
						{saving ? 'Creating...' : 'Create Account'}
					</button>
				</div>
			{/if}
		</div>
	{/if}

	{#if matrixError}
		<p class="text-xs text-red-400">{matrixError}</p>
	{/if}
</div>
