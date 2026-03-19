<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { api } from '$lib/api';
	import ChatView from './ChatView.svelte';
	import WalletStep from './setup/WalletStep.svelte';

	let { onclose }: { onclose: () => void } = $props();

	let step = $state<1 | 2 | 3 | 4 | 5>(1);

	const steps = [
		{ num: 1, label: 'Role' },
		{ num: 2, label: 'Connections' },
		{ num: 3, label: 'Skills' },
		{ num: 4, label: 'Actions' },
		{ num: 5, label: 'Wallet' },
	] as const;

	const stepConfig: Record<1 | 2 | 3 | 4, { channel: string; label: string; initialMessage: string }> = {
		1: {
			channel: 'onboard-role',
			label: 'Role & Understanding',
			initialMessage: "What's my role and what should I know about you and my job?",
		},
		2: {
			channel: 'onboard-connections',
			label: 'Connections',
			initialMessage: "What services do you want me to connect to? Based on my role, I can suggest what I'll need.",
		},
		3: {
			channel: 'onboard-skills',
			label: 'Skills',
			initialMessage: "What skills do you want me to have? Based on my role, here's what I'd suggest — let me check what's available and recommend the best ones for my job.",
		},
		4: {
			channel: 'onboard-actions',
			label: 'Actions',
			initialMessage: "What do you want me to do each day, or what actions should I take when I see something?",
		},
	};

	async function finalizeAndReload() {
		const agentId = store.activeAgentId;
		if (!agentId) return;
		try {
			await api.finalizeOnboarding(agentId);
			await store.loadAgents();
			store.loadMemories();
			store.loadSoul();
		} catch {}
	}

	function generateAvatarInBackground() {
		const agentId = store.activeAgentId;
		if (!agentId) return;
		// Fire and forget — don't block onboarding completion
		api.generateAgentAvatar(agentId)
			.then(() => store.loadAgents())
			.catch(() => {}); // Silently skip if image gen unavailable
	}

	async function advance() {
		if (step === 1) {
			await finalizeAndReload();
		}

		if (step === 5) {
			await finalizeAndReload();
			generateAvatarInBackground();
			onclose();
		} else {
			step = (step + 1) as 2 | 3 | 4 | 5;
		}
	}

	async function skip() {
		if (step === 5) {
			await finalizeAndReload();
			generateAvatarInBackground();
			onclose();
		} else {
			step = (step + 1) as 2 | 3 | 4 | 5;
		}
	}

	function handleWalletSaved() {
		generateAvatarInBackground();
		finalizeAndReload().then(() => onclose());
	}

	let agentName = $derived(store.activeAgent?.name || 'Agent');

	// Show "Next" only after agent has replied (at least one assistant message, not still responding)
	// For step 5 (wallet form), no need to wait for chat
	let agentReady = $derived(
		step === 5 ||
		(store.messages.some((m: { role: string }) => m.role === 'assistant')
		&& !store.isTyping
		&& !store.isStreaming)
	);
</script>

<div class="flex h-full flex-col">
	<!-- Step indicator -->
	<div class="flex shrink-0 items-center gap-1 border-b border-border px-6 py-3">
		<!-- Completed "Create" checkmark -->
		<div class="flex items-center gap-2">
			<span class="flex h-6 w-6 items-center justify-center rounded-full bg-primary/20 text-primary text-xs font-medium">
				<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
					<path d="M20 6 9 17l-5-5" />
				</svg>
			</span>
			<span class="text-xs font-medium text-ink-muted">{agentName}</span>
		</div>

		{#each steps as s, i}
			<div class="mx-1 h-px w-6 {step > s.num ? 'bg-primary' : step === s.num ? 'bg-primary/50' : 'bg-border'}"></div>
			<div class="flex items-center gap-2">
				<span
					class="flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium transition-colors
						{step === s.num ? 'bg-primary text-white' : step > s.num ? 'bg-primary/20 text-primary' : 'bg-surface text-ink-muted'}"
				>
					{#if step > s.num}
						<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
							<path d="M20 6 9 17l-5-5" />
						</svg>
					{:else}
						{s.num}
					{/if}
				</span>
				<span class="text-xs font-medium {step === s.num ? 'text-ink' : 'text-ink-muted'}">{s.label}</span>
			</div>
		{/each}

		<!-- Skip link -->
		<button onclick={skip} class="ml-auto text-xs text-ink-muted hover:text-ink">Skip</button>
	</div>

	<!-- Chat content (steps 1-4) or Wallet form (step 5) -->
	<div class="flex flex-1 flex-col overflow-hidden">
		<div class="flex-1 overflow-hidden">
			{#if step <= 4}
				{@const cfg = stepConfig[step as 1 | 2 | 3 | 4]}
				<ChatView
					channel={cfg.channel}
					contextLabel={cfg.label}
					initialMessage={cfg.initialMessage}
					autoSend={true}
				/>
			{:else}
				<WalletStep onsave={handleWalletSaved} />
			{/if}
		</div>

		<!-- Footer -->
		<div class="flex shrink-0 items-center justify-between border-t border-border px-6 py-3">
			<span class="text-xs text-ink-muted">
				Step {step} of 5
			</span>
			{#if agentReady && step <= 4}
				<button
					onclick={advance}
					class="rounded-lg bg-primary px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-hover"
				>
					Next
				</button>
			{/if}
		</div>
	</div>
</div>
