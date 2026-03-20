<script lang="ts">
	import type { Message } from '$lib/api';

	function handleLinkClick(e: MouseEvent) {
		const a = (e.target as HTMLElement).closest('a');
		if (!a) return;
		const href = a.getAttribute('href');
		if (!href || (!href.startsWith('http://') && !href.startsWith('https://'))) return;
		e.preventDefault();
		// @ts-ignore — withGlobalTauri exposes this
		window.__TAURI__?.shell?.open(href);
	}

	let {
		messages,
		activeAgent,
		agentName,
		streamingContent,
		isStreaming,
		isTyping,
		avatarUri
	}: {
		messages: Message[];
		activeAgent: { avatar?: string } | undefined;
		agentName: string;
		streamingContent: string;
		isStreaming: boolean;
		isTyping: boolean;
		avatarUri?: string;
	} = $props();

	const WINDOW_SIZE = 40;
	const EST_HEIGHT = 72;

	// Only render the last WINDOW_SIZE messages plus a spacer for the rest
	let visibleStart = $derived(Math.max(0, messages.length - WINDOW_SIZE));

	let container: HTMLDivElement | undefined = $state();
	let userScrolledUp = $state(false);
	let scrollRafId: number | null = null;

	// Load more messages when user scrolls to top (-1 = not requested)
	let loadMoreStart = $state(-1);

	function onScroll() {
		if (!container) return;
		const threshold = 80;
		userScrolledUp = container.scrollHeight - container.scrollTop - container.clientHeight > threshold;

		// If scrolled near top and there are hidden messages, show more
		if (container.scrollTop < 200 && visibleStart > 0) {
			loadMoreStart = Math.max(0, visibleStart - WINDOW_SIZE);
		}
	}

	// Extend visible range when user scrolls up
	let extendedStart = $derived(loadMoreStart >= 0 ? Math.min(visibleStart, loadMoreStart) : visibleStart);
	let allVisibleMessages = $derived(messages.slice(extendedStart));
	let actualTopSpacer = $derived(extendedStart * EST_HEIGHT);

	function scrollToBottom() {
		if (container) {
			container.scrollTop = container.scrollHeight;
		}
	}

	// Auto-scroll on new content — RAF-gated
	// Read .length to create a fine-grained dependency on array mutations (push)
	$effect(() => {
		messages.length;
		streamingContent;
		if (userScrolledUp) return;
		if (!scrollRafId) {
			scrollRafId = requestAnimationFrame(() => {
				scrollToBottom();
				scrollRafId = null;
			});
		}
	});

	let avatarChar = $derived(activeAgent?.avatar || agentName.charAt(0));
	let hasImageAvatar = $derived(!!avatarUri);
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div bind:this={container} onscroll={onScroll} onclick={handleLinkClick} class="flex-1 overflow-y-auto p-3">
	{#if allVisibleMessages.length === 0}
		<!-- empty state handled by parent -->
	{:else}
		<div class="space-y-3">
			<!-- Spacer for virtualized messages above -->
			{#if actualTopSpacer > 0}
				<div style="height: {actualTopSpacer}px"></div>
			{/if}

			{#each allVisibleMessages as message (message.id)}
				<div class="flex gap-2" class:justify-end={message.role === 'user'}>
					{#if message.role === 'assistant'}
						{#if hasImageAvatar}<img class="h-7 w-7 shrink-0 rounded-lg object-cover" src={avatarUri} alt={agentName} />{:else}<div class="vulti-avatar flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs font-bold">{avatarChar}</div>{/if}
					{/if}
					<div
						class="max-w-[85%] rounded-xl px-3 py-2 text-sm"
						class:bg-primary={message.role === 'user'}
						class:text-white={message.role === 'user'}
						class:bg-surface={message.role === 'assistant'}
						class:text-ink={message.role === 'assistant'}
					>
						<div class="prose prose-sm">{@html message.content}</div>
					</div>
				</div>
			{/each}

			<!-- Streaming content -->
			{#if isStreaming && streamingContent}
				<div class="flex gap-2">
					{#if hasImageAvatar}<img class="h-7 w-7 shrink-0 rounded-lg object-cover" src={avatarUri} alt={agentName} />{:else}<div class="vulti-avatar flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs font-bold">{avatarChar}</div>{/if}
					<div class="max-w-[85%] rounded-xl bg-surface px-3 py-2 text-sm text-ink">
						<div class="prose prose-sm">{streamingContent}</div>
						<span class="streaming-cursor"></span>
					</div>
				</div>
			{/if}

			<!-- Typing indicator -->
			{#if isTyping && !isStreaming}
				<div class="flex gap-2">
					{#if hasImageAvatar}<img class="h-7 w-7 shrink-0 rounded-lg object-cover" src={avatarUri} alt={agentName} />{:else}<div class="vulti-avatar flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs font-bold">{avatarChar}</div>{/if}
					<div class="rounded-xl bg-surface px-3 py-2">
						<div class="flex gap-1">
							<span class="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-muted" style="animation-delay: 0ms"></span>
							<span class="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-muted" style="animation-delay: 150ms"></span>
							<span class="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-muted" style="animation-delay: 300ms"></span>
						</div>
					</div>
				</div>
			{/if}
		</div>
	{/if}
</div>

<style>
	.vulti-avatar {
		background: linear-gradient(135deg, #E8607A, #F0A84A, #4AC6B7, #6B8BEB, #9D7AEA);
		background-size: 200% 200%;
		color: white;
	}

	.streaming-cursor {
		display: inline-block;
		width: 3px;
		height: 14px;
		border-radius: 1px;
		vertical-align: text-bottom;
		margin-left: 1px;
		background: linear-gradient(180deg, #E8607A, #F0A84A, #4AC6B7, #9D7AEA);
		background-size: 100% 300%;
		animation: cursor-blink 0.8s step-end infinite, cursor-shimmer 2s ease infinite;
	}

	@keyframes cursor-blink {
		0%, 100% { opacity: 1; }
		50% { opacity: 0; }
	}

	@keyframes cursor-shimmer {
		0% { background-position: 0% 0%; }
		50% { background-position: 0% 100%; }
		100% { background-position: 0% 0%; }
	}
</style>
