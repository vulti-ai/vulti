<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import VirtualMessages from './VirtualMessages.svelte';

	let { contextLabel = '', contextHint = '', channel = '', initialMessage = '', autoSend = false }: {
		contextLabel?: string;
		contextHint?: string;
		channel?: string;
		initialMessage?: string;
		autoSend?: boolean;
	} = $props();

	// Track which channels have already auto-sent to avoid repeating
	let autoSentChannels = $state<Set<string>>(new Set());

	let agentName = $derived(store.activeAgent?.name || 'agent');

	let input = $state('');

	// Composite key: agent + channel. When either changes, switch chat session.
	let loadedKey = $state('');

	$effect(() => {
		const ch = channel;
		const agentId = store.activeAgentId;
		const sessionsList = store.sessions; // track sessions as dependency
		if (!ch || !agentId) return;

		const sessionName = `hub:${agentId}:${ch}`;
		const existing = sessionsList.find(s => s.name === sessionName);
		const key = `${agentId}:${ch}`;
		const keyChanged = key !== loadedKey;

		if (existing) {
			if (store.activeSessionId !== existing.id) {
				store.switchSession(existing.id);
			}
		} else if (keyChanged) {
			// No session for this channel yet -- just clear messages locally.
			// Session gets created on first send.
			store.switchSession('');
		}

		if (keyChanged) {
			loadedKey = key;
			input = '';

			// Auto-send initialMessage on first visit to this channel
			if (autoSend && initialMessage && !existing && !autoSentChannels.has(key)) {
				autoSentChannels.add(key);
				// Defer to next tick so session state settles
				queueMicrotask(() => {
					input = initialMessage;
					send();
				});
			}
		}
	});

	async function send() {
		const text = input.trim();
		if (!text) return;

		const agentId = store.activeAgentId;
		const sessionName = channel && agentId ? `hub:${agentId}:${channel}` : undefined;

		// Find or create channel-specific session
		if (!store.activeSessionId || (sessionName && !store.sessions.find(s => s.id === store.activeSessionId && s.name === sessionName))) {
			const existing = sessionName ? store.sessions.find(s => s.name === sessionName) : null;
			if (existing) {
				await store.switchSession(existing.id);
			} else {
				await store.createSession(sessionName);
			}
		}

		const meta: Record<string, string> = {};
		if (channel) meta.hub_channel = channel;
		if (agentId) meta.agent_id = agentId;
		store.sendMessage(text, Object.keys(meta).length ? meta : undefined);
		input = '';
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			send();
		}
	}
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="flex h-full flex-col">
	<!-- Messages -->
	{#if store.messages.length === 0 && initialMessage}
		<div class="flex-1 overflow-y-auto p-3">
			<div class="space-y-3">
				<div class="flex gap-2">
					{#if store.activeAgentId && store.avatarCache[store.activeAgentId]}
						<img class="h-7 w-7 shrink-0 rounded-lg object-cover" src={store.avatarCache[store.activeAgentId]} alt={agentName} />
					{:else}
						<div class="vulti-avatar flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs font-bold">{store.activeAgent?.avatar || agentName.charAt(0)}</div>
					{/if}
					<div class="max-w-[85%] rounded-xl bg-surface px-3 py-2 text-sm text-ink whitespace-pre-line">
						{initialMessage}
					</div>
				</div>
			</div>
		</div>
	{:else if store.messages.length === 0}
		<div class="flex-1 overflow-y-auto p-3">
			<div class="flex h-full flex-col items-center justify-center text-center px-4">
				{#if contextHint}
					<p class="max-w-xs text-sm font-medium text-ink-dim">Ask {agentName} anything</p>
					<p class="mt-1 max-w-xs text-xs text-ink-muted">{contextHint}</p>
				{:else}
					<p class="max-w-xs text-sm text-ink-muted">Ask {agentName} anything</p>
				{/if}
			</div>
		</div>
	{:else}
		<VirtualMessages
			messages={store.messages}
			activeAgent={store.activeAgent}
			{agentName}
			streamingContent={store.streamingContent}
			isStreaming={store.isStreaming}
			isTyping={store.isTyping}
			avatarUri={store.activeAgentId ? store.avatarCache[store.activeAgentId] : undefined}
		/>
	{/if}

	<!-- Input -->
	<div class="shrink-0 border-t border-border p-3">
		<div class="flex gap-2">
			<textarea
				bind:value={input}
				onkeydown={handleKeydown}
				placeholder="Message {agentName}..."
				rows="1"
				class="flex-1 resize-none rounded-xl border border-border bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-primary focus:outline-none"
			></textarea>
			<button
				onclick={send}
				disabled={!input.trim()}
				class="shrink-0 rounded-xl bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-hover disabled:opacity-40"
			>
				Send
			</button>
		</div>
	</div>
</div>

<style>
	.vulti-avatar {
		background: linear-gradient(135deg, #E8607A, #F0A84A, #4AC6B7, #6B8BEB, #9D7AEA);
		background-size: 200% 200%;
		color: white;
	}
</style>
