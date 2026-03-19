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
	<!-- Header -->
	<header class="flex h-10 shrink-0 items-center border-b border-border px-4">
		<div class="flex items-center gap-2">
			<svg class="h-3.5 w-3.5 text-ink-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
				<path stroke-linecap="round" stroke-linejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
			</svg>
			<span class="text-xs font-medium text-ink-muted">{contextLabel || agentName}</span>
		</div>
	</header>

	<!-- Messages -->
	{#if store.messages.length === 0 && initialMessage}
		<div class="flex-1 overflow-y-auto p-3">
			<div class="space-y-3">
				<div class="flex gap-2">
					<div class="vulti-avatar flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs font-bold">{store.activeAgent?.avatar || agentName.charAt(0)}</div>
					<div class="max-w-[85%] rounded-xl bg-surface px-3 py-2 text-sm text-ink whitespace-pre-line">
						{initialMessage}
					</div>
				</div>
			</div>
		</div>
	{:else if store.messages.length === 0}
		<div class="flex-1 overflow-y-auto p-3">
			<div class="flex h-full flex-col items-center justify-center text-center px-4">
				<p class="max-w-xs text-sm text-ink-muted">
					{contextHint || `Ask ${agentName} anything`}
				</p>
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
