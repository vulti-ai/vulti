<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { tick } from 'svelte';
	import VultiLogo from '$lib/components/VultiLogo.svelte';

	let input = $state('');
	let messagesEl: HTMLDivElement | undefined = $state();
	let showSessions = $state(false);

	async function send() {
		const text = input.trim();
		if (!text) return;

		if (!store.activeSessionId) {
			await store.createSession();
		}

		store.sendMessage(text);
		input = '';
		await tick();
		scrollToBottom();
	}

	function scrollToBottom() {
		if (messagesEl) {
			messagesEl.scrollTop = messagesEl.scrollHeight;
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			send();
		}
	}

	function selectSession(id: string) {
		store.switchSession(id);
		showSessions = false;
	}

	// Auto-scroll on new messages
	$effect(() => {
		store.messages;
		store.streamingContent;
		tick().then(scrollToBottom);
	});
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="flex h-full flex-col">
	<!-- Header -->
	<header class="flex h-14 shrink-0 items-center justify-between border-b border-border px-6">
		<div class="relative flex items-center gap-3">
			<button
				onclick={() => (showSessions = !showSessions)}
				class="flex items-center gap-2 rounded-lg px-2 py-1 text-left hover:bg-surface-hover"
			>
				<h2 class="font-semibold">
					{#if store.activeSessionId}
						{store.sessions.find(s => s.id === store.activeSessionId)?.name || 'Chat'}
					{:else}
						New Conversation
					{/if}
				</h2>
				<svg class="h-4 w-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
				</svg>
			</button>

			<!-- Sessions dropdown -->
			{#if showSessions}
				<!-- Backdrop -->
				<div class="fixed inset-0 z-40" onclick={() => (showSessions = false)} onkeydown={() => {}}></div>
				<div class="absolute left-0 top-full z-50 mt-1 w-64 rounded-lg border border-border bg-slate-900 py-1 shadow-xl">
					<div class="flex items-center justify-between border-b border-border px-3 py-2">
						<span class="text-xs font-medium uppercase tracking-wider text-slate-500">Sessions</span>
						<button
							onclick={() => { store.createSession(); showSessions = false; }}
							class="rounded px-2 py-0.5 text-xs text-primary hover:bg-surface-hover"
						>
							+ New
						</button>
					</div>
					<div class="max-h-64 overflow-y-auto">
						{#each store.sessions as session}
							<div class="group flex items-center">
								<button
									onclick={() => selectSession(session.id)}
									class="flex-1 truncate px-3 py-2 text-left text-sm transition-colors"
									class:text-white={store.activeSessionId === session.id}
									class:bg-surface-active={store.activeSessionId === session.id}
									class:text-slate-400={store.activeSessionId !== session.id}
									class:hover:bg-surface-hover={store.activeSessionId !== session.id}
								>
									{session.name || 'Untitled'}
								</button>
								<button
									onclick={() => store.deleteSession(session.id)}
									class="mr-2 text-xs text-slate-500 opacity-0 hover:text-red-400 group-hover:opacity-100"
									title="Delete"
								>
									x
								</button>
							</div>
						{/each}
						{#if store.sessions.length === 0}
							<p class="px-3 py-2 text-xs text-slate-500">No sessions yet</p>
						{/if}
					</div>
				</div>
			{/if}
		</div>
		<button
			onclick={() => store.createSession()}
			class="rounded-lg bg-surface px-3 py-1.5 text-sm text-slate-300 hover:bg-surface-hover"
		>
			+ New Chat
		</button>
	</header>

	<!-- Messages -->
	<div bind:this={messagesEl} class="flex-1 overflow-y-auto p-6">
		{#if store.messages.length === 0 && !store.activeSessionId}
			<div class="flex h-full flex-col items-center justify-center text-center">
				<div class="mb-6">
					<VultiLogo mode="wordmark" size={28} />
				</div>
				<p class="max-w-md text-sm text-slate-400">
					Start a conversation with your AI agent. Ask anything, manage tasks, or review messages from your connected platforms.
				</p>
			</div>
		{:else}
			<div class="mx-auto max-w-3xl space-y-4">
				{#each store.messages as message}
					<div class="flex gap-3" class:justify-end={message.role === 'user'}>
						{#if message.role === 'assistant'}
							<div class="vulti-avatar flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-sm font-bold">H</div>
						{/if}
						<div
							class="max-w-[80%] rounded-xl px-4 py-2.5 text-sm"
							class:bg-primary={message.role === 'user'}
							class:text-white={message.role === 'user'}
							class:bg-surface={message.role === 'assistant'}
							class:text-slate-200={message.role === 'assistant'}
						>
							<div class="prose">{@html message.content}</div>
						</div>
					</div>
				{/each}

				<!-- Streaming content -->
				{#if store.isStreaming && store.streamingContent}
					<div class="flex gap-3">
						<div class="vulti-avatar flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-sm font-bold">H</div>
						<div class="max-w-[80%] rounded-xl bg-surface px-4 py-2.5 text-sm text-slate-200">
							<div class="prose">{store.streamingContent}</div>
							<span class="inline-block h-4 w-1 animate-pulse bg-primary"></span>
						</div>
					</div>
				{/if}

				<!-- Typing indicator -->
				{#if store.isTyping && !store.isStreaming}
					<div class="flex gap-3">
						<div class="vulti-avatar flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-sm font-bold">H</div>
						<div class="rounded-xl bg-surface px-4 py-3">
							<div class="flex gap-1">
								<span class="h-2 w-2 animate-bounce rounded-full bg-slate-400" style="animation-delay: 0ms"></span>
								<span class="h-2 w-2 animate-bounce rounded-full bg-slate-400" style="animation-delay: 150ms"></span>
								<span class="h-2 w-2 animate-bounce rounded-full bg-slate-400" style="animation-delay: 300ms"></span>
							</div>
						</div>
					</div>
				{/if}
			</div>
		{/if}
	</div>

	<!-- Input -->
	<div class="shrink-0 border-t border-border p-4">
		<div class="mx-auto flex max-w-3xl gap-3">
			<textarea
				bind:value={input}
				onkeydown={handleKeydown}
				placeholder="Message Vulti..."
				rows="1"
				class="flex-1 resize-none rounded-xl border border-border bg-surface px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-primary focus:outline-none"
			></textarea>
			<button
				onclick={send}
				disabled={!input.trim()}
				class="rounded-xl bg-primary px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary-hover disabled:opacity-40"
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
		animation: rainbow-shift 8s linear infinite;
		color: white;
	}
	@keyframes rainbow-shift {
		0%   { background-position: 0% 50%; }
		100% { background-position: 200% 50%; }
	}
</style>
